import type { ApiErrorAttempt, ApiErrorBody, ValidationItem } from '../types';

/** Normalised view of a backend error envelope (or a transport failure). */
export interface ApiError {
  status: number;
  errorCode: string;
  message: string;
  requestId: string | null;
  llmRequestId?: string;
  attempts?: ApiErrorAttempt[];
  routingPath?: string[];
  estimatedTokens?: number;
  largestWindow?: number | null;
  /** Raw 422 items, kept so a form can map them to fields. */
  validation?: ValidationItem[];
}

/** An Error that carries the envelope fields — what `api.ts` throws. */
export type ApiErrorLike = Error & Partial<Omit<ApiError, 'message'>>;

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;

const codeForStatus = (status: number): string => {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 413) return 'payload_too_large';
  if (status === 422) return 'validation_error';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'database_unavailable';
  if (status >= 500) return 'internal_error';
  return 'http_error';
};

const formatValidationItem = (item: ValidationItem): string => {
  const field = (item.loc || []).filter((p) => p !== 'body').join('.');
  const msg = item.msg || 'invalid value';
  return field ? `${field}: ${msg}` : msg;
};

/** Human summary of a `detail` that may be a string, a 422 array or junk —
 * never the literal "[object Object]". */
export const summariseDetail = (detail: unknown, fallback: string): string => {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const items = detail.filter(isRecord) as ValidationItem[];
    if (items.length === 0) return fallback;
    const first = formatValidationItem(items[0]);
    return items.length > 1 ? `${first} (+${items.length - 1} more)` : first;
  }
  if (isRecord(detail)) {
    if (typeof detail.message === 'string' && detail.message) return detail.message;
    if (typeof detail.msg === 'string' && detail.msg) return detail.msg;
  }
  return fallback;
};

/**
 * Parse a backend error response (a fetch `Response` whose body was already
 * read, or the parsed body object) into an `ApiError`. Missing envelope fields
 * are derived from the status, never invented.
 */
export const parseApiError = (
  input: Response | Partial<ApiErrorBody> | unknown,
  status: number,
  fallbackMessage = `Request failed (HTTP ${status})`,
): ApiError => {
  const body: Partial<ApiErrorBody> = isRecord(input) && !(input instanceof Response) ? (input as Partial<ApiErrorBody>) : {};
  const headerRequestId =
    input instanceof Response && typeof input.headers?.get === 'function'
      ? input.headers.get('X-Request-ID')
      : null;

  const detail = body.detail;
  const validation = Array.isArray(detail) ? (detail.filter(isRecord) as ValidationItem[]) : undefined;
  const message =
    (typeof body.message === 'string' && body.message.trim()) || summariseDetail(detail, fallbackMessage);

  return {
    status,
    errorCode: typeof body.error_code === 'string' && body.error_code ? body.error_code : codeForStatus(status),
    message,
    requestId: (typeof body.request_id === 'string' && body.request_id) || headerRequestId || null,
    llmRequestId: typeof body.llm_request_id === 'string' ? body.llm_request_id : undefined,
    attempts: Array.isArray(body.attempts) ? body.attempts : undefined,
    routingPath: Array.isArray(body.routing_path) ? body.routing_path : undefined,
    estimatedTokens: typeof body.estimated_tokens === 'number' ? body.estimated_tokens : undefined,
    largestWindow: body.largest_window === null || typeof body.largest_window === 'number' ? body.largest_window : undefined,
    validation,
  };
};

/** Build the Error `api.ts` throws so callers keep `status`/`errorCode`/`requestId`/`attempts`. */
export const toApiErrorInstance = (parsed: ApiError): ApiErrorLike => {
  const err = new Error(parsed.message) as ApiErrorLike;
  err.status = parsed.status;
  err.errorCode = parsed.errorCode;
  err.requestId = parsed.requestId;
  if (parsed.llmRequestId) err.llmRequestId = parsed.llmRequestId;
  if (parsed.attempts) err.attempts = parsed.attempts;
  if (parsed.routingPath) err.routingPath = parsed.routingPath;
  if (parsed.estimatedTokens !== undefined) err.estimatedTokens = parsed.estimatedTokens;
  if (parsed.largestWindow !== undefined) err.largestWindow = parsed.largestWindow;
  if (parsed.validation) err.validation = parsed.validation;
  return err;
};

/** Read the envelope fields back off an unknown thrown value. */
export const fromUnknownError = (err: unknown): Partial<ApiError> & { name?: string } => {
  if (!isRecord(err)) return { message: typeof err === 'string' ? err : undefined };
  const e = err as Partial<ApiErrorLike> & { name?: string; code?: string };
  return {
    name: e.name,
    status: typeof e.status === 'number' ? e.status : undefined,
    errorCode: typeof e.errorCode === 'string' ? e.errorCode : undefined,
    message: typeof e.message === 'string' ? e.message : undefined,
    requestId: typeof e.requestId === 'string' ? e.requestId : null,
    attempts: Array.isArray(e.attempts) ? e.attempts : undefined,
    estimatedTokens: typeof e.estimatedTokens === 'number' ? e.estimatedTokens : undefined,
    largestWindow: e.largestWindow,
  };
};

const attemptsList = (attempts: ApiErrorAttempt[] | undefined): string =>
  (attempts || [])
    .map((a) => `${a.provider}${a.model ? `/${a.model}` : ''}→${a.failure_kind || 'unknown'}`)
    .join(', ');

/**
 * Friendly copy per error_code. Timeouts/aborts are recognised by the DOM
 * exception name so a 300 s LLM budget reads as "timed out", not "failed".
 */
export const toUserMessage = (
  err: Partial<ApiError> & { name?: string } | unknown,
  opts: { timeoutMs?: number } = {},
): string => {
  const e = fromUnknownError(err);
  if (e.name === 'TimeoutError' || e.name === 'AbortError') {
    const secs = opts.timeoutMs ? Math.round(opts.timeoutMs / 1000) : undefined;
    return secs ? `Request timed out after ${secs}s.` : 'Request timed out.';
  }
  const code = e.errorCode;
  const n = e.attempts?.length ?? 0;
  switch (code) {
    case 'all_candidates_failed':
      return n > 0
        ? `All AI routes failed — nothing was fabricated. ${n} attempt${n === 1 ? '' : 's'}: ${attemptsList(e.attempts)}.`
        : 'All AI routes failed — nothing was fabricated.';
    case 'context_window_exceeded': {
      const tokens = e.estimatedTokens != null ? `~${e.estimatedTokens.toLocaleString()} tokens` : 'more context than any model allows';
      return `Needs ${tokens}; no eligible model can hold it. Nothing was truncated.`;
    }
    case 'rate_limited':
      return 'Too many requests right now — the free-tier limit was hit. Wait a moment and retry.';
    case 'validation_error':
      return e.message ? `Please check your input: ${e.message}` : 'Please check your input — the request was rejected as invalid.';
    case 'llm_error':
      return e.message ? `The AI provider returned an error: ${e.message}` : 'The AI provider returned an error.';
    case 'database_unavailable':
      return 'The database is unavailable right now. Nothing was lost — retry shortly.';
    case 'unauthorized':
      return 'Your session has expired. Please sign in again.';
    case 'forbidden':
      return e.message || 'You do not have access to this resource.';
    case 'not_found':
      return e.message || 'That item could not be found.';
    case 'payload_too_large':
      return 'The upload is too large for the server to accept.';
    case 'internal_error':
      return 'The server hit an internal error. Nothing was fabricated — retry, and quote the request ID if it persists.';
    default:
      return e.message || 'The request did not complete.';
  }
};

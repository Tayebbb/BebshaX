export const SESSION_CHANGED = 'bebshax:session-changed';
const REFRESH_CREDENTIAL_KEY = 'bebshax_refresh_token';
let epoch = 0;
let controller = new AbortController();
let notificationPending = false;
let csrfToken: string | null = null;
let refreshCredential: string | null = null;
/** Installed by api.ts: refreshes the session and returns replacement auth
 * headers, or null when the session is gone for good. */
let recoverUnauthorized: (() => Promise<Record<string, string> | null>) | null = null;

export function hasCookieSession(): boolean {
  return localStorage.getItem('bebshax_cookie_session') === '1';
}

export function setCookieSession(csrf: string | null): void {
  csrfToken = csrf;
  if (csrf) localStorage.setItem('bebshax_cookie_session', '1');
  else localStorage.removeItem('bebshax_cookie_session');
}

// Tab-scoped like the bearer access token: without it a reload after the
// 15-minute access lifetime had no way back but the sign-in form.
export function setRefreshCredential(value: string | null): void {
  refreshCredential = value;
  try {
    if (value) sessionStorage.setItem(REFRESH_CREDENTIAL_KEY, value);
    else sessionStorage.removeItem(REFRESH_CREDENTIAL_KEY);
  } catch {
    // storage unavailable: memory copy still serves this page
  }
}
export function getRefreshCredential(): string | null {
  if (refreshCredential) return refreshCredential;
  try {
    refreshCredential = sessionStorage.getItem(REFRESH_CREDENTIAL_KEY);
  } catch {
    refreshCredential = null;
  }
  return refreshCredential;
}

export function resetSessionSecrets(): void {
  csrfToken = null;
  setRefreshCredential(null);
}

export function setUnauthorizedRecovery(handler: (() => Promise<Record<string, string> | null>) | null): void {
  recoverUnauthorized = handler;
}

export function csrfHeaders(): Record<string, string> {
  return hasCookieSession() && csrfToken ? { 'X-CSRF-Token': csrfToken, 'X-Auth-Transport': 'cookie' } : {};
}

export function getSessionEpoch(): number { return epoch; }

export function advanceSession(notify = true): void {
  epoch += 1;
  controller.abort();
  controller = new AbortController();
  if (notify && !notificationPending) {
    notificationPending = true;
    queueMicrotask(() => {
      notificationPending = false;
      window.dispatchEvent(new Event(SESSION_CHANGED));
    });
  }
}

export function purgePrivateSnapshots(): void {
  for (const storage of [localStorage, sessionStorage]) {
    for (const key of Object.keys(storage)) {
      if (/^bebshax_(studies|study|draft|personas|reports|interviews|conv|job|script_generated)_/.test(key)) storage.removeItem(key);
    }
  }
}

export function sessionSignal(signal?: AbortSignal, timeoutMs?: number): AbortSignal {
  const signals = signal ? [signal, controller.signal] : [controller.signal];
  if (timeoutMs !== undefined) signals.push(AbortSignal.timeout(timeoutMs));
  if (typeof AbortSignal.any === 'function') return AbortSignal.any(signals);
  const combined = new AbortController();
  const abort = () => {
    combined.abort(signals.find((source) => source.aborted)?.reason);
    for (const source of signals) source.removeEventListener('abort', abort);
  };
  for (const source of signals) {
    if (source.aborted) { abort(); break; }
    source.addEventListener('abort', abort, { once: true });
  }
  return combined.signal;
}

export function assertSession(expected: number): void {
  if (expected !== epoch) throw new DOMException('Session changed', 'AbortError');
}

function hasAuthorizationHeader(init: RequestInit): boolean {
  const headers = (init.headers as Record<string, string> | undefined) ?? {};
  return Object.keys(headers).some((name) => name.toLowerCase() === 'authorization');
}

function credentialed(init: RequestInit): boolean {
  return hasCookieSession() || getRefreshCredential() !== null || hasAuthorizationHeader(init);
}

function recoverable(input: RequestInfo | URL, init: RequestInit): boolean {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  return !/\/api\/auth\//.test(url) && credentialed(init);
}

function withReplacementHeaders(init: RequestInit, replacement: Record<string, string>): RequestInit {
  const headers = { ...(init.headers as Record<string, string> | undefined) };
  for (const name of Object.keys(headers)) {
    if (name.toLowerCase() === 'authorization') delete headers[name];
  }
  return { ...init, headers: { ...headers, ...replacement } };
}

export async function sessionFetch(input: RequestInfo | URL, init: RequestInit = {}, retried = false): Promise<Response> {
  const expected = epoch;
  const signal = sessionSignal(init.signal ?? undefined);
  signal.throwIfAborted();
  // Access credential already expired but a refresh credential is held: rotate
  // first. Owner-scoped endpoints answer 404 to anonymous writes, which no
  // 401 replay could repair.
  if (!retried && recoverUnauthorized !== null && !hasAuthorizationHeader(init) && !hasCookieSession()
      && getRefreshCredential() !== null && recoverable(input, init)) {
    const replacement = await recoverUnauthorized();
    assertSession(expected);
    signal.throwIfAborted();
    if (replacement !== null) return sessionFetch(input, withReplacementHeaders(init, replacement), true);
  }
  const response = await globalThis.fetch(input, {
    ...init, credentials: 'include', signal,
    headers: { ...(init.headers as Record<string, string> | undefined), ...csrfHeaders() },
  });
  assertSession(expected);
  signal.throwIfAborted();
  // An expired access credential is not a sign-out: refresh once and replay.
  if (response.status === 401 && !retried && recoverUnauthorized !== null && recoverable(input, init)) {
    const replacement = await recoverUnauthorized();
    assertSession(expected);
    signal.throwIfAborted();
    if (replacement !== null) return sessionFetch(input, withReplacementHeaders(init, replacement), true);
  }
  if (typeof response.json === 'function') {
    const readJson = response.json.bind(response);
    response.json = async () => {
      const value: unknown = await readJson();
      assertSession(expected);
      signal.throwIfAborted();
      return value;
    };
  }
  return response;
}
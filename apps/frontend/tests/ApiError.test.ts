import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { api } from '../src/services/api';
import { parseApiError, toUserMessage, toApiErrorInstance, summariseDetail } from '../src/utils/apiError';

describe('parseApiError — backend error envelope', () => {
  it('summarises a 422 validation array instead of "[object Object]"', () => {
    const body = {
      detail: [
        { loc: ['body', 'study_prompt'], msg: 'field required', type: 'missing' },
        { loc: ['body', 'roles', 0, 'count'], msg: 'must be >= 0', type: 'value_error' },
      ],
      error_code: 'validation_error',
      request_id: 'req_422_abc',
      message: 'Request validation failed (2 fields)',
    };
    const err = parseApiError(body, 422);

    expect(err.status).toBe(422);
    expect(err.errorCode).toBe('validation_error');
    expect(err.requestId).toBe('req_422_abc');
    // The backend summary wins; the raw items are kept for form mapping.
    expect(err.message).toBe('Request validation failed (2 fields)');
    expect(err.validation).toHaveLength(2);
    expect(err.message).not.toMatch(/\[object Object\]/);

    // Without a summary, the first item is rendered as "field: msg (+n more)".
    const noSummary = parseApiError({ ...body, message: undefined }, 422);
    expect(noSummary.message).toBe('study_prompt: field required (+1 more)');
  });

  it('parses a 503 all_candidates_failed body with attempts and request id', () => {
    const body = {
      detail: 'All candidate routes failed',
      error_code: 'all_candidates_failed',
      request_id: 'req_503_xyz',
      llm_request_id: 'llm_77',
      attempts: [
        { provider: 'groq', model: 'llama-3.3-70b', failure_kind: 'RATE_LIMITED', fallback_reason: 'HTTP 429' },
        { provider: 'mistral', model: 'mistral-small', failure_kind: 'SERVER_ERROR', fallback_reason: 'HTTP 502' },
      ],
      routing_path: ['groq/llama-3.3-70b', 'mistral/mistral-small'],
    };
    const err = parseApiError(body, 503);

    expect(err.errorCode).toBe('all_candidates_failed');
    expect(err.requestId).toBe('req_503_xyz');
    expect(err.llmRequestId).toBe('llm_77');
    expect(err.attempts).toHaveLength(2);
    expect(err.routingPath).toEqual(['groq/llama-3.3-70b', 'mistral/mistral-small']);

    const instance = toApiErrorInstance(err);
    expect(instance).toBeInstanceOf(Error);
    expect(instance.status).toBe(503);
    expect(instance.errorCode).toBe('all_candidates_failed');
    expect(instance.requestId).toBe('req_503_xyz');
    expect(instance.attempts).toHaveLength(2);
  });

  it('derives an error code from the status when the envelope is missing', () => {
    expect(parseApiError({}, 404).errorCode).toBe('not_found');
    expect(parseApiError({}, 429).errorCode).toBe('rate_limited');
    expect(parseApiError({ detail: 'nope' }, 500).message).toBe('nope');
    expect(parseApiError({}, 500, 'Fallback copy').message).toBe('Fallback copy');
    expect(parseApiError({}, 500).requestId).toBeNull();
  });

  it('summariseDetail never leaks object stringification', () => {
    expect(summariseDetail({ weird: true }, 'fallback')).toBe('fallback');
    expect(summariseDetail({ message: 'from message' }, 'fallback')).toBe('from message');
    expect(summariseDetail([], 'fallback')).toBe('fallback');
  });
});

describe('toUserMessage — friendly copy per error_code', () => {
  it('explains all_candidates_failed with the attempt list and no fabrication', () => {
    const err = toApiErrorInstance(
      parseApiError(
        {
          detail: 'x',
          error_code: 'all_candidates_failed',
          request_id: 'r1',
          attempts: [
            { provider: 'groq', model: 'llama', failure_kind: 'RATE_LIMITED', fallback_reason: null },
            { provider: 'ollama', model: 'llama3.2:3b', failure_kind: 'TIMEOUT', fallback_reason: null },
          ],
        },
        503,
      ),
    );
    expect(toUserMessage(err)).toBe(
      'All AI routes failed — nothing was fabricated. 2 attempts: groq/llama→RATE_LIMITED, ollama/llama3.2:3b→TIMEOUT.',
    );
  });

  it('explains context_window_exceeded with the token estimate and no truncation', () => {
    const err = toApiErrorInstance(
      parseApiError({ detail: 'x', error_code: 'context_window_exceeded', request_id: 'r2', estimated_tokens: 24500, largest_window: 16384 }, 413),
    );
    expect(toUserMessage(err)).toBe('Needs ~24,500 tokens; no eligible model can hold it. Nothing was truncated.');
  });

  it('covers rate_limited and validation_error', () => {
    expect(toUserMessage(toApiErrorInstance(parseApiError({ error_code: 'rate_limited' }, 429)))).toMatch(/free-tier limit/i);
    const v = toApiErrorInstance(
      parseApiError({ detail: [{ loc: ['body', 'title'], msg: 'too long' }], error_code: 'validation_error' }, 422),
    );
    expect(toUserMessage(v)).toBe('Please check your input: title: too long');
  });

  it('recognises DOM timeout/abort errors and reports the budget', () => {
    const timeout = Object.assign(new Error('signal timed out'), { name: 'TimeoutError' });
    expect(toUserMessage(timeout, { timeoutMs: 300000 })).toBe('Request timed out after 300s.');
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    expect(toUserMessage(abort)).toBe('Request timed out.');
  });

  it('falls back to the error message for plain errors', () => {
    expect(toUserMessage(new Error('LLM providers busy'))).toBe('LLM providers busy');
    expect(toUserMessage(undefined)).toBe('The request did not complete.');
  });
});

describe('saved research API reads', () => {
  const fetchMock = vi.fn<typeof fetch>();
  const studyId = 'study_read_regression';

  beforeEach(() => {
    localStorage.clear();
    api.setMockMode(false);
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    api.setMockMode(true);
    localStorage.clear();
  });

  describe.each([
    {
      name: 'getMarketSegments',
      read: (id: string) => api.getMarketSegments(id),
      emptyResult: [],
    },
    {
      name: 'listStudyInterviews',
      read: (id: string) => api.listStudyInterviews(id),
      emptyResult: { interviews: [], total: 0 },
    },
  ])('$name', ({ read, emptyResult }) => {
    it.each([
      { status: 404, errorCode: 'not_found' },
      { status: 500, errorCode: 'internal_error' },
      { status: 503, errorCode: 'database_unavailable' },
    ])('rejects HTTP $status with its error envelope instead of empty research', async ({ status, errorCode }) => {
      fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
        detail: 'Unable to read saved research',
        error_code: errorCode,
        request_id: 'req_saved_research',
      }), { status, headers: { 'Content-Type': 'application/json' } }));

      const request = read(studyId);

      await expect(request).rejects.toBeInstanceOf(Error);
      await expect(request).rejects.toMatchObject({
        message: 'Unable to read saved research',
        status,
        errorCode,
        requestId: 'req_saved_research',
      });
      expect(api.isLive()).toBe(false);
    });

    it('rejects a non-JSON server error and preserves the request ID header', async () => {
      fetchMock.mockResolvedValueOnce(new Response('Upstream unavailable', {
        status: 502,
        headers: { 'X-Request-ID': 'req_upstream' },
      }));

      await expect(read(studyId)).rejects.toMatchObject({
        message: expect.stringContaining('HTTP 502'),
        status: 502,
        errorCode: 'internal_error',
        requestId: 'req_upstream',
      });
    });

    it('rejects the original transport error instead of empty research', async () => {
      const error = new TypeError('Failed to fetch');
      fetchMock.mockRejectedValueOnce(error);

      await expect(read(studyId)).rejects.toBe(error);
      expect(api.isLive()).toBe(false);
    });

    it('returns genuine empty research from HTTP 200', async () => {
      fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(emptyResult), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

      await expect(read(studyId)).resolves.toEqual(emptyResult);
      expect(fetchMock).toHaveBeenCalledOnce();
      expect(api.isLive()).toBe(true);
    });
  });

  it('preserves the explicit mock segment result without fetching', async () => {
    api.setMockMode(true);

    await expect(api.getMarketSegments(studyId)).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns seeded interviews in explicit mock mode without fetching', async () => {
    api.setMockMode(true);
    await api.resetMockStore();
    const study = api.getStoredUserStudies().find((item) => (item.interviews?.length ?? 0) > 0);
    const interviews = study?.interviews;
    expect(study).toBeDefined();
    if (!study || !interviews) throw new Error('Expected a study fixture with saved interviews');

    await expect(api.listStudyInterviews(study.id)).resolves.toMatchObject({
      total: interviews.length,
      interviews: interviews.map((interview) => ({
        id: interview.id,
        persona_id: interview.persona_id,
        summary: interview.key_takeaway,
      })),
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

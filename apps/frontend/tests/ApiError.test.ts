import { describe, it, expect } from 'vitest';
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

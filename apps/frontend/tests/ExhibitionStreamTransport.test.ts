import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/services/api';

const fetchMock = vi.fn<typeof fetch>();
const encoder = new TextEncoder();
const studyId = 'study_exhibition';
const interviewId = 'interview_exhibition';
const question = 'How do you decide whether to subscribe?';
const donePayload = {
  reply: 'The complete canonical interview reply.',
  turn_number: 2,
  turn_count: 2,
  max_turns: 14,
  is_finished: false,
  topic: 'purchasing',
  topics_explored: { purchasing: 'explored' },
  suggested_questions: ['What would make you reconsider?'],
  latency_ms: 125,
  served_by: 'test/synthetic-fixture',
};

const frame = (event: 'delta' | 'done' | 'error', payload: unknown, newline = '\n'): string => (
  `event: ${event}${newline}data: ${JSON.stringify(payload)}${newline}${newline}`
);

const stubStream = () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  let closed = false;
  const cancel = vi.fn(() => { closed = true; });
  const body = new ReadableStream<Uint8Array>({
    start(streamController) { controller = streamController; },
    cancel,
  });
  fetchMock.mockResolvedValueOnce(new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  }));
  return {
    cancel,
    enqueue(chunk: string | Uint8Array) {
      controller.enqueue(typeof chunk === 'string' ? encoder.encode(chunk) : chunk);
    },
    close() {
      if (!closed) {
        closed = true;
        controller.close();
      }
    },
  };
};

describe('Exhibition interview stream transport', () => {
  let previousMockMode: boolean;

  beforeEach(() => {
    previousMockMode = api.isMockMode();
    api.setMockMode(false);
    localStorage.clear();
    fetchMock.mockReset();
    fetchMock.mockRejectedValue(new Error('Unexpected network request'));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    api.setMockMode(previousMockMode);
    localStorage.clear();
  });

  it('settles on the first done frame and cancels the reader while the server keeps the body open', async () => {
    vi.useFakeTimers();
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    stream.enqueue(frame('delta', { text: 'An incremental draft.' }) + frame('done', donePayload));
    const request: Promise<unknown> = api.sendInterviewMessageStream(studyId, interviewId, question, onDelta);
    const settlement = request.then(
      (value) => ({ status: 'fulfilled' as const, value }),
      (error: unknown) => ({ status: 'rejected' as const, error }),
    );
    let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<'pending before EOF'>((resolve) => {
      deadlineTimer = setTimeout(() => resolve('pending before EOF'), 25);
    });

    try {
      const boundedSettlement = Promise.race([settlement, deadline]);
      await vi.advanceTimersByTimeAsync(25);
      expect(await boundedSettlement).toEqual({ status: 'fulfilled', value: donePayload });
      expect(onDelta.mock.calls).toEqual([['An incremental draft.']]);
      expect(stream.cancel).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringMatching(/\/studies\/study_exhibition\/interviews\/interview_exhibition\/messages\/stream$/),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ content: question }),
          headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
        }),
      );
    } finally {
      if (deadlineTimer !== undefined) clearTimeout(deadlineTimer);
      stream.close();
      await settlement;
    }
  });

  it('keeps the first canonical reply when a duplicate done frame is queued in the same chunk', async () => {
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    stream.enqueue(
      frame('delta', { text: 'An incremental draft.' }) +
      frame('done', donePayload) +
      frame('done', { ...donePayload, reply: 'A duplicate must not replace the reply.', turn_number: 99 }),
    );
    stream.close();

    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta)).resolves.toEqual(donePayload);
    expect(onDelta.mock.calls).toEqual([['An incremental draft.']]);
  });

  it('ignores error and delta frames queued after a successful done frame', async () => {
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    stream.enqueue(
      frame('delta', { text: 'An incremental draft.' }) +
      frame('done', donePayload) +
      frame('error', { kind: 'no_route', detail: 'A late error must not invalidate success.' }) +
      frame('delta', { text: 'A late delta must not reach the transcript.' }),
    );
    stream.close();

    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta)).resolves.toEqual(donePayload);
    expect(onDelta.mock.calls).toEqual([['An incremental draft.']]);
  });

  it('decodes split UTF-8 bytes and CRLF frames with multiline data without corrupting the reply', async () => {
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    const text = 'caf\u00e9 \u20ac \ud83d\ude42';
    const finalReply = { ...donePayload, reply: text };
    const wire = ': keep-alive\r\n\r\n' +
      'event: delta\r\ndata: {"text":\r\n' +
      `data: ${JSON.stringify(text)}}\r\n\r\n` +
      frame('done', finalReply, '\r\n');
    for (const byte of encoder.encode(wire)) {
      stream.enqueue(Uint8Array.of(byte));
    }
    stream.close();

    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta)).resolves.toEqual(finalReply);
    expect(onDelta.mock.calls).toEqual([[text]]);
  });

  it('rejects EOF without a done frame instead of treating partial deltas as a final reply', async () => {
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    stream.enqueue(frame('delta', { text: 'Only a partial reply.' }));
    stream.close();

    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta)).rejects.toThrow(
      'Stream ended without a final reply',
    );
    expect(onDelta.mock.calls).toEqual([['Only a partial reply.']]);
  });

  it('does not fetch when the caller signal is already aborted', async () => {
    const abortController = new AbortController();
    abortController.abort();

    await expect(api.sendInterviewMessageStream(
      studyId, interviewId, question, vi.fn(), abortController.signal,
    )).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a caller abort and cancels an open reader without waiting for EOF', async () => {
    vi.useFakeTimers();
    const stream = stubStream();
    const abortController = new AbortController();
    const onDelta = vi.fn<(text: string) => void>();
    stream.enqueue(frame('delta', { text: 'Only a partial reply.' }));
    const request: Promise<unknown> = api.sendInterviewMessageStream(
      studyId, interviewId, question, onDelta, abortController.signal,
    );
    const settlement = request.then(
      (value) => ({ status: 'fulfilled' as const, value }),
      (error: unknown) => ({ status: 'rejected' as const, error }),
    );
    let deadlineTimer: ReturnType<typeof setTimeout> | undefined;

    try {
      await vi.advanceTimersByTimeAsync(0);
      expect(onDelta.mock.calls).toEqual([['Only a partial reply.']]);
      abortController.abort();
      const deadline = new Promise<'pending after abort'>((resolve) => {
        deadlineTimer = setTimeout(() => resolve('pending after abort'), 25);
      });
      const boundedSettlement = Promise.race([settlement, deadline]);
      await vi.advanceTimersByTimeAsync(25);

      expect(await boundedSettlement).toMatchObject({
        status: 'rejected', error: { name: 'AbortError' },
      });
      expect(stream.cancel).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
        signal: abortController.signal,
      }));
      expect(onDelta).toHaveBeenCalledTimes(1);
    } finally {
      if (deadlineTimer !== undefined) clearTimeout(deadlineTimer);
      stream.close();
      await settlement;
    }
  });

  it('preserves the typed error envelope when an error frame arrives before any done frame', async () => {
    const stream = stubStream();
    const onDelta = vi.fn<(text: string) => void>();
    const failure = {
      kind: 'no_route',
      detail: 'No route could serve this interview turn.',
      error_code: 'all_candidates_failed',
      request_id: 'request_exhibition_failure',
      llm_request_id: 'llm_exhibition_failure',
      attempts: [{ provider: 'test', model: 'synthetic-fixture', failure_kind: 'timeout' }],
    };
    stream.enqueue(
      frame('delta', { text: 'Only a partial reply.' }) + frame('error', failure) + frame('done', donePayload),
    );
    stream.close();

    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta)).rejects.toMatchObject({
      name: 'Error',
      message: failure.detail,
      status: 502,
      kind: failure.kind,
      errorCode: failure.error_code,
      requestId: failure.request_id,
      llmRequestId: failure.llm_request_id,
      attempts: failure.attempts,
    });
    expect(onDelta.mock.calls).toEqual([['Only a partial reply.']]);
  });
});
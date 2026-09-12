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

  it.each([{}, { ...donePayload, reply: 3 }, { ...donePayload, turn_number: -1 }, { ...donePayload, is_finished: 'yes' }])(
    'rejects a malformed terminal payload without reporting a canonical reply', async (payload) => {
      const stream = stubStream();
      stream.enqueue(frame('done', payload));
      await expect(api.sendInterviewMessageStream(studyId, interviewId, question, vi.fn()))
        .rejects.toThrow(/Invalid interview reply/);
      expect(stream.cancel).toHaveBeenCalledTimes(1);
    },
  );

  it.each([{}, { text: 42 }, { text: null }])('rejects malformed deltas without calling the consumer', async (payload) => {
    const stream = stubStream();
    const onDelta = vi.fn();
    stream.enqueue(frame('delta', payload) + frame('done', donePayload));
    stream.close();
    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, onDelta))
      .rejects.toThrow(/Invalid interview delta/);
    expect(onDelta).not.toHaveBeenCalled();
  });

  it('bounds an unterminated frame and cancels the reader without truncating an answer', async () => {
    const stream = stubStream();
    stream.enqueue('event: delta\ndata: ' + 'x'.repeat(1024 * 1024 + 1));
    await expect(api.sendInterviewMessageStream(studyId, interviewId, question, vi.fn()))
      .rejects.toThrow(/frame.*limit/i);
    expect(stream.cancel).toHaveBeenCalledTimes(1);
  });

  it('preserves a detail server failure instead of reporting a missing interview', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Interview storage unavailable' }), { status: 500 }));
    await expect(api.getStudyInterviewDetail(studyId, interviewId))
      .rejects.toMatchObject({ status: 500, message: 'Interview storage unavailable' });
  });

  it('rejects malformed flat interview detail rather than rendering fabricated state', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}'));
    await expect(api.getStudyInterviewDetail(studyId, interviewId)).rejects.toThrow('Invalid interview detail');
  });

  it('validates a blocking reply using the same contract as the stream terminal', async () => {
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 200 }));
    await expect(api.sendInterviewMessage(studyId, interviewId, { content: question }))
      .rejects.toThrow(/Invalid interview reply/);
  });

  it('accepts an interview closed without synthesis only when the server says so explicitly', async () => {
    const closed = {
      id: interviewId, status: 'completed', summary: null, key_findings: [], structured_insights: [],
      insights_dropped: 0, source: 'unavailable', served_by: null, error_code: 'llm_error:AllCandidatesFailed',
    };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(closed), { status: 200 }));
    await expect(api.completeStudyInterview(studyId, interviewId)).resolves.toEqual(closed);

    // A null summary with no explicit reason would let a silent failure pass as a completed analysis.
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ...closed, source: 'llm' }), { status: 200 }));
    await expect(api.completeStudyInterview(studyId, interviewId)).rejects.toThrow('Invalid interview synthesis response');
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ...closed, source: undefined }), { status: 200 }));
    await expect(api.completeStudyInterview(studyId, interviewId)).rejects.toThrow('Invalid interview synthesis response');
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ...closed, summary: '   ', source: 'llm' }), { status: 200 }));
    await expect(api.completeStudyInterview(studyId, interviewId)).rejects.toThrow('Invalid interview synthesis response');
  });

  it('keeps a written synthesis intact and rejects malformed synthesis metadata', async () => {
    const written = {
      id: interviewId, status: 'completed', summary: 'The persona values predictable pickup windows.',
      key_findings: ['Time slots matter more than price.'], structured_insights: [], source: 'llm',
      served_by: 'test/synthetic-fixture', error_code: null, insights_dropped: 0,
    };
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(written), { status: 200 }));
    await expect(api.completeStudyInterview(studyId, interviewId)).resolves.toEqual(written);
    for (const broken of [
      { ...written, status: 'active' }, { ...written, source: 'template' },
      { ...written, insights_dropped: -1 }, { ...written, error_code: 7 }, { ...written, key_findings: [1] },
    ]) {
      fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(broken), { status: 200 }));
      await expect(api.completeStudyInterview(studyId, interviewId)).rejects.toThrow('Invalid interview synthesis response');
    }
  });

  it('never fetches a cancelled detail, fallback, or synthesis request', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(api.getStudyInterviewDetail(studyId, interviewId, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await expect(api.sendInterviewMessage(studyId, interviewId, { content: question }, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    await expect(api.completeStudyInterview(studyId, interviewId, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(['detail', 'reply', 'synthesis'] as const)('bounds %s transport even without a caller signal', async (operation) => {
    const deadline = new AbortController();
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(deadline.signal);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Fixture unavailable' }), { status: 503 }));
    const request = operation === 'detail' ? api.getStudyInterviewDetail(studyId, interviewId)
      : operation === 'reply' ? api.sendInterviewMessage(studyId, interviewId, { content: question })
      : api.completeStudyInterview(studyId, interviewId);
    await expect(request).rejects.toMatchObject({ status: 503 });
    expect(timeout).toHaveBeenCalledWith(expect.any(Number));
    const milliseconds = timeout.mock.calls[0][0];
    expect(milliseconds).toBeGreaterThan(0);
    expect(milliseconds).toBeLessThanOrEqual(600000);
  });

  it('closes a stalled stream at its transport deadline without fabricating a completed reply', async () => {
    const deadline = new AbortController();
    const timeout = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(deadline.signal);
    const stream = stubStream();
    const pending = api.sendInterviewMessageStream(studyId, interviewId, question, vi.fn());
    const settled = pending.then((value) => ({ value }), (error: unknown) => ({ error }));
    await Promise.resolve();
    await Promise.resolve();
    deadline.abort(new DOMException('Interview request timed out', 'TimeoutError'));
    stream.close();

    await expect(settled).resolves.toMatchObject({ error: { name: 'TimeoutError' } });
    expect(timeout).toHaveBeenCalled();
    expect(stream.cancel).toHaveBeenCalledTimes(1);
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
      const transportSignal = fetchMock.mock.calls[0][1]?.signal;
      expect(transportSignal).toBeInstanceOf(AbortSignal);
      expect(transportSignal?.aborted).toBe(false);
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
        signal: transportSignal,
      }));
      expect(transportSignal?.aborted).toBe(true);
      expect(transportSignal?.reason).toBe(abortController.signal.reason);
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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/services/api';

const url = 'http://127.0.0.1:8000/api/studies/poll-study/reports/generate/jobs/poll-job';
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe('Frontend bounded job observation', () => {
  beforeEach(() => {
    api.setMockMode(false);
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    api.setMockMode(true);
  });

  it('does not fetch an already cancelled job observation', async () => {
    const controller = new AbortController();
    controller.abort();
    vi.mocked(fetch).mockResolvedValue(response({ status: 'completed', result: { title: 'Saved' } }));
    await expect(api.pollGenerationJob(url, { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('stops immediately on unauthorized job access instead of retrying', async () => {
    vi.mocked(fetch).mockImplementation(async () => response({ detail: 'Unauthorized' }, 401));
    const result = api.pollGenerationJob(url, { intervalMs: 100 }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(1000);
    expect(await result).toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('never overlaps slow poll reads', async () => {
    let finishFirst!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finishFirst = resolve; }))
      .mockResolvedValueOnce(response({ status: 'completed', result: { title: 'Saved report' } }));
    const result = api.pollGenerationJob(url, { intervalMs: 1000, timeoutMs: 20000 });
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetch).toHaveBeenCalledTimes(1);
    finishFirst(response({ status: 'running' }));
    await vi.advanceTimersByTimeAsync(1000);
    await expect(result).resolves.toEqual({ title: 'Saved report' });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('rejects a completed job without a valid result instead of returning null', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response({ status: 'completed', result: null }));
    const result = api.pollGenerationJob(url, { intervalMs: 100 }).catch((error: unknown) => error);
    await vi.advanceTimersByTimeAsync(1000);
    expect(await result).toBeInstanceOf(Error);
  });

  it('bounds a stalled read and distinguishes stopped observation from failed generation', async () => {
    let finishRead!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { finishRead = resolve; }));
    let outcome: unknown;
    const result = api.pollGenerationJob(url, { timeoutMs: 1000 }).then(
      (value) => { outcome = value; }, (error: unknown) => { outcome = error; },
    );
    await vi.advanceTimersByTimeAsync(1001);
    try {
      expect(outcome).toMatchObject({ jobContinues: true });
      expect(vi.mocked(fetch).mock.calls[0][1]?.signal?.aborted).toBe(true);
    } finally {
      finishRead(response({ status: 'completed', result: { title: 'Saved later' } }));
      await result;
    }
  });

  it('resumes an accepted report handle with GET and never submits duplicate generation', async () => {
    const report = { id: 'saved-report', title: 'Saved result', executive_summary: 'Full summary', key_findings: [], recommendations: [] };
    api.rememberJobHandle('poll-study', 'report', 'poll-job');
    vi.mocked(fetch).mockResolvedValueOnce(response({ status: 'completed', result: report }))
      .mockResolvedValueOnce(response(report));
    await expect(api.generateStudyReport('poll-study')).resolves.toEqual(report);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBeUndefined();
    expect(api.getPendingJobHandle('poll-study', 'report')).toBeNull();
  });
});
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { api } from '../src/services/api';

/**
 * `getStudies()` is called by three independent consumers on a single dashboard
 * mount, and the sidebar re-runs it on every tab switch. The coalescing cache
 * that fixes that is only exercised in live mode — an earlier version of it was
 * a silent no-op in production because the read's own write-through invalidated
 * the entry it had just created, and mock mode structurally hid the bug.
 *
 * These tests pin the live-mode behaviour: coalesce concurrent reads, serve
 * repeats from cache, and drop everything the moment data actually changes.
 */
describe('getStudies read coalescing (live mode)', () => {
  const originalFetch = globalThis.fetch;
  let fetchSpy: ReturnType<typeof vi.fn>;

  const studies = [{ id: 'std_1', title: 'Alpha' }];

  const respondWithStudies = (payload: unknown = studies) => {
    fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
  };

  const studyRequests = () =>
    fetchSpy.mock.calls.filter(([url]) => String(url).includes('/studies')).length;

  beforeEach(() => {
    api.setMockMode(false);
    localStorage.clear();
    // The cache is module state with a 2s TTL and these tests run in
    // milliseconds — without an explicit drop, one test is served the
    // previous test's entry.
    api.setStoredUser(null);
    respondWithStudies();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    api.setMockMode(true);
    localStorage.clear();
  });

  it('issues one request for concurrent callers', async () => {
    const [a, b, c] = await Promise.all([api.getStudies(), api.getStudies(), api.getStudies()]);

    expect(studyRequests()).toBe(1);
    expect(a).toEqual(studies);
    expect(b).toEqual(studies);
    expect(c).toEqual(studies);
  });

  it('serves a sequential repeat from cache instead of refetching', async () => {
    await api.getStudies();
    await api.getStudies();

    // The regression this guards: the read persisted its own result through the
    // invalidating setter, so the cache could never be populated in live mode.
    expect(studyRequests()).toBe(1);
  });

  it('refetches after a mutation invalidates the cache', async () => {
    await api.getStudies();
    api.saveStoredUserStudies([]);
    await api.getStudies();

    expect(studyRequests()).toBe(2);
  });

  it('never serves one account the previous account\u2019s studies', async () => {
    // Each identity gets a distinguishable payload: asserting only on the
    // request count would still pass if the cache key check were deleted,
    // because the invalidation in setStoredUser alone forces a refetch.
    fetchSpy = vi.fn().mockImplementation((url: string) => ({
      ok: true,
      status: 200,
      json: async () => (String(url).includes('usr_a') ? [{ id: 'a' }] : [{ id: 'b' }]),
    }));
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    api.setStoredUser({ id: 'usr_a', email: 'a@example.com' } as any);
    const first = await api.getStudies();

    api.setStoredUser({ id: 'usr_b', email: 'b@example.com' } as any);
    const second = await api.getStudies();

    expect(studyRequests()).toBe(2);
    expect(first).toEqual([{ id: 'a' }]);
    expect(second).toEqual([{ id: 'b' }]);
  });

  it('does not cache a failed read', async () => {
    fetchSpy = vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
    await expect(api.getStudies()).rejects.toThrow();

    // A rejection must clear the in-flight slot, or every later caller would
    // be handed the same failure for the rest of the session.
    respondWithStudies();
    await expect(api.getStudies()).resolves.toEqual(studies);
    expect(studyRequests()).toBe(1);
  });

  it('hands each consumer its own array', async () => {
    const a = await api.getStudies();
    const b = await api.getStudies();

    // Cache hits must not share one array: three dashboard views read this
    // within the TTL window and one in-place sort would corrupt the others.
    expect(a).not.toBe(b);
    expect(a).toEqual(b);
  });
});

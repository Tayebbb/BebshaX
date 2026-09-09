import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/services/api';
import type { Study } from '../src/types';

const setUser = (id: string): void => {
  api.setStoredUser({
    id,
    email: `e2e.${id}@example.test`,
    full_name: 'Cache isolation test',
    is_active: true,
    is_verified: true,
    auth_provider: 'email',
    created_at: '2026-09-09T00:00:00Z',
  });
};

const study = (id: string, owner?: string): Study => ({
  id,
  user_id: owner,
  title: id,
  type: 'interviews',
  status: 'draft',
  persona_count: 0,
  persona_ids: [],
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
});

describe('live study cache account isolation during outages', () => {
  beforeEach(async () => {
    localStorage.clear();
    api.setMockMode(true);
    await api.getHealth();
    api.setMockMode(false);
    setUser('new-account');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    api.setStoredUser(null);
    api.setMockMode(false);
    localStorage.clear();
  });

  it('returns no fixtures for a live cold cache even after the mock module loaded', async () => {
    api.setMockMode(true);
    await api.getHealth();
    api.setMockMode(false);

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([]);
  });

  it('only returns current-owner rows from a contaminated account bucket', async () => {
    const own = study('Own research', 'new-account');
    localStorage.setItem(api.getUserStudiesStorageKey(), JSON.stringify([
      study('Perfume research', 'previous-account'),
      study('UI Check', 'previous-account'),
      study('Unknown owner'),
      null,
      own,
    ]));

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([own]);
  });

  it('does not reuse a mock request cache after switching to live mode', async () => {
    api.setMockMode(true);
    expect((await api.getStudies()).length).toBeGreaterThan(0);
    api.setMockMode(false);

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([]);
  });

  it('retains a successfully fetched same-owner list during a later outage', async () => {
    const own = study('Own research', 'new-account');
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([own]), { status: 200 }));
    expect(await api.getStudies()).toEqual([own]);
    setUser('new-account');

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([own]);
  });

  it('returns an empty list for malformed live storage without loading fixtures', () => {
    localStorage.setItem(api.getUserStudiesStorageKey(), '{invalid');

    expect(api.getStoredUserStudies()).toEqual([]);
  });

  it('does not expose the anonymous default bucket after signout', () => {
    localStorage.setItem('bebshax_studies_default_user', JSON.stringify([
      study('Previous research', 'previous-account'),
    ]));
    api.setStoredUser(null);

    expect(api.getStoredUserStudies()).toEqual([]);
  });

  it('preserves another account cache without exposing it to the new account', async () => {
    setUser('previous-account');
    const own = study('Existing owner research', 'previous-account');
    api.saveStoredUserStudies([own]);
    const previousKey = api.getUserStudiesStorageKey();
    const previousValue = localStorage.getItem(previousKey);
    setUser('new-account');

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([]);
    expect(localStorage.getItem(previousKey)).toBe(previousValue);
    setUser('previous-account');
    expect(api.getStoredUserStudies()).toEqual([own]);
  });

  it('does not persist foreign or unowned studies in the current live bucket', () => {
    const own = study('Own research', 'new-account');
    api.saveStoredUserStudies([own, study('Foreign research', 'previous-account'), study('Unknown owner')]);

    expect(JSON.parse(localStorage.getItem(api.getUserStudiesStorageKey())!)).toEqual([own]);
  });

  it('does not write to an anonymous bucket in live mode', () => {
    api.setStoredUser(null);
    api.saveStoredUserStudies([study('Foreign research', 'previous-account')]);

    expect(localStorage.getItem('bebshax_studies_default_user')).toBeNull();
  });

  it('does not write an in-flight previous-account response into the new account cache', async () => {
    setUser('previous-account');
    let resolveFetch!: (response: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve; })));
    const pending = api.getStudies();
    setUser('new-account');
    resolveFetch(new Response(JSON.stringify([study('Previous research', 'previous-account')]), { status: 200 }));
    await pending;

    expect(api.getStoredUserStudies()).toEqual([]);
    expect(localStorage.getItem(api.getUserStudiesStorageKey())).toBeNull();
  });
});
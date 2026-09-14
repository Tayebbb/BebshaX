import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, SIGNOUT_BROADCAST_KEY } from '../src/services/api';
import { AuthProvider, useAuth } from '../src/context/AuthContext';
import { neonAuth } from '../src/services/neonAuth';
import { getRefreshCredential } from '../src/services/session';
import type { User } from '../src/types/auth';

const currentUser: User = {
  id: 'session-current', email: 'current@example.test', full_name: 'Current researcher',
  is_active: true, is_verified: true, auth_provider: 'email', created_at: '2026-09-09T00:00:00Z',
};
const otherUser = { ...currentUser, id: 'session-other', full_name: 'Other researcher' };
function SessionProbe() {
  const { user, isLoading } = useAuth();
  return <output>{isLoading ? 'Checking' : user?.full_name ?? 'Signed out'}</output>;
}

describe('Frontend authoritative session boundary', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(false);
    api.setAuthToken(null);
    api.setStoredUser(null);
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.setAuthToken(null);
    api.setStoredUser(null);
    api.setMockMode(true);
    window.history.replaceState({}, '', '/');
  });

  it('never replaces a session from URL bearer parameters and keeps safe return parameters', async () => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(currentUser)));
    window.history.replaceState({}, '', '/auth/signin?token=attacker-fixture&access_token=another-fixture&next=%2Fresearch%2Fstudy-a%2Fstep3');
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Current researcher');
    expect(api.getAuthToken()).toBe('current-fixture-token');
    expect(new URLSearchParams(window.location.search).get('next')).toBe('/research/study-a/step3');
    expect(window.location.search).not.toContain('token=');
  });

  it('does not replace the new identity with a late profile from the previous token', async () => {
    let resolveProfile!: (response: Response) => void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise((resolve) => { resolveProfile = resolve; }));
    api.setAuthToken('previous-fixture-token');
    api.setStoredUser(currentUser);
    const request = api.getMe();
    api.setAuthToken('new-fixture-token');
    api.setStoredUser(otherUser);
    resolveProfile(new Response(JSON.stringify(currentUser)));
    await request.catch(() => null);
    expect(api.getStoredUser()).toEqual(otherUser);
    expect(api.getAuthToken()).toBe('new-fixture-token');
  });

  it.each([500, 503])('does not authorize a cached identity when profile verification returns %s', async (status) => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Session verification unavailable' }), { status }));

    await expect(api.getMe()).rejects.toMatchObject({ status });
    expect(api.getAuthToken()).toBe('current-fixture-token');
  });

  it('does not authorize a cached identity when profile verification loses its connection', async () => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Connection unavailable'));

    await expect(api.getMe()).rejects.toThrow('Connection unavailable');
    expect(api.getAuthToken()).toBe('current-fixture-token');
  });

  it('rejects a malformed server profile without replacing the stored identity', async () => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ id: 'incomplete-profile' })));

    await expect(api.getMe()).rejects.toThrow(/Invalid.*profile/i);
    expect(api.getStoredUser()).toEqual(currentUser);
  });

  it('invalidates the visible identity on a cross-tab logout', async () => {
    api.setMockMode(true);
    api.setAuthToken('mock-fixture-token');
    api.setStoredUser(currentUser);
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Current researcher');
    act(() => {
      localStorage.removeItem('bebshax_auth_token');
      localStorage.removeItem('bebshax_auth_user');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_auth_token', newValue: null }));
    });
    await screen.findByText('Signed out');
  });

  it('sends reset-purpose OTP requests to the local password authority', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Code requested' })));
    await api.sendOtp('current@example.test', 'forget-password');
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/forgot-password$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ email: 'current@example.test', purpose: 'forget-password' }),
    }));
  });

  it('resets the local password without calling the Neon password authority', async () => {
    const neonReset = vi.spyOn(neonAuth, 'resetPasswordWithOtp');
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Password reset' })));
    await api.resetPasswordWithOtp('current@example.test', '123456', 'FixturePassword123');
    expect(neonReset).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/reset-password$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ email: 'current@example.test', otp: '123456', password: 'FixturePassword123', purpose: 'forget-password' }),
    }));
  });

  it('requires an acknowledged verification response instead of fabricating a verified user', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid or expired verification code' }), { status: 400 }));
    await expect(api.verifyEmailOtp('current@example.test', '123456')).rejects.toThrow(/Invalid or expired verification code/);
    expect(api.getStoredUser()).toBeNull();
  });

  it('revokes the server session before reporting logout success and removes private snapshots', async () => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    localStorage.setItem('bebshax_studies_live_session-current', '[{"private":"fixture"}]');
    const neonLogout = vi.spyOn(neonAuth, 'signOut').mockResolvedValue(undefined);
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Signed out' })));
    await api.signout();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/logout$/), expect.objectContaining({ method: 'POST' }));
    expect(neonLogout).not.toHaveBeenCalled();
    expect(api.getAuthToken()).toBeNull();
    expect(localStorage.getItem('bebshax_studies_live_session-current')).toBeNull();
  });

  it('does not wait on Neon for an anonymous public page', async () => {
    const neonSession = vi.spyOn(neonAuth, 'getSession').mockImplementation(() => new Promise(() => {}));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await waitFor(() => expect(screen.getByText('Signed out')).toBeInTheDocument());
    expect(neonSession).not.toHaveBeenCalled();
  });

  it('keeps cookie credentials out of browser storage and sends session-bound CSRF on logout', async () => {
    const csrf = 'c'.repeat(64);
    api.acceptAuthResponse({ access_token: '', csrf_token: csrf, token_type: 'bearer', expires_in_days: 0.01, user: currentUser });
    expect(api.hasSession()).toBe(true);
    expect(api.getAuthToken()).toBeNull();
    expect(localStorage.getItem('bebshax_auth_token')).toBeNull();
    expect(sessionStorage.getItem('bebshax_auth_token')).toBeNull();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Signed out' })));
    await api.signout();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/logout$/), expect.objectContaining({
      credentials: 'include', headers: expect.objectContaining({ 'X-CSRF-Token': csrf, 'X-Auth-Transport': 'cookie' }),
    }));
    expect(api.hasSession()).toBe(false);
  });

  it('bootstraps and rotates an expired cookie session once using the latest CSRF token', async () => {
    const csrf = 'a'.repeat(64);
    const rotated = 'b'.repeat(64);
    api.acceptAuthResponse({ access_token: '', csrf_token: csrf, token_type: 'bearer', expires_in_days: 0.01, user: currentUser });
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: currentUser, csrf_token: csrf, needs_refresh: true })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: currentUser, access_token: '', csrf_token: rotated, token_type: 'bearer', expires_in_days: 0.01 })));
    const [first, second] = await Promise.all([api.getMe(), api.getMe()]);
    expect(first).toEqual(currentUser);
    expect(second).toEqual(currentUser);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith(expect.stringMatching(/\/auth\/refresh$/), expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': csrf }),
    }));
    expect(api.getAuthHeaders()['X-CSRF-Token']).toBe(rotated);
    api.clearSession();
  });

  it('reports failed server revocation while clearing the local private session', async () => {
    api.setAuthToken('current-fixture-token');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Revocation unavailable' }), { status: 503 }));
    await expect(api.signout()).rejects.toMatchObject({ status: 503 });
    expect(api.getAuthToken()).toBeNull();
    expect(api.getStoredUser()).toBeNull();
  });

  it('rejects a wrong-state OAuth return before consulting the federation provider', async () => {
    const neonSession = vi.spyOn(neonAuth, 'getSession');
    sessionStorage.setItem('bebshax_oauth_state', 'expected-fixture-state');
    window.history.replaceState({}, '', '/app?oauth_state=wrong-fixture-state');
    await expect(api.completeOAuthReturn()).rejects.toThrow(/Invalid or already used/);
    expect(neonSession).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('bebshax_oauth_state')).toBeNull();
    expect(window.location.search).not.toContain('oauth_state');
  });

  it('clears tab-scoped bearer credentials after a cross-tab logout broadcast', async () => {
    api.setAuthToken('tab-local-fixture');
    api.setStoredUser(currentUser);
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(currentUser)));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Current researcher');
    act(() => {
      localStorage.setItem(SIGNOUT_BROADCAST_KEY, '1789240000000');
      window.dispatchEvent(new StorageEvent('storage', { key: SIGNOUT_BROADCAST_KEY, newValue: '1789240000000' }));
      localStorage.removeItem('bebshax_auth_user');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_auth_user', newValue: null }));
    });
    await screen.findByText('Signed out');
    expect(api.getAuthToken()).toBeNull();
  });

  it('invalidates old tab credentials on another tab account switch without erasing the new shared identity', async () => {
    api.acceptAuthResponse({ access_token: 'previous-tab-token', refresh_token: 'previous-tab-refresh', token_type: 'bearer', expires_in_days: 1, user: currentUser });
    vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify(currentUser)));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Current researcher');

    act(() => {
      localStorage.setItem('bebshax_auth_user', JSON.stringify(otherUser));
      localStorage.setItem('bebshax_session_generation', 'other-tab-generation');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_session_generation', newValue: 'other-tab-generation' }));
    });

    await screen.findByText('Signed out');
    expect(api.getAuthHeaders()).not.toHaveProperty('Authorization');
    expect(getRefreshCredential()).toBeNull();
    expect(api.getStoredUser()).toEqual(otherUser);
    expect(localStorage.getItem('bebshax_session_generation')).toBe('other-tab-generation');
  });

  it('does not coalesce cookie bootstrap requests across different session generations', async () => {
    let resolvePrevious!: (response: Response) => void;
    const csrf = 'a'.repeat(64);
    const currentCsrf = 'b'.repeat(64);
    api.acceptAuthResponse({ access_token: '', csrf_token: csrf, token_type: 'bearer', expires_in_days: 1, user: currentUser });
    vi.mocked(fetch)
      .mockReturnValueOnce(new Promise((resolve) => { resolvePrevious = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: otherUser, csrf_token: currentCsrf, needs_refresh: false })));
    const previous = api.getMe().catch((error: unknown) => error);

    api.acceptAuthResponse({ access_token: '', csrf_token: currentCsrf, token_type: 'bearer', expires_in_days: 1, user: otherUser });
    const current = api.getMe().then((value) => ({ value }), (error: unknown) => ({ error }));
    resolvePrevious(new Response(JSON.stringify({ user: currentUser, csrf_token: csrf, needs_refresh: false })));

    await expect(current).resolves.toEqual({ value: otherUser });
    await expect(previous).resolves.toMatchObject({ name: 'AbortError' });
    expect(api.getStoredUser()).toEqual(otherUser);
    expect(api.getAuthHeaders()['X-CSRF-Token']).toBe(currentCsrf);
    api.clearSession();
  });

  it('recovers an expired bearer session using its server-issued refresh credential', async () => {
    const refresh = `${'a'.repeat(32)}.${'b'.repeat(43)}`;
    const expired = `fixture.${btoa(JSON.stringify({ exp: 1 }))}.fixture`;
    api.acceptAuthResponse({ access_token: expired, refresh_token: refresh, token_type: 'bearer', expires_in_days: 0, user: currentUser });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'renewed-fixture-token', refresh_token: refresh, token_type: 'bearer', expires_in_days: 1, user: currentUser })));

    await expect(api.getMe()).resolves.toEqual(currentUser);
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/refresh$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ refresh_token: refresh }),
    }));
    expect(api.getAuthToken()).toBe('renewed-fixture-token');
  });

  it('coalesces concurrent expired-bearer recovery into one token rotation', async () => {
    const refresh = `${'a'.repeat(32)}.${'b'.repeat(43)}`;
    const expired = `fixture.${btoa(JSON.stringify({ exp: 1 }))}.fixture`;
    api.acceptAuthResponse({ access_token: expired, refresh_token: refresh, token_type: 'bearer', expires_in_days: 0, user: currentUser });
    let finishRefresh!: () => void;
    const pending = new Promise<void>((resolve) => { finishRefresh = resolve; });
    vi.mocked(fetch).mockImplementation(async () => {
      await pending;
      return new Response(JSON.stringify({ access_token: 'renewed-fixture-token', refresh_token: refresh, token_type: 'bearer', expires_in_days: 1, user: currentUser }));
    });

    const results = Promise.allSettled([api.getMe(), api.getMe()]);
    finishRefresh();

    await expect(results).resolves.toEqual([
      { status: 'fulfilled', value: currentUser }, { status: 'fulfilled', value: currentUser },
    ]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('revokes an expired bearer session with the refresh credential and clears local state', async () => {
    const refresh = `${'a'.repeat(32)}.${'b'.repeat(43)}`;
    const expired = `fixture.${btoa(JSON.stringify({ exp: 1 }))}.fixture`;
    api.acceptAuthResponse({ access_token: expired, refresh_token: refresh, token_type: 'bearer', expires_in_days: 0, user: currentUser });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Signed out' })));

    await api.signout();
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/logout$/), expect.objectContaining({
      method: 'POST', body: JSON.stringify({ refresh_token: refresh }),
    }));
    expect(api.hasSession()).toBe(false);
    expect(getRefreshCredential()).toBeNull();
  });

  it('reports unavailable refresh without silently treating it as an absent session', async () => {
    api.acceptAuthResponse({ access_token: 'current-fixture-token', token_type: 'bearer', expires_in_days: 1, user: currentUser });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Refresh unavailable' }), { status: 503 }));

    await expect(api.refreshToken()).rejects.toMatchObject({ status: 503 });
    expect(api.getAuthToken()).toBe('current-fixture-token');
  });

  it('rejects incomplete cookie profiles without authorizing or caching them', async () => {
    const csrf = 'a'.repeat(64);
    api.acceptAuthResponse({ access_token: '', csrf_token: csrf, token_type: 'bearer', expires_in_days: 1, user: currentUser });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ user: { id: 'incomplete-profile' }, csrf_token: csrf, needs_refresh: false })));

    await expect(api.getMe()).rejects.toThrow(/Invalid.*profile/i);
    expect(api.getStoredUser()).toEqual(currentUser);
    api.clearSession();
  });
});
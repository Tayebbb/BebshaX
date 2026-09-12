import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, SIGNOUT_BROADCAST_KEY } from '../src/services/api';
import { AuthProvider, useAuth } from '../src/context/AuthContext';
import { getRefreshCredential, getSessionEpoch } from '../src/services/session';
import type { User } from '../src/types/auth';

const user: User = {
  id: 'replay-user', email: 'replay@example.test', full_name: 'Replay researcher',
  is_active: true, is_verified: true, auth_provider: 'email', created_at: '2026-09-09T00:00:00Z',
};
const refresh = `${'c'.repeat(32)}.${'d'.repeat(43)}`;
const expiredToken = `fixture.${btoa(JSON.stringify({ exp: 1 }))}.fixture`;
const liveToken = (seconds: number) => `fixture.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + seconds }))}.fixture`;
const renewed = () => new Response(JSON.stringify({
  access_token: 'renewed-fixture-token', refresh_token: refresh, token_type: 'bearer', expires_in: 900, expires_in_days: 0.01, user,
}));
const requestUrl = (call: unknown[]) => String(call[0]);
const requestHeaders = (call: unknown[]) => ((call[1] as RequestInit | undefined)?.headers ?? {}) as Record<string, string>;

function SessionProbe() {
  const { user, isLoading } = useAuth();
  return <output>{isLoading ? 'Checking' : user?.full_name ?? 'Signed out'}</output>;
}

describe('Session refresh replay', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(false);
    api.setAuthToken(null);
    api.setStoredUser(null);
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.clearSession();
    api.setMockMode(true);
  });

  it('replays a data request once after a 401 by rotating the bearer session', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Invalid or expired authentication token' }), { status: 401 }))
      .mockResolvedValueOnce(renewed())
      .mockResolvedValueOnce(new Response(JSON.stringify([])));

    await expect(api.getStudies()).resolves.toEqual([]);

    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.map(requestUrl)).toEqual([
      expect.stringMatching(/\/studies/), expect.stringMatching(/\/auth\/refresh$/), expect.stringMatching(/\/studies/),
    ]);
    expect(requestHeaders(calls[2]).Authorization).toBe('Bearer renewed-fixture-token');
    expect(api.getAuthToken()).toBe('renewed-fixture-token');
  });

  it('ends the session as a boundary change when the refresh credential is rejected', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    vi.mocked(fetch)
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Invalid or expired authentication token' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Invalid or expired refresh token' }), { status: 401 }));

    // The caller sees the same session-changed abort as any other sign-out, never a fabricated result.
    await expect(api.getStudies()).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.hasSession()).toBe(false);
    expect(getRefreshCredential()).toBeNull();
  });

  it('rotates before sending when the access token already expired, so owner-scoped writes never go out anonymous', async () => {
    api.acceptAuthResponse({ access_token: expiredToken, refresh_token: refresh, token_type: 'bearer', expires_in_days: 0, user });
    const epoch = getSessionEpoch();
    vi.mocked(fetch)
      .mockResolvedValueOnce(renewed())
      .mockResolvedValueOnce(new Response(JSON.stringify([])));

    await expect(api.getStudies()).resolves.toEqual([]);

    const calls = vi.mocked(fetch).mock.calls;
    expect(calls.map(requestUrl)).toEqual([expect.stringMatching(/\/auth\/refresh$/), expect.stringMatching(/\/studies/)]);
    expect(requestHeaders(calls[1]).Authorization).toBe('Bearer renewed-fixture-token');
    // Same user: the rotation must not tear down the dashboard (session epoch).
    expect(getSessionEpoch()).toBe(epoch);
  });

  it('never replays authentication endpoints', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'Invalid or expired refresh token' }), { status: 401 }));

    await expect(api.refreshToken()).resolves.toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('keeps the session epoch stable across a same-user rotation so in-flight work survives', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    const epoch = getSessionEpoch();
    const generation = localStorage.getItem('bebshax_session_generation');
    vi.mocked(fetch).mockResolvedValueOnce(renewed());

    await expect(api.refreshToken()).resolves.toMatchObject({ access_token: 'renewed-fixture-token' });

    expect(getSessionEpoch()).toBe(epoch);
    expect(localStorage.getItem('bebshax_session_generation')).toBe(generation);
    expect(api.getAuthToken()).toBe('renewed-fixture-token');
  });

  it('still resets the session when a different account signs in', () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    const epoch = getSessionEpoch();

    api.acceptAuthResponse({
      access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01,
      user: { ...user, id: 'another-account' },
    });

    expect(getSessionEpoch()).toBeGreaterThan(epoch);
  });

  it('persists the refresh credential for this tab and recovers an expired token after a reload', async () => {
    api.acceptAuthResponse({ access_token: expiredToken, refresh_token: refresh, token_type: 'bearer', expires_in_days: 0, user });
    expect(sessionStorage.getItem('bebshax_refresh_token')).toBe(refresh);
    vi.mocked(fetch).mockResolvedValueOnce(renewed());

    await expect(api.getMe()).resolves.toEqual(user);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(requestUrl(vi.mocked(fetch).mock.calls[0])).toMatch(/\/auth\/refresh$/);
    expect(api.getAuthToken()).toBe('renewed-fixture-token');
  });

  it('rotates proactively one minute before the access credential expires', async () => {
    vi.useFakeTimers();
    api.acceptAuthResponse({ access_token: liveToken(120), refresh_token: refresh, token_type: 'bearer', expires_in: 120, expires_in_days: 0.01, user });
    vi.mocked(fetch).mockResolvedValueOnce(renewed());

    await vi.advanceTimersByTimeAsync(59_000);
    expect(fetch).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2_000);

    expect(fetch).toHaveBeenCalledTimes(1);
    expect(requestUrl(vi.mocked(fetch).mock.calls[0])).toMatch(/\/auth\/refresh$/);
    expect(api.getAuthToken()).toBe('renewed-fixture-token');
  });

  it('cancels the proactive rotation on sign-out', async () => {
    vi.useFakeTimers();
    api.acceptAuthResponse({ access_token: liveToken(120), refresh_token: refresh, token_type: 'bearer', expires_in: 120, expires_in_days: 0.01, user });
    api.clearSession();

    await vi.advanceTimersByTimeAsync(130_000);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('keeps this tab signed in when the same account signs in from another tab', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(user)));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Replay researcher');
    const epoch = getSessionEpoch();

    act(() => {
      localStorage.setItem('bebshax_auth_user', JSON.stringify({ ...user, updated_at: '2026-09-12T12:00:00Z' }));
      localStorage.setItem('bebshax_session_generation', 'second-tab-generation');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_session_generation', newValue: 'second-tab-generation' }));
    });

    expect(screen.getByRole('status').textContent).toBe('Replay researcher');
    expect(api.getAuthToken()).not.toBeNull();
    expect(getRefreshCredential()).toBe(refresh);
    expect(getSessionEpoch()).toBe(epoch);
  });

  it('still signs this tab out when another tab signs out deliberately', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(user)));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Replay researcher');

    act(() => {
      // api.signout() in the other tab: broadcast first, then its own cleanup.
      localStorage.setItem(SIGNOUT_BROADCAST_KEY, '1789240000000');
      window.dispatchEvent(new StorageEvent('storage', { key: SIGNOUT_BROADCAST_KEY, newValue: '1789240000000' }));
      localStorage.removeItem('bebshax_auth_user');
      localStorage.removeItem('bebshax_session_generation');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_auth_user', newValue: null }));
    });

    await screen.findByText('Signed out');
    expect(api.getAuthToken()).toBeNull();
    expect(getRefreshCredential()).toBeNull();
  });

  it('keeps a valid tab-scoped session when another tab merely loses its own', async () => {
    api.acceptAuthResponse({ access_token: liveToken(600), refresh_token: refresh, token_type: 'bearer', expires_in: 600, expires_in_days: 0.01, user });
    // A fresh Response per call: the re-verification must not read an already-consumed body.
    vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify(user)));
    render(<AuthProvider><SessionProbe /></AuthProvider>);
    await screen.findByText('Replay researcher');
    const token = api.getAuthToken();
    vi.mocked(fetch).mockClear();

    act(() => {
      // The other tab's access expired and its refresh was rejected: it cleared the shared identity.
      localStorage.removeItem('bebshax_auth_user');
      localStorage.removeItem('bebshax_session_generation');
      window.dispatchEvent(new StorageEvent('storage', { key: 'bebshax_auth_user', newValue: null }));
    });

    // This tab re-verifies its own credentials with the server instead of dropping them.
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/me$/), expect.anything()));
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe('Replay researcher'));
    expect(api.getAuthToken()).toBe(token);
    expect(getRefreshCredential()).toBe(refresh);
    expect(api.getStoredUser()?.id).toBe(user.id);
  });
});

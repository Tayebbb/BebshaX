import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { api } from '../src/services/api';

/** Blocker 2: in live mode a non-ok backend response must surface as an error.
 * It once fell through to the mock branch and minted `mock_jwt_<timestamp>`
 * plus a fabricated stored user — a 500 silently "logged the user in". */
describe('Blocker 2 — live auth never fabricates a session', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    api.setMockMode(false);
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    api.setMockMode(true);
  });

  const respondWith = (status: number) => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status,
      json: async () => ({ detail: 'Internal Server Error' }),
    }) as unknown as typeof fetch;
  };

  it.each([500, 429, 404])('throws on HTTP %i during signin and stores nothing', async (status) => {
    respondWith(status);

    await expect(api.signin({ email: 'a@b.io', password: 'Password123' })).rejects.toThrow();

    expect(api.getAuthToken()).toBeNull();
    expect(api.getStoredUser()).toBeNull();
    expect(localStorage.getItem('bebshax_auth_token')).toBeNull();
  });

  it('still reports invalid credentials on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid email or password.' }),
    }) as unknown as typeof fetch;

    await expect(api.signin({ email: 'a@b.io', password: 'nope' })).rejects.toThrow(
      /Invalid email or password/i
    );
    expect(api.getAuthToken()).toBeNull();
  });

  it('throws on a failed signup instead of returning a mock account', async () => {
    respondWith(500);

    await expect(
      api.signup({ full_name: 'A B', email: 'a@b.io', password: 'Password123' })
    ).rejects.toThrow();
  });

  it('returns the real session on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: 'real_token',
        token_type: 'bearer',
        expires_in_days: 7,
        user: {
          id: 'usr_1',
          email: 'a@b.io',
          full_name: 'A B',
          avatar_url: null,
          is_active: true,
          is_verified: true,
          auth_provider: 'email',
          created_at: new Date().toISOString(),
        },
      }),
    }) as unknown as typeof fetch;

    const res = await api.signin({ email: 'a@b.io', password: 'Password123' });

    expect(res.access_token).toBe('real_token');
    expect(api.getAuthToken()).toBe('real_token');
  });
});

/** Fix 1 (round 5): the backend's OTP user-binding gate only engages when the
 * email is posted alongside the token — the client used to drop it. */
describe('verify-email posts the email with the OTP so the binding gate engages', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    api.setMockMode(false);
    localStorage.clear();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    api.setMockMode(true);
  });

  it('includes both token and email in the verify-email body', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    await api.verifyEmailOtp('user@example.com', ' 123456 ');

    const call = fetchSpy.mock.calls.find(([url]) => String(url).includes('/auth/verify-email'));
    expect(call).toBeDefined();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body).toEqual({ token: '123456', email: 'user@example.com' });
  });

  it('omits the email key entirely when no email is available', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    await api.verifyEmailOtp('   ', '654321');

    const call = fetchSpy.mock.calls.find(([url]) => String(url).includes('/auth/verify-email'));
    expect(call).toBeDefined();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body).toEqual({ token: '654321' });
    expect('email' in body).toBe(false);
  });
});

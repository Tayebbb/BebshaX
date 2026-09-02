import { describe, it, expect, vi, beforeEach } from 'vitest';
import { neonAuth, NEON_AUTH_URL } from '../src/services/neonAuth';

describe('Neon Auth Client & Service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reads the Neon Auth URL from the environment with no hardcoded tenant fallback', async () => {
    expect(neonAuth.getAuthUrl()).toBe(NEON_AUTH_URL);

    vi.resetModules();
    vi.stubEnv('VITE_NEON_AUTH_URL', 'https://auth.example.test/neondb/auth');
    const configured = await import('../src/services/neonAuth');
    expect(configured.NEON_AUTH_URL).toBe('https://auth.example.test/neondb/auth');
    expect(configured.isNeonAuthConfigured()).toBe(true);

    // Absent/empty env ⇒ '' ⇒ federated sign-in disabled — never a default tenant URL.
    vi.resetModules();
    vi.stubEnv('VITE_NEON_AUTH_URL', '');
    const unconfigured = await import('../src/services/neonAuth');
    expect(unconfigured.NEON_AUTH_URL).toBe('');
    expect(unconfigured.isNeonAuthConfigured()).toBe(false);

    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('handles sign-up successfully and maps user profile', async () => {
    const mockNeonUser = {
      id: 'usr_neon_123',
      name: 'Sarah Chen',
      email: 'sarah.chen@example.com',
      emailVerified: true,
      createdAt: '2026-08-24T12:00:00.000Z',
      updatedAt: '2026-08-24T12:00:00.000Z',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        token: 'neon_jwt_token_sample',
        user: mockNeonUser,
      }),
    });

    const res = await neonAuth.signUp({
      email: 'sarah.chen@example.com',
      password: 'StrongPassword123!',
      name: 'Sarah Chen',
    });

    expect(res.user.id).toBe('usr_neon_123');
    expect(res.user.full_name).toBe('Sarah Chen');
    expect(res.user.email).toBe('sarah.chen@example.com');
    expect(res.token).toBe('neon_jwt_token_sample');
    expect(res.emailVerificationRequired).toBe(false);
  });

  it('handles email verification requirement upon sign-in failure', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        code: 'EMAIL_NOT_VERIFIED',
        message: 'Email not verified',
      }),
    });

    await expect(
      neonAuth.signIn({
        email: 'unverified@example.com',
        password: 'Password123!',
      })
    ).rejects.toThrow(/Email not verified/);
  });

  it('handles invalid credentials upon sign-in failure', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        code: 'INVALID_EMAIL_OR_PASSWORD',
        message: 'Invalid email or password',
      }),
    });

    await expect(
      neonAuth.signIn({
        email: 'wrong@example.com',
        password: 'WrongPassword!',
      })
    ).rejects.toThrow(/Invalid email or password/);
  });

  it('sends verification email successfully', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: true }),
    });

    const sent = await neonAuth.sendVerificationEmail('sarah@example.com');
    expect(sent).toBe(true);
  });

  it('sends verification OTP successfully', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: true }),
    });

    const sent = await neonAuth.sendVerificationOtp('sarah@example.com', 'email-verification');
    expect(sent).toBe(true);
  });

  it('verifies email OTP code and returns authenticated session', async () => {
    const mockNeonUser = {
      id: 'usr_neon_verified',
      name: 'Sarah Chen',
      email: 'sarah.chen@example.com',
      emailVerified: true,
      createdAt: '2026-08-24T12:00:00.000Z',
      updatedAt: '2026-08-24T12:00:00.000Z',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        token: 'neon_verified_jwt',
        user: mockNeonUser,
      }),
    });

    const res = await neonAuth.verifyEmailOtp({
      email: 'sarah.chen@example.com',
      otp: '123456',
    });

    expect(res.user.email).toBe('sarah.chen@example.com');
    expect(res.user.is_verified).toBe(true);
    expect(res.token).toBe('neon_verified_jwt');
  });

  it('resets password with OTP code', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });

    const success = await neonAuth.resetPasswordWithOtp({
      email: 'sarah.chen@example.com',
      otp: '123456',
      password: 'NewStrongPassword123!',
    });

    expect(success).toBe(true);
  });

  it('retrieves active session if token or cookie is valid', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        user: {
          id: 'usr_neon_active',
          name: 'Active User',
          email: 'active@example.com',
          emailVerified: true,
          createdAt: '2026-08-24T12:00:00.000Z',
          updatedAt: '2026-08-24T12:00:00.000Z',
        },
        session: { id: 'sess_123' },
      }),
    });

    const user = await neonAuth.getSession('token_123');
    expect(user).not.toBeNull();
    expect(user?.email).toBe('active@example.com');
    expect(user?.full_name).toBe('Active User');
  });
});

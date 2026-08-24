import { describe, it, expect, beforeEach, vi } from 'vitest';
import { api } from '../src/services/api';

describe('Shehab Track Audit Findings (B5, M7, H1, L7, L8, L9, L10)', () => {
  beforeEach(() => {
    localStorage.clear();
    api.resetMockStore();
    vi.restoreAllMocks();
  });

  it('B5 & M7: getMe() returns null and clears token if token is expired or invalid', async () => {
    // Construct an expired JWT (payload: {"exp": 1000})
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const payload = btoa(JSON.stringify({ sub: 'user_123', exp: Math.floor(Date.now() / 1000) - 3600 }));
    const signature = 'fake_sig';
    const expiredToken = `${header}.${payload}.${signature}`;

    localStorage.setItem('bebshax_auth_token', expiredToken);
    localStorage.setItem('bebshax_auth_user', JSON.stringify({ id: 'user_123', email: 'test@example.com' }));

    // getAuthToken should detect expired token and clear it
    const token = api.getAuthToken();
    expect(token).toBeNull();
    expect(localStorage.getItem('bebshax_auth_token')).toBeNull();
    expect(localStorage.getItem('bebshax_auth_user')).toBeNull();

    // getMe() should return null (never fake Sarah Chen!)
    const user = await api.getMe();
    expect(user).toBeNull();
  });

  it('L7: getAuthHeaders includes X-BebshaX-Mock: 1 when in mock mode', () => {
    const mockHeaders = api.getAuthHeaders();
    expect(mockHeaders['X-BebshaX-Mock']).toBe('1');
  });

  it('L9: resetMockStore resets modified mock state to fresh initial state', () => {
    api.resetMockStore();
    expect(api.getStoredUserStudies().length).toBeGreaterThan(0);
  });

  it('L10: honest empty arrays are returned rather than fallback mocks', async () => {
    // When studies in localStorage is an empty array [], it should return []
    api.saveStoredUserStudies([]);
    const studies = api.getStoredUserStudies();
    expect(Array.isArray(studies)).toBe(true);
    expect(studies.length).toBe(0);
  });

  it('H1: In live mode (mockMode disabled), network errors throw instead of serving fake mocks', async () => {
    // Disable mock mode
    api.setMockMode(false);

    // Mock fetch to simulate a live 500 error from backend
    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockRejectedValue(new Error('Network failure'));

    await expect(api.getPersonas()).rejects.toThrow('Network failure');

    // Restore
    global.fetch = originalFetch;
    api.setMockMode(true);
  });
});

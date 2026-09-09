import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import { neonAuth } from '../src/services/neonAuth';
import type { Study } from '../src/types';
import type { User } from '../src/types/auth';

const user: User = {
  id: 'cache-followup-owner',
  email: 'cache-followup@example.test',
  full_name: 'Cache followup',
  is_active: true,
  is_verified: true,
  auth_provider: 'email',
  created_at: '2026-09-09T00:00:00Z',
};

const study = (id: string, overrides: Partial<Study> = {}): Study => ({
  id,
  user_id: user.id,
  title: id,
  type: 'interviews',
  status: 'draft',
  persona_count: 0,
  persona_ids: [],
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
  ...overrides,
});

const renderDashboard = () => render(
  <NavigationProvider>
    <AuthProvider>
      <DashboardLayout />
    </AuthProvider>
  </NavigationProvider>,
);

describe('study persistence mode isolation and public examples', () => {
  beforeEach(() => {
    localStorage.clear();
    api.setMockMode(false);
    api.setStoredUser(user);
    window.history.pushState({}, '', '/create-study');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    vi.spyOn(neonAuth, 'getSession').mockResolvedValue(null);
    vi.spyOn(api, 'getMe').mockResolvedValue(user);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.setStoredUser(null);
    api.setMockMode(false);
    localStorage.clear();
  });

  it('does not read a persisted mock-created same-owner study during a live outage', async () => {
    api.setMockMode(true);
    const created = await api.createStudy({ id: 'mock-created', title: 'Mock-created research' });
    const mockKey = api.getUserStudiesStorageKey();
    const mockValue = localStorage.getItem(mockKey);
    expect(created.user_id).toBe(user.id);
    expect(created.is_demo).toBe(false);
    expect(JSON.parse(mockValue!)).toContainEqual(created);
    api.setMockMode(false);

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([]);
    expect(api.getUserStudiesStorageKey()).not.toBe(mockKey);
    expect(localStorage.getItem(mockKey)).toBe(mockValue);
  });

  it('preserves live owner persistence when mock creation occurs for the same account', async () => {
    const own = study('Real owned research');
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([own]), { status: 200 }));
    expect(await api.getStudies()).toEqual([own]);
    const liveKey = api.getUserStudiesStorageKey();
    const liveValue = localStorage.getItem(liveKey);
    api.setMockMode(true);
    await api.createStudy({ id: 'mock-created', title: 'Mock-created research' });
    api.setMockMode(false);

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([own]);
    expect(localStorage.getItem(liveKey)).toBe(liveValue);
  });

  it('retains ambiguous legacy storage without trusting an old mock-created owner row', async () => {
    const legacyKey = `bebshax_studies_${user.id}`;
    const legacyValue = JSON.stringify([study('Old mock creation', { is_demo: false })]);
    localStorage.setItem(legacyKey, legacyValue);

    await expect(api.getStudies()).rejects.toThrow('Failed to fetch');
    expect(api.getStoredUserStudies()).toEqual([]);
    expect(localStorage.getItem(legacyKey)).toBe(legacyValue);
  });

  it('exposes a successful public demo separately from owned recents and foreign private studies', async () => {
    const own = study('Own recent research');
    const foreign = study('Foreign private research', {
      user_id: 'another-owner', status: 'completed', step: 5, is_demo: false,
    });
    const publicDemo = study('Public finished example', {
      user_id: undefined, status: 'completed', step: 5, is_demo: true,
    });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([own, foreign, publicDemo]), { status: 200 }));

    renderDashboard();

    expect(await screen.findByRole('button', { name: 'Own recent research' })).toBeVisible();
    expect(await screen.findByRole('button', { name: 'See a finished example study' })).toBeVisible();
    expect(screen.queryByText('Foreign private research')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Public finished example' })).not.toBeInTheDocument();
    expect(api.getStoredUserStudies()).toEqual([own]);
  });

  it('does not expose an unmarked foreign completed study as an example', async () => {
    const own = study('Own recent research');
    const foreign = study('Foreign private research', {
      user_id: 'another-owner', status: 'completed', step: 5,
    });
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify([own, foreign]), { status: 200 }));

    renderDashboard();

    expect(await screen.findByRole('button', { name: 'Own recent research' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'See a finished example study' })).not.toBeInTheDocument();
    expect(screen.queryByText('Foreign private research')).not.toBeInTheDocument();
  });
});
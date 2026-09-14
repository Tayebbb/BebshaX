import { afterEach, beforeEach, describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from '../src/App';
import { api } from '../src/services/api';

describe('App Minimal Shell', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(true);
    api.setAuthToken(null);
    api.setStoredUser(null);
  });
  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('renders the landing with a single h1 and no hidden status chatter', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getAllByText(/BebshaX/i).length).toBeGreaterThan(0);
    });
    // The landing hero owns the page's single h1 (two h1s confused the outline).
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    // Live 2026-09-14: a visually-hidden "BebshaX / Synthetic Persona Research
    // Platform / Backend Status: ok" block was read out on every page.
    expect(screen.queryByText(/Backend Status:/i)).toBeNull();
  });

  it('sends a signed-out visit to an app URL to the sign-in route and keeps the destination', async () => {
    // Live 2026-09-14: /persona-library rendered the login form in place, so the
    // bookmark/back entry was an app URL that only ever showed a sign-in form.
    window.history.pushState({}, '', '/persona-library?persona=per_1');
    render(<App />);

    await screen.findByRole('heading', { name: 'Welcome back' });
    await waitFor(() => expect(window.location.pathname).toBe('/auth/signin'));
    expect(new URLSearchParams(window.location.search).get('next')).toBe('/persona-library?persona=per_1');
  });

  it('does not add a next parameter for the default app entry', async () => {
    window.history.pushState({}, '', '/app');
    render(<App />);

    await screen.findByRole('heading', { name: 'Welcome back' });
    await waitFor(() => expect(window.location.pathname).toBe('/auth/signin'));
    expect(window.location.search).toBe('');
  });
});

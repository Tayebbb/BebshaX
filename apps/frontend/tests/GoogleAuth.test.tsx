import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { AuthPage } from '../src/components/auth/AuthPage';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import { neonAuth } from '../src/services/neonAuth';

describe('Google Social Authentication & Dashboard Redirect', () => {
  beforeEach(() => {
    api.setMockMode(true);
    vi.restoreAllMocks();
  });

  const renderAuthPage = (initialMode: any = 'signin') => {
    return render(
      <NavigationProvider>
        <AuthProvider>
          <AuthPage initialMode={initialMode} />
        </AuthProvider>
      </NavigationProvider>
    );
  };

  it('initiates Google social sign in with /app callback URL', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        url: 'https://ep-cold-star-azazjakq.neonauth.c-3.ap-southeast-1.aws.neon.tech/neondb/auth/sign-in/social/init?token=test_token',
        redirect: true,
      }),
    });
    globalThis.fetch = fetchSpy;

    await neonAuth.signInWithGoogle();

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/sign-in/social'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"provider":"google"'),
      })
    );

    // Verify callback URL points to /app
    const requestBody = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(requestBody.callbackURL).toContain('/app');
  });

  it('authenticates and redirects to dashboard when clicking Continue with Google on Sign In', async () => {
    renderAuthPage('signin');

    const googleBtn = screen.getByRole('button', { name: /Continue with Google/i });
    expect(googleBtn).toBeInTheDocument();
    fireEvent.click(googleBtn);

    await waitFor(() => {
      expect(api.getAuthToken()).not.toBeNull();
      expect(api.getStoredUser()).not.toBeNull();
    });
  });

  it('authenticates and redirects to dashboard when clicking Continue with Google on Sign Up', async () => {
    renderAuthPage('signup');

    const googleBtn = screen.getByRole('button', { name: /Continue with Google/i });
    expect(googleBtn).toBeInTheDocument();
    fireEvent.click(googleBtn);

    await waitFor(() => {
      expect(api.getAuthToken()).not.toBeNull();
      expect(api.getStoredUser()).not.toBeNull();
    });
  });
});

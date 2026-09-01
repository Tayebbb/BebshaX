import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { AuthPage } from '../src/components/auth/AuthPage';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';

describe('AuthPage OTP Verification & Reset Flows', () => {
  beforeEach(() => {
    api.setMockMode(true);
    vi.restoreAllMocks();
  });

  const renderAuthPage = (initialMode: any = 'signup-email') => {
    return render(
      <NavigationProvider>
        <AuthProvider>
          <AuthPage initialMode={initialMode} />
        </AuthProvider>
      </NavigationProvider>
    );
  };

  it('associates each visible label with its input via htmlFor/id on the sign-in form', () => {
    renderAuthPage('signin');

    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('lets a user the backend already authenticated continue into the app after signup', async () => {
    renderAuthPage('signup-email');

    // Fill sign up form
    fireEvent.change(screen.getByPlaceholderText('John Doe'), {
      target: { value: 'Alex Founder' },
    });
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'alex@bebshax.io' },
    });
    fireEvent.change(screen.getByPlaceholderText('Create a password'), {
      target: { value: 'SuperSecret123!' },
    });

    const createBtn = screen.getByRole('button', { name: /Create account/i });
    fireEvent.click(createBtn);

    // Signup returned a session, so the user is routed into the app instead of
    // being trapped on an OTP screen with no way past it.
    await waitFor(() => {
      expect(window.location.pathname).toBe('/app');
    });
    expect(screen.queryByRole('heading', { name: /Enter verification code/i })).toBeNull();
  });

  it('still offers the 6-digit OTP screen when verification is opened directly', async () => {
    renderAuthPage('verify-otp');

    expect(screen.getByRole('heading', { name: /Enter verification code/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Verify & Continue/i })).toBeInTheDocument();

    // Enter 6 digit OTP
    const digit1 = screen.getByLabelText('Digit 1');
    fireEvent.change(digit1, { target: { value: '1' } });
    const digit2 = screen.getByLabelText('Digit 2');
    fireEvent.change(digit2, { target: { value: '2' } });
    const digit3 = screen.getByLabelText('Digit 3');
    fireEvent.change(digit3, { target: { value: '3' } });
    const digit4 = screen.getByLabelText('Digit 4');
    fireEvent.change(digit4, { target: { value: '4' } });
    const digit5 = screen.getByLabelText('Digit 5');
    fireEvent.change(digit5, { target: { value: '5' } });
    const digit6 = screen.getByLabelText('Digit 6');
    fireEvent.change(digit6, { target: { value: '6' } });

    const verifyBtn = screen.getByRole('button', { name: /Verify & Continue/i });
    expect(verifyBtn).not.toBeDisabled();
    fireEvent.click(verifyBtn);
  });

  it('shows OTP password reset form when requesting password reset', async () => {
    renderAuthPage('forgot-password');

    expect(screen.getByRole('heading', { name: /Reset password/i })).toBeInTheDocument();

    const emailInput = screen.getByPlaceholderText('you@example.com');
    fireEvent.change(emailInput, { target: { value: 'alex@bebshax.io' } });

    const sendBtn = screen.getByRole('button', { name: /Send reset code/i });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Set new password/i })).toBeInTheDocument();
      expect(screen.getByText(/6-digit reset code/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText('At least 8 characters')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Repeat new password')).toBeInTheDocument();
    });

    // Enter OTP and new password
    const digit1 = screen.getByLabelText('Digit 1');
    fireEvent.change(digit1, { target: { value: '9' } });
    const digit2 = screen.getByLabelText('Digit 2');
    fireEvent.change(digit2, { target: { value: '8' } });
    const digit3 = screen.getByLabelText('Digit 3');
    fireEvent.change(digit3, { target: { value: '7' } });
    const digit4 = screen.getByLabelText('Digit 4');
    fireEvent.change(digit4, { target: { value: '6' } });
    const digit5 = screen.getByLabelText('Digit 5');
    fireEvent.change(digit5, { target: { value: '5' } });
    const digit6 = screen.getByLabelText('Digit 6');
    fireEvent.change(digit6, { target: { value: '4' } });

    fireEvent.change(screen.getByPlaceholderText('At least 8 characters'), {
      target: { value: 'BrandNewPassword123!' },
    });
    fireEvent.change(screen.getByPlaceholderText('Repeat new password'), {
      target: { value: 'BrandNewPassword123!' },
    });

    const resetBtn = screen.getByRole('button', { name: /Reset Password & Sign In/i });
    expect(resetBtn).not.toBeDisabled();
    fireEvent.click(resetBtn);
  });

  it('associates the reset OTP group with its label and labels both eye toggles', async () => {
    renderAuthPage('forgot-password');

    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'alex@bebshax.io' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Send reset code/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Set new password/i })).toBeInTheDocument();
    });

    // The OTP digit group is announced via its "6-digit reset code" label
    const otpGroup = screen.getByRole('group', { name: /6-digit reset code/i });
    expect(otpGroup).toContainElement(screen.getByLabelText('Digit 1'));

    // Both password-visibility toggles have accessible names
    expect(screen.getByRole('button', { name: /Show new password/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Show password confirmation/i })).toBeInTheDocument();
  });
});

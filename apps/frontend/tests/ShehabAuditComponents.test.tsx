import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { AuthPage } from '../src/components/auth/AuthPage';
import { AuthModal } from '../src/components/auth/AuthModal';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';

const renderWithProviders = (ui: React.ReactElement) => {
  return render(
    <NavigationProvider>
      <AuthProvider>{ui}</AuthProvider>
    </NavigationProvider>
  );
};

describe('Shehab Audit Track UI Tests (L2, L5, L6, L11)', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, '', '/');
  });

  it('L2: AuthPage opens LegalModal for Terms of Service and Privacy Policy', () => {
    renderWithProviders(<AuthPage initialMode="signup-email" />);

    // Click Terms of Service
    const termsBtn = screen.getByRole('button', { name: /Terms of Service/i });
    expect(termsBtn).toBeInTheDocument();
    fireEvent.click(termsBtn);

    expect(screen.getByRole('heading', { name: /BebshaX Terms of Service/i })).toBeInTheDocument();
    expect(screen.getByText(/Legitimate Free-Tier & Zero API Budget Protocol/i)).toBeInTheDocument();

    // Close modal
    const closeBtn = screen.getByRole('button', { name: /I Understand/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole('heading', { name: /BebshaX Terms of Service/i })).not.toBeInTheDocument();

    // Click Privacy Policy
    const privacyBtn = screen.getByRole('button', { name: /Privacy Policy/i });
    fireEvent.click(privacyBtn);
    expect(screen.getByRole('heading', { name: /BebshaX Privacy Policy/i })).toBeInTheDocument();
  });

  it('L5: AuthPage inputs contain name and autoComplete attributes', () => {
    renderWithProviders(<AuthPage initialMode="signin" />);

    const emailInput = screen.getByPlaceholderText('you@example.com');
    expect(emailInput).toHaveAttribute('name', 'email');
    expect(emailInput).toHaveAttribute('autoComplete', 'email');

    const passwordInput = screen.getByPlaceholderText('Enter your password');
    expect(passwordInput).toHaveAttribute('name', 'password');
    expect(passwordInput).toHaveAttribute('autoComplete', 'current-password');
  });

  it('L6: AuthPage enforces alphanumeric password validation at signup', async () => {
    renderWithProviders(<AuthPage initialMode="signup-email" />);

    const nameInput = screen.getByPlaceholderText('John Doe');
    const emailInput = screen.getByPlaceholderText('you@example.com');
    const passwordInput = screen.getByPlaceholderText('Create a password');
    const submitBtn = screen.getByRole('button', { name: /Create account/i });

    // Enter non-alphanumeric password (e.g. only letters "passwordonly" or only numbers "12345678")
    fireEvent.change(nameInput, { target: { value: 'Jane Doe' } });
    fireEvent.change(emailInput, { target: { value: 'jane@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'passwordonly' } });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Password must contain at least one letter and one number/i)).toBeInTheDocument();
  });

  it('L2 & L5: AuthModal contains legal triggers and autocomplete attributes', () => {
    renderWithProviders(
      <AuthModal isOpen={true} onClose={() => {}} initialView="signup-email" />
    );

    const fullNameInput = screen.getByPlaceholderText('John Doe');
    expect(fullNameInput).toHaveAttribute('name', 'fullName');
    expect(fullNameInput).toHaveAttribute('autoComplete', 'name');

    const emailInput = screen.getByPlaceholderText('you@example.com');
    expect(emailInput).toHaveAttribute('name', 'email');
    expect(emailInput).toHaveAttribute('autoComplete', 'email');

    const passwordInput = screen.getByPlaceholderText('Create a password');
    expect(passwordInput).toHaveAttribute('name', 'password');
    expect(passwordInput).toHaveAttribute('autoComplete', 'new-password');

    // Terms button opens modal
    const termsBtn = screen.getByRole('button', { name: /Terms of Service/i });
    fireEvent.click(termsBtn);
    expect(screen.getByRole('heading', { name: /BebshaX Terms of Service/i })).toBeInTheDocument();
  });
});

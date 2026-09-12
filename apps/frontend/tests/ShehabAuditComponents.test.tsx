import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { AuthPage } from '../src/components/auth/AuthPage';
import { AuthModal } from '../src/components/auth/AuthModal';
import { LegalModal } from '../src/components/auth/LegalModal';
import { Footer } from '../src/components/landing/Footer';
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

  describe.each(['AuthPage', 'Footer'] as const)('%s legal dialog', (source) => {
    it.each(['Terms of Service', 'Privacy Policy'])(
      'labels %s, contains keyboard focus, closes on Escape and restores the opener',
      async (label) => {
        renderWithProviders(source === 'AuthPage' ? <AuthPage initialMode="signup-email" /> : <Footer />);
        const opener = screen.getByRole('button', { name: label });
        opener.focus();
        fireEvent.click(opener);

        const dialog = screen.getByRole('dialog', { name: `BebshaX ${label}` });
        expect(screen.getAllByRole('dialog')).toHaveLength(1);
        expect(dialog).toHaveAttribute('aria-modal', 'true');
        const close = within(dialog).getByRole('button', { name: 'Close' });
        const acknowledge = within(dialog).getByRole('button', { name: 'I Understand' });
        await waitFor(() => expect(close).toHaveFocus());

        fireEvent.keyDown(close, { key: 'Tab', shiftKey: true });
        expect(acknowledge).toHaveFocus();
        fireEvent.keyDown(acknowledge, { key: 'Tab' });
        expect(close).toHaveFocus();
        fireEvent.keyDown(close, { key: 'Escape' });

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(opener).toHaveFocus();
      },
    );
  });

  describe('LegalModal owns its behavior without a caller wrapper', () => {
    function LegalHarness() {
      const [isOpen, setIsOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setIsOpen(true)}>Open privacy</button>
          <LegalModal isOpen={isOpen} onClose={() => setIsOpen(false)} type="privacy" />
        </>
      );
    }

    it.each(['close', 'acknowledge', 'backdrop'] as const)('restores focus after %s dismissal', async (method) => {
      render(<LegalHarness />);
      const opener = screen.getByRole('button', { name: 'Open privacy' });
      opener.focus();
      fireEvent.click(opener);
      const dialog = screen.getByRole('dialog');
      const close = within(dialog).getByRole('button', { name: 'Close' });
      await waitFor(() => expect(close).toHaveFocus());
      fireEvent.click(within(dialog).getByRole('heading'));
      expect(dialog).toBeInTheDocument();

      if (method === 'backdrop') {
        fireEvent.click(dialog.closest('.bx-backdrop')!);
      } else {
        fireEvent.click(method === 'close' ? close : within(dialog).getByRole('button', { name: 'I Understand' }));
      }

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(opener).toHaveFocus();
    });

    it('locks body scrolling only while open and restores the previous value on unmount', () => {
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'scroll';
      try {
        const { unmount } = render(<LegalHarness />);
        expect(document.body.style.overflow).toBe('scroll');
        fireEvent.click(screen.getByRole('button', { name: 'Open privacy' }));
        expect(document.body.style.overflow).toBe('hidden');
        unmount();
        expect(document.body.style.overflow).toBe('scroll');
      } finally {
        document.body.style.overflow = previousOverflow;
      }
    });

    it('consumes one Escape and ignores an Escape already handled by another surface', () => {
      const onClose = vi.fn();
      render(<LegalModal isOpen onClose={onClose} type="privacy" />);
      const consumed = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true });
      consumed.preventDefault();
      document.dispatchEvent(consumed);
      expect(onClose).not.toHaveBeenCalled();

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('describes synthetic research and remote provider policies without privacy guarantees', () => {
      render(<LegalModal isOpen onClose={() => {}} type="privacy" />);
      const dialog = screen.getByRole('dialog');

      expect(dialog).not.toHaveTextContent(/zero pii leakage|stateless free model pools|never share|full rights.*at any time/i);
      expect(dialog).toHaveTextContent(/synthetic/i);
      expect(dialog).toHaveTextContent(/remote (model )?providers/i);
      expect(dialog).toHaveTextContent(/retention.*training policies/i);
      expect(dialog).toHaveTextContent(/do not (submit|enter|include).*personal data.*confidential/i);
    });

    it('uses neutral theme surfaces and at least 44px dialog action targets', () => {
      render(<LegalModal isOpen onClose={() => {}} type="privacy" />);
      const panel = screen.getByRole('heading').closest<HTMLElement>('.bx-modal')!;

      expect(panel.style.backgroundColor).toBe('var(--bg-card)');
      expect(panel.style.color).toBe('var(--text-main)');
      expect(Number.parseFloat(panel.style.borderRadius)).toBeLessThanOrEqual(8);
      for (const button of within(panel).getAllByRole('button')) {
        expect(Math.max(Number.parseFloat(button.style.height) || 0, Number.parseFloat(button.style.minHeight) || 0))
          .toBeGreaterThanOrEqual(44);
        expect(Math.max(Number.parseFloat(button.style.width) || 0, Number.parseFloat(button.style.minWidth) || 0))
          .toBeGreaterThanOrEqual(44);
      }
    });
  });
});

import { useState } from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { AuthPage } from '../src/components/auth/AuthPage';
import { OtpInput } from '../src/components/auth/OtpInput';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';

describe('OtpInput fixed digit slots', () => {
  function ControlledOtp({ initialValue = '123456' }: { initialValue?: string }) {
    const [value, setValue] = useState(initialValue);
    return <><OtpInput value={value} onChange={setValue} /><output aria-label="OTP value">{value}</output></>;
  }

  const digit = (position: number) => screen.getByLabelText<HTMLInputElement>(`Digit ${position}`);
  const slotValues = () => Array.from({ length: 6 }, (_, index) => digit(index + 1).value);

  it('preserves later slots when a middle digit is removed and replaced', () => {
    render(<ControlledOtp />);

    fireEvent.change(digit(3), { target: { value: '' } });
    expect(slotValues()).toEqual(['1', '2', '', '4', '5', '6']);
    expect(screen.getByLabelText('OTP value')).toHaveTextContent('12456');

    fireEvent.change(digit(3), { target: { value: '9' } });
    expect(slotValues()).toEqual(['1', '2', '9', '4', '5', '6']);
    expect(screen.getByLabelText('OTP value')).toHaveTextContent('129456');
    expect(digit(4)).toHaveFocus();
  });

  it.each(['Backspace', 'Delete'])('clears only the focused occupied slot with %s', (key) => {
    render(<ControlledOtp />);
    digit(3).focus();

    fireEvent.keyDown(digit(3), { key });

    expect(slotValues()).toEqual(['1', '2', '', '4', '5', '6']);
    expect(digit(3)).toHaveFocus();
  });

  it('moves back from an empty slot and clears only the previous digit', () => {
    render(<ControlledOtp />);
    fireEvent.change(digit(3), { target: { value: '' } });
    digit(3).focus();

    fireEvent.keyDown(digit(3), { key: 'Backspace' });

    expect(slotValues()).toEqual(['1', '', '', '4', '5', '6']);
    expect(digit(2)).toHaveFocus();
  });

  it('selects digits reached with arrows and stays within the digit group', () => {
    render(<ControlledOtp />);
    digit(1).focus();
    fireEvent.keyDown(digit(1), { key: 'ArrowLeft' });
    expect(digit(1)).toHaveFocus();

    fireEvent.keyDown(digit(1), { key: 'ArrowRight' });
    expect(digit(2)).toHaveFocus();
    expect(digit(2).selectionStart).toBe(0);
    expect(digit(2).selectionEnd).toBe(1);

    digit(6).focus();
    fireEvent.keyDown(digit(6), { key: 'ArrowRight' });
    expect(digit(6)).toHaveFocus();
    expect(slotValues()).toEqual(['1', '2', '3', '4', '5', '6']);
  });

  it('overwrites only the destination slots for a partial paste', () => {
    render(<ControlledOtp />);
    fireEvent.paste(digit(3), { clipboardData: { getData: () => '9 8' } });

    expect(slotValues()).toEqual(['1', '2', '9', '8', '5', '6']);
    expect(digit(5)).toHaveFocus();
  });

  it('replaces all slots with a complete pasted code from any digit', () => {
    render(<ControlledOtp />);
    fireEvent.paste(digit(4), { clipboardData: { getData: () => '654 321' } });

    expect(slotValues()).toEqual(['6', '5', '4', '3', '2', '1']);
    expect(digit(6)).toHaveFocus();
  });

  it('accepts a complete autofill value without dropping its leading digits', () => {
    render(<ControlledOtp initialValue="" />);
    fireEvent.input(digit(4), { target: { value: '654321' } });

    expect(slotValues()).toEqual(['6', '5', '4', '3', '2', '1']);
    expect(screen.getByLabelText('OTP value')).toHaveTextContent('654321');
    expect(digit(1)).toHaveAttribute('autocomplete', 'one-time-code');
    expect(digit(1).maxLength).toBeGreaterThanOrEqual(6);
  });

  it('reflects external controlled replacements and clears without emitting changes', () => {
    const onChange = vi.fn();
    const { rerender } = render(<OtpInput value="123456" onChange={onChange} />);

    rerender(<OtpInput value="654321" onChange={onChange} />);
    expect(slotValues()).toEqual(['6', '5', '4', '3', '2', '1']);
    rerender(<OtpInput value="" onChange={onChange} />);
    expect(slotValues()).toEqual(['', '', '', '', '', '']);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('does not alter a code for a paste containing no digits', () => {
    render(<ControlledOtp />);
    fireEvent.paste(digit(3), { clipboardData: { getData: () => 'not a code' } });

    expect(slotValues()).toEqual(['1', '2', '3', '4', '5', '6']);
  });

  it('ignores pasted values while disabled', () => {
    const onChange = vi.fn();
    render(<OtpInput value="123456" onChange={onChange} disabled />);
    fireEvent.paste(digit(1), { clipboardData: { getData: () => '654321' } });

    expect(onChange).not.toHaveBeenCalled();
    expect(slotValues()).toEqual(['1', '2', '3', '4', '5', '6']);
  });

  it('does not silently turn an overlong pasted code into a complete code', () => {
    render(<ControlledOtp initialValue="" />);
    fireEvent.paste(digit(1), { clipboardData: { getData: () => '1234567' } });

    expect(slotValues()).toEqual(['', '', '', '', '', '']);
    expect(screen.getByLabelText('OTP value')).toBeEmptyDOMElement();
  });

  it('requires exactly one numeric character in every named native control', () => {
    render(<ControlledOtp initialValue="" />);

    expect(screen.getByRole('group', { name: 'Verification code' })).toBeInTheDocument();
    for (let position = 1; position <= 6; position += 1) {
      const input = digit(position);
      expect(input).toBeRequired();
      expect(input).toHaveAttribute('name', `otp-${position}`);
      expect(input).toHaveAttribute('pattern', '[0-9]');
      expect(input.checkValidity()).toBe(false);
    }

    fireEvent.paste(digit(1), { clipboardData: { getData: () => '123456' } });
    expect(Array.from({ length: 6 }, (_, index) => digit(index + 1).checkValidity())).toEqual(Array(6).fill(true));
  });
});

describe('AuthPage OTP Verification & Reset Flows', () => {
  beforeEach(() => {
    api.setMockMode(true);
    vi.restoreAllMocks();
  });

  it('provides one named main landmark around authentication controls', () => {
    renderAuthPage('signin');
    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('main', { name: 'BebshaX account' })).toContainElement(screen.getByRole('button', { name: /^Sign in$/i }));
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

  it.each(['verification', 'resend'] as const)(
    'keeps a manually entered verification email mounted while typing and sends the full address for %s',
    async (operation) => {
      api.clearSession();
      const email = 'alex+verify@example.com';
      const fetchRequest = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Unexpected network request'));
      const sendOtp = vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      const verifyEmailOtp = vi.spyOn(api, 'verifyEmailOtp').mockResolvedValue({
        user: {
          id: 'otp-user',
          email,
          full_name: 'Alex Founder',
          avatar_url: null,
          is_active: true,
          is_verified: true,
          auth_provider: 'email',
          created_at: '2026-09-12T00:00:00Z',
        },
      });
      renderAuthPage('verify-otp');

      const emailInput = screen.getByRole<HTMLInputElement>('textbox', { name: 'Email address' });
      expect(emailInput).toHaveValue('');
      expect(screen.getByRole('button', { name: 'Resend code' })).toBeDisabled();
      emailInput.focus();

      let typedEmail = '';
      for (const character of email) {
        typedEmail += character;
        fireEvent.input(emailInput, { target: { value: typedEmail } });

        expect(emailInput, `email remains mounted after typing ${typedEmail}`).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: 'Email address' })).toBe(emailInput);
        expect(emailInput).toHaveValue(typedEmail);
        expect(emailInput).toHaveFocus();
      }
      expect(sendOtp).not.toHaveBeenCalled();
      expect(verifyEmailOtp).not.toHaveBeenCalled();

      if (operation === 'verification') {
        for (const [index, digit] of Array.from('123456').entries()) {
          fireEvent.input(screen.getByLabelText(`Digit ${index + 1}`), { target: { value: digit } });
        }
        fireEvent.click(screen.getByRole('button', { name: 'Verify & Continue' }));

        await waitFor(() => expect(verifyEmailOtp).toHaveBeenCalledExactlyOnceWith(email, '123456'));
        expect(sendOtp).not.toHaveBeenCalled();
      } else {
        fireEvent.click(screen.getByRole('button', { name: 'Resend code' }));

        await waitFor(() => expect(sendOtp).toHaveBeenCalledExactlyOnceWith(email, 'email-verification'));
        expect(verifyEmailOtp).not.toHaveBeenCalled();
      }
      expect(fetchRequest).not.toHaveBeenCalled();
    },
  );

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

  describe('password reset completion', () => {
    const email = 'alex@bebshax.io';
    const newPassword = 'BrandNewPassword123!';

    const prepareReset = async () => {
      api.clearSession();
      renderAuthPage('forgot-password');
      fireEvent.change(screen.getByLabelText('Email address'), { target: { value: email } });
      fireEvent.click(screen.getByRole('button', { name: 'Send reset code' }));
      await screen.findByRole('heading', { name: 'Set new password' });
      fireEvent.paste(screen.getByLabelText('Digit 1'), { clipboardData: { getData: () => '123456' } });
      fireEvent.change(screen.getByLabelText('New password'), { target: { value: newPassword } });
      fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: newPassword } });
    };

    it('confirms a completed reset and retries only sign-in when automatic sign-in fails', async () => {
      vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      const resetPassword = vi.spyOn(api, 'resetPasswordWithOtp').mockResolvedValue(true);
      const signin = vi.spyOn(api, 'signin').mockRejectedValueOnce(new Error('Sign-in temporarily unavailable.'));
      await prepareReset();

      fireEvent.click(screen.getByRole('button', { name: 'Reset Password & Sign In' }));

      await screen.findByRole('heading', { name: 'Welcome back' });
      expect(screen.getByRole('status')).toHaveTextContent(/password (?:has been )?(?:updated|reset)/i);
      expect(screen.getByRole('alert')).toHaveTextContent('Sign-in temporarily unavailable.');
      expect(screen.queryByLabelText('Digit 1')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Email')).toHaveValue(email);
      expect(screen.getByLabelText('Password')).toHaveValue(newPassword);

      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

      await waitFor(() => expect(window.location.pathname).toBe('/app'));
      expect(resetPassword).toHaveBeenCalledExactlyOnceWith(email, '123456', newPassword);
      expect(signin).toHaveBeenCalledTimes(2);
      expect(signin).toHaveBeenLastCalledWith({ email, password: newPassword });
    });

    it('keeps the reset form and never signs in when the reset itself fails', async () => {
      vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      const resetPassword = vi.spyOn(api, 'resetPasswordWithOtp').mockRejectedValue(new Error('Invalid reset code.'));
      const signin = vi.spyOn(api, 'signin');
      await prepareReset();

      fireEvent.click(screen.getByRole('button', { name: 'Reset Password & Sign In' }));

      expect(await screen.findByRole('alert')).toHaveTextContent('Invalid reset code.');
      expect(screen.getByRole('heading', { name: 'Set new password' })).toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(resetPassword).toHaveBeenCalledExactlyOnceWith(email, '123456', newPassword);
      expect(signin).not.toHaveBeenCalled();
    });

    it('does not claim completion or sign in when the reset API returns false', async () => {
      vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      vi.spyOn(api, 'resetPasswordWithOtp').mockResolvedValue(false);
      const signin = vi.spyOn(api, 'signin');
      await prepareReset();

      fireEvent.click(screen.getByRole('button', { name: 'Reset Password & Sign In' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(/failed to reset password/i);
      expect(screen.getByRole('heading', { name: 'Set new password' })).toBeInTheDocument();
      expect(screen.queryByRole('status')).not.toBeInTheDocument();
      expect(signin).not.toHaveBeenCalled();
    });

    it('uses the existing email verification recovery when sign-in requires it after reset', async () => {
      const sendOtp = vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      const resetPassword = vi.spyOn(api, 'resetPasswordWithOtp').mockResolvedValue(true);
      vi.spyOn(api, 'signin').mockRejectedValue(Object.assign(new Error('Email not verified'), { code: 'EMAIL_NOT_VERIFIED' }));
      await prepareReset();

      fireEvent.click(screen.getByRole('button', { name: 'Reset Password & Sign In' }));

      await screen.findByRole('heading', { name: 'Enter verification code' });
      expect(resetPassword).toHaveBeenCalledExactlyOnceWith(email, '123456', newPassword);
      expect(sendOtp).toHaveBeenLastCalledWith(email, 'email-verification');
      expect(screen.queryByRole('button', { name: 'Reset Password & Sign In' })).not.toBeInTheDocument();
    });
  });

  describe('AuthPage-owned UI controls', () => {
    const passwordCases = [
      ['signin', 'Password', 'password'],
      ['signup-email', 'Password', 'password'],
      ['reset-password-otp', 'New password', 'new password'],
      ['reset-password-otp', 'Confirm new password', 'password confirmation'],
    ] as const;
    const fieldCases = [
      ['signin', ['Email', 'Password']],
      ['signup-email', ['Full name', 'Work email', 'Password']],
      ['forgot-password', ['Email address']],
      ['verify-otp', ['Email address']],
      ['reset-password-otp', ['New password', 'Confirm new password']],
    ] as const;

    const declaredSize = (element: HTMLElement, axis: 'width' | 'height') => Math.max(
      0,
      ...[element.style.getPropertyValue(axis), element.style.getPropertyValue(`min-${axis}`)]
        .filter((value) => /^\d+(?:\.\d+)?px$/.test(value))
        .map((value) => Number.parseFloat(value)),
    );

    const observeDeclaration = (property: 'border' | 'borderColor') => {
      const assignments = vi.spyOn(CSSStyleDeclaration.prototype, property, 'set');
      return (element: HTMLElement) => assignments.mock.calls[
        assignments.mock.contexts.lastIndexOf(element.style)
      ]?.[0];
    };

    it.each([
      ['signin', [['Email', 'email', 'email'], ['Password', 'password', 'current-password']]],
      ['signup-email', [['Full name', 'fullName', 'name'], ['Work email', 'email', 'email'], ['Password', 'password', 'new-password']]],
      ['forgot-password', [['Email address', 'email', 'email']]],
      ['verify-otp', [['Email address', 'email', 'email']]],
      ['reset-password-otp', [['Email address', 'email', 'email'], ['New password', 'password', 'new-password'], ['Confirm new password', 'confirmPassword', 'new-password']]],
    ] as const)('%s fields retain labels, names, autofill and native validation', (mode, fields) => {
      api.clearSession();
      renderAuthPage(mode);

      for (const [label, name, autoComplete] of fields) {
        const input = screen.getByLabelText<HTMLInputElement>(label);
        expect(input).toHaveAttribute('name', name);
        expect(input).toHaveAttribute('autocomplete', autoComplete);
        expect(input).toBeRequired();
        expect(input.form?.noValidate).toBe(false);
        if (name === 'email') {
          expect(input).toHaveAttribute('type', 'email');
          fireEvent.change(input, { target: { value: 'not-an-email' } });
          expect(input.checkValidity()).toBe(false);
          fireEvent.change(input, { target: { value: 'alex@example.com' } });
          expect(input.checkValidity()).toBe(true);
        }
        if (autoComplete === 'new-password') expect(input.minLength).toBe(8);
      }
    });

    it.each(['signin', 'signup', 'signup-email', 'forgot-password', 'verify-otp', 'reset-password-otp'] as const)(
      '%s exposes named button controls with 44px minimum touch targets',
      (mode) => {
        api.clearSession();
        renderAuthPage(mode);

        for (const button of screen.getAllByRole('button')) {
          expect(button).toHaveAccessibleName();
          const name = button.getAttribute('aria-label') || button.textContent || 'button';
          expect.soft(declaredSize(button, 'height'), `${name}: height`).toBeGreaterThanOrEqual(44);
          if (button.style.width !== '100%') {
            expect.soft(declaredSize(button, 'width'), `${name}: width`).toBeGreaterThanOrEqual(44);
          }
        }
      },
    );

    it('offers the brand home action as a keyboard-operable button', () => {
      renderAuthPage('signin');
      const home = screen.getByRole('button', { name: 'BebshaX home' });
      home.focus();
      expect(home).toHaveFocus();
      expect(home).toHaveAttribute('type', 'button');
      fireEvent.click(home);
      expect(window.location.pathname).toBe('/');
    });

    it.each(['', '123456'])('uses control tokens and stable OTP touch targets for value "%s"', (value) => {
      const border = observeDeclaration('border');
      const borderColor = observeDeclaration('borderColor');
      render(<OtpInput value={value} onChange={() => {}} autoFocus={false} />);
      const inputs = screen.getAllByRole('textbox');
      const group = screen.getByRole('group');

      for (const input of inputs) {
        expect.soft(border(input)).toBe('1px solid var(--border-control)');
        expect.soft(declaredSize(input, 'width')).toBeGreaterThanOrEqual(44);
        expect.soft(declaredSize(input, 'height')).toBeGreaterThanOrEqual(44);
        expect.soft(input.style.borderRadius).toBe('6px');
        expect.soft(input.style.outline).not.toMatch(/(^|\s)(none|0(?:px)?)(\s|$)/);
        fireEvent.focus(input);
        expect.soft(borderColor(input)).toBe('var(--focus-ring)');
        expect.soft(input.style.boxShadow).toBe('0 0 0 2px var(--focus-ring)');
        fireEvent.blur(input);
        expect.soft(borderColor(input)).toBe('var(--border-control)');
        expect.soft(input.style.boxShadow).toBe('none');
      }

      const rowWidth = inputs.reduce((total, input) => total + declaredSize(input, 'width'), 0)
        + Number.parseFloat(group.style.gap) * (inputs.length - 1);
      expect(rowWidth, 'six targets fit within the auth panel at 320px').toBeLessThanOrEqual(286);
    });

    it.each(['verify-otp', 'reset-password-otp'] as const)('%s never resends to an invalid email draft', async (mode) => {
      api.clearSession();
      const sendOtp = vi.spyOn(api, 'sendOtp').mockResolvedValue(true);
      renderAuthPage(mode);
      const email = screen.getByLabelText<HTMLInputElement>('Email address');
      expect(screen.getByRole('button', { name: 'Resend code' })).toBeDisabled();
      email.focus();
      for (const address of ['n', 'not-an-email']) {
        fireEvent.change(email, { target: { value: address } });
        expect(screen.getByLabelText('Email address')).toBe(email);
        expect(email).toHaveFocus();
      }
      fireEvent.click(screen.getByRole('button', { name: 'Resend code' }));
      expect(sendOtp).not.toHaveBeenCalled();

      fireEvent.change(email, { target: { value: 'alex@example.com' } });
      fireEvent.click(screen.getByRole('button', { name: 'Resend code' }));
      await waitFor(() => expect(sendOtp).toHaveBeenCalledExactlyOnceWith(
        'alex@example.com', mode === 'verify-otp' ? 'email-verification' : 'forget-password',
      ));
      expect(screen.getByRole('status')).toHaveTextContent(/code sent/i);
    });

    it.each(['verify-otp', 'reset-password-otp'] as const)('%s blocks submission when any middle OTP slot is empty', (mode) => {
      api.clearSession();
      const verify = vi.spyOn(api, 'verifyEmailOtp');
      const reset = vi.spyOn(api, 'resetPasswordWithOtp');
      renderAuthPage(mode);
      fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'alex@example.com' } });
      fireEvent.paste(screen.getByLabelText('Digit 1'), { clipboardData: { getData: () => '123456' } });
      if (mode === 'reset-password-otp') {
        fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'NewPassword123!' } });
        fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'NewPassword123!' } });
      }
      const submit = screen.getByRole('button', {
        name: mode === 'verify-otp' ? 'Verify & Continue' : 'Reset Password & Sign In',
      });
      expect(submit).toBeEnabled();
      fireEvent.change(screen.getByLabelText('Digit 3'), { target: { value: '' } });
      expect(submit).toBeDisabled();
      fireEvent.submit(submit.closest('form')!);

      expect(screen.getByRole('alert')).toHaveTextContent(/6-digit/i);
      expect(verify).not.toHaveBeenCalled();
      expect(reset).not.toHaveBeenCalled();
      expect(screen.getByLabelText('Digit 4')).toHaveValue('4');
      expect(screen.getByLabelText('Digit 6')).toHaveValue('6');
    });

    describe.each(passwordCases)('%s: %s visibility control', (mode, label, toggleName) => {
      it('can focus, reveal and conceal the password without clearing it or submitting', () => {
        renderAuthPage(mode);
        const input = screen.getByLabelText<HTMLInputElement>(label);
        const submit = vi.fn((event: Event) => event.preventDefault());
        expect(input.form).not.toBeNull();
        input.form!.addEventListener('submit', submit);
        fireEvent.change(input, { target: { value: 'VisibleOnlyOnRequest123!' } });

        const showButton = screen.getByRole('button', { name: `Show ${toggleName}` });
        expect(showButton).toHaveAttribute('type', 'button');
        expect(showButton.tabIndex).toBeGreaterThanOrEqual(0);
        showButton.focus();
        expect(showButton).toHaveFocus();
        expect(input).toHaveAttribute('type', 'password');
        fireEvent.click(showButton);

        expect(input).toHaveAttribute('type', 'text');
        expect(input).toHaveValue('VisibleOnlyOnRequest123!');
        const hideButton = screen.getByRole('button', { name: `Hide ${toggleName}` });
        expect(hideButton).toHaveAttribute('type', 'button');
        expect(hideButton.tabIndex).toBeGreaterThanOrEqual(0);
        hideButton.focus();
        expect(hideButton).toHaveFocus();
        fireEvent.click(hideButton);

        expect(input).toHaveAttribute('type', 'password');
        expect(input).toHaveValue('VisibleOnlyOnRequest123!');
        expect(screen.getByRole('button', { name: `Show ${toggleName}` })).toBeInTheDocument();
        expect(submit).not.toHaveBeenCalled();
      });

      it('declares a 44px minimum target with enough password padding to avoid overlap', () => {
        renderAuthPage(mode);
        const input = screen.getByLabelText<HTMLInputElement>(label);
        const button = screen.getByRole('button', { name: `Show ${toggleName}` });
        const width = declaredSize(button, 'width');
        const rightInset = Number.parseFloat(button.style.right || '0');

        expect.soft(width, 'toggle width').toBeGreaterThanOrEqual(44);
        expect.soft(declaredSize(button, 'height'), 'toggle height').toBeGreaterThanOrEqual(44);
        expect.soft(Number.parseFloat(input.style.paddingRight), 'password right padding')
          .toBeGreaterThanOrEqual(Math.max(44, width) + rightInset);
      });
    });

    describe.each(fieldCases)('%s owned fields', (mode, labels) => {
      it('declares control borders on render and blur and a focus-ring token on focus', () => {
        const border = observeDeclaration('border');
        const borderColor = observeDeclaration('borderColor');
        renderAuthPage(mode);

        for (const label of labels) {
          const input = screen.getByLabelText<HTMLInputElement>(label);
          expect.soft(border(input), `${label}: initial border`).toBe('1px solid var(--border-control)');

          fireEvent.focus(input);
          expect.soft(borderColor(input), `${label}: focused border`).toBe('var(--focus-ring)');
          expect.soft(input.style.boxShadow, `${label}: focus ring`).toBe('0 0 0 2px var(--focus-ring)');

          fireEvent.blur(input);
          expect.soft(borderColor(input), `${label}: blurred border`).toBe('var(--border-control)');
          expect.soft(input.style.boxShadow, `${label}: cleared focus ring`).toBe('none');
        }
      });

      it('declares 6px corners and 44px height without suppressing the keyboard outline', () => {
        renderAuthPage(mode);

        for (const label of labels) {
          const input = screen.getByLabelText<HTMLInputElement>(label);
          expect.soft(input.style.borderRadius, `${label}: radius`).toBe('6px');
          expect.soft(declaredSize(input, 'height'), `${label}: height`).toBeGreaterThanOrEqual(44);
          expect.soft(input.style.outline, `${label}: outline`).not.toMatch(/(^|\s)(none|0(?:px)?)(\s|$)/);
          expect.soft(input.style.outlineStyle, `${label}: outline style`).not.toBe('none');
          expect.soft(input.style.outlineWidth, `${label}: outline width`).not.toMatch(/^0(?:px)?$/);
        }
      });
    });

    it('declares zero tracking on the auth heading', () => {
      renderAuthPage('signin');

      expect(Number.parseFloat(screen.getByRole('heading', { level: 1 }).style.letterSpacing)).toBe(0);
    });

    it('keeps the standalone auth panel outside responsive dialog styling', () => {
      renderAuthPage('signin');

      expect(screen.getByRole('heading', { level: 1 }).closest('.bx-modal')).toBeNull();
    });

    it('keeps auth panel and button corner declarations at or below 8px', () => {
      renderAuthPage('signin');
      const panel = screen.getByRole('heading', { level: 1 }).closest<HTMLElement>('.bx-auth-panel');
      expect(panel).toBeInTheDocument();
      expect.soft(Number.parseFloat(panel!.style.borderRadius), 'auth panel radius').toBeLessThanOrEqual(8);

      for (const name of ['Sign in', 'Continue with Google', 'Back to BebshaX', 'Switch to light mode']) {
        const button = screen.getByRole('button', { name });
        expect.soft(Number.parseFloat(button.style.borderRadius), `${name}: radius`).toBeLessThanOrEqual(8);
      }
    });

    it('declares a theme-toggle target at least 44px in both dimensions', () => {
      renderAuthPage('signin');
      const button = screen.getByRole('button', { name: /Switch to (light|dark) mode/ });

      expect.soft(declaredSize(button, 'width'), 'theme toggle width').toBeGreaterThanOrEqual(44);
      expect.soft(declaredSize(button, 'height'), 'theme toggle height').toBeGreaterThanOrEqual(44);
    });
  });
});

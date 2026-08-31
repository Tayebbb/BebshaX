import React, { useState, useEffect } from 'react';
import {
  X,
  Mail,
  Eye,
  EyeOff,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  ShieldCheck,
  KeyRound,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../services/api';
import { neonAuth, isNeonAuthConfigured } from '../../services/neonAuth';
import { OtpInput } from './OtpInput';
import { BebshaXLogo } from '../common/BebshaXLogo';
import { LegalModal } from './LegalModal';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialView?: 'signin' | 'signup-options' | 'signup-email' | 'verify-otp';
  onSuccess?: () => void;
}

type AuthView =
  | 'signin'
  | 'signup-options'
  | 'signup-email'
  | 'verify-otp'
  | 'forgot-password'
  | 'reset-password-otp';

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  initialView = 'signin',
  onSuccess,
}) => {
  const [view, setView] = useState<AuthView>(initialView);

  // Form states
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [otp, setOtp] = useState('');
  const [legalModal, setLegalModal] = useState<'terms' | 'privacy' | null>(null);

  // Resend countdown
  const [countdown, setCountdown] = useState(0);

  // Loading & Error states
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const {
    signin,
    signup,
    googleAuth,
    sendOtp,
    verifyEmailOtp,
    resetPasswordWithOtp,
  } = useAuth();

  // Escape closes the top surface only: the legal modal first when stacked,
  // then the auth dialog. Capture phase + defaultPrevented + preventDefault
  // follow the repo Escape-stacking protocol (one surface per press).
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if (e.key !== 'Escape') return;
      e.preventDefault();
      if (legalModal) {
        setLegalModal(null);
        return;
      }
      onClose();
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [isOpen, legalModal, onClose]);

  if (!isOpen) return null;

  const resetForm = () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    setIsLoading(false);
  };

  const handleSwitchView = (newView: AuthView) => {
    resetForm();
    setView(newView);
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    resetForm();
    if (!email || !password) {
      setErrorMessage('Please provide both email and password.');
      return;
    }

    try {
      setIsLoading(true);
      await signin(email, password);
      onSuccess?.();
      onClose();
    } catch (err: any) {
      if (err.code === 'EMAIL_NOT_VERIFIED' || err.message?.includes('Email not verified')) {
        const sent = await sendOtp(email, 'email-verification').catch(() => false);
        if (sent) {
          setSuccessMessage(`We sent a 6-digit verification code to ${email}.`);
          setCountdown(30);
        } else {
          setErrorMessage(`Your email is not verified and we could not send a code to ${email}. Use "Resend" to retry.`);
        }
        setView('verify-otp');
      } else {
        setErrorMessage(err.message || 'Invalid email or password.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    resetForm();
    if (!fullName || !email || !password) {
      setErrorMessage('Please fill in all fields.');
      return;
    }
    if (password.length < 8) {
      setErrorMessage('Password must be at least 8 characters.');
      return;
    }
    const hasLetter = /[a-zA-Z]/.test(password);
    const hasDigit = /[0-9]/.test(password);
    if (!hasLetter || !hasDigit) {
      setErrorMessage('Password must contain at least one letter and one number.');
      return;
    }

    try {
      setIsLoading(true);
      await signup(fullName, email, password);
      const sent = await sendOtp(email, 'email-verification').catch(() => false);
      if (sent) {
        setSuccessMessage(`We sent a 6-digit verification code to ${email}.`);
        setCountdown(30);
      } else {
        setErrorMessage(`Account created, but we could not send a verification code to ${email}. Use "Resend" to retry.`);
      }
      setOtp('');
      setView('verify-otp');
    } catch (err: any) {
      if (err.message?.includes('already exists')) {
        setErrorMessage('An account with this email already exists. Please sign in.');
      } else if (err.code === 'EMAIL_NOT_VERIFIED' || err.message?.includes('verification')) {
        const sent = await sendOtp(email, 'email-verification').catch(() => false);
        if (sent) {
          setSuccessMessage(`Please enter the 6-digit verification code sent to ${email}.`);
          setCountdown(30);
        } else {
          setErrorMessage(`We could not send a verification code to ${email}. Use "Resend" to retry.`);
        }
        setView('verify-otp');
      } else {
        setErrorMessage(err.message || 'Registration failed. Email might already exist.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    resetForm();
    if (!otp || otp.length < 6) {
      setErrorMessage('Please enter the 6-digit verification code.');
      return;
    }

    try {
      setIsLoading(true);
      await verifyEmailOtp(email, otp);
      onSuccess?.();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Invalid verification code. Please check and try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    resetForm();
    if (!email) {
      setErrorMessage('Please enter your email address.');
      return;
    }
    setIsLoading(true);
    try {
      const sent = await sendOtp(email, 'forget-password');
      if (sent) {
        setSuccessMessage(`A 6-digit password reset code was sent to ${email}.`);
        setCountdown(30);
        setOtp('');
        setPassword('');
        setConfirmPassword('');
        setView('reset-password-otp');
      } else {
        setErrorMessage('Could not send reset code. Please check the email address.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to send reset code.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetPasswordWithOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    resetForm();
    if (!otp || otp.length < 6) {
      setErrorMessage('Please enter the 6-digit reset code.');
      return;
    }
    if (!password || password.length < 8) {
      setErrorMessage('New password must be at least 8 characters.');
      return;
    }
    const hasLetter = /[a-zA-Z]/.test(password);
    const hasDigit = /[0-9]/.test(password);
    if (!hasLetter || !hasDigit) {
      setErrorMessage('Password must contain at least one letter and one number.');
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    try {
      setIsLoading(true);
      await resetPasswordWithOtp(email, otp, password);
      await signin(email, password);
      onSuccess?.();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reset password. Please check the OTP code.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    if (!api.isMockMode() && !isNeonAuthConfigured()) {
      setErrorMessage('Google sign-in requires Neon Auth configuration.');
      return;
    }
    try {
      setIsLoading(true);
      if (api.isMockMode()) {
        // Test/mock builds: clearly-mock local session (same gate as email signin).
        await googleAuth({});
        onSuccess?.();
        onClose();
        return;
      }
      // Real federated flow: Neon-hosted Google OAuth (full-page redirect).
      // On return, AuthContext exchanges the verified Neon session for a
      // backend JWT via server-verified /auth/sync — no fabricated identity.
      await neonAuth.signInWithGoogle(`${window.location.origin}/app`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Google sign in failed.');
      setIsLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sign in or create your BebshaX account"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(15, 23, 42, 0.4)',
        backdropFilter: 'blur(8px)',
        padding: '16px',
        overflowY: 'auto',
      }}
      onClick={onClose}
    >
      {/* Container */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '460px',
          margin: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Brand Logo & Wordmark */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '20px',
          }}
        >
          <BebshaXLogo size={34} textSize="1.75rem" />
        </div>

        {/* Floating Card */}
        <div
          style={{
            background: '#FFFFFF',
            borderRadius: '24px',
            border: '1px solid rgba(229, 231, 235, 0.9)',
            boxShadow:
              '0 20px 40px -10px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02)',
            padding: '36px 32px',
            position: 'relative',
          }}
        >
          {/* Close button */}
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              position: 'absolute',
              top: '20px',
              right: '20px',
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              background: '#F3F4F6',
              border: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              color: '#6B7280',
            }}
          >
            <X size={15} />
          </button>

          {/* Alerts */}
          {errorMessage && (
            <div
              style={{
                padding: '12px 14px',
                borderRadius: '10px',
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
                color: '#DC2626',
                fontSize: '0.82rem',
                marginBottom: '18px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                <AlertCircle size={16} style={{ marginTop: '2px', flexShrink: 0 }} />
                <div style={{ flex: 1 }}>{errorMessage}</div>
              </div>
            </div>
          )}

          {successMessage && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                borderRadius: '10px',
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.2)',
                color: '#059669',
                fontSize: '0.82rem',
                marginBottom: '18px',
              }}
            >
              <CheckCircle2 size={16} />
              <span>{successMessage}</span>
            </div>
          )}

          {/* VIEW: SIGN IN */}
          {view === 'signin' && (
            <div>
              <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Welcome back
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  Sign in to your BebshaX account to continue
                </p>
              </div>

              {/* Google Button */}
              <button
                type="button"
                onClick={handleGoogleAuth}
                disabled={isLoading}
                style={{
                  width: '100%',
                  height: '42px',
                  borderRadius: '10px',
                  background: '#18181B',
                  color: '#FFFFFF',
                  border: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.1)',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.34 24 12 24z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 9.96 0 12s.45 3.83 1.25 5.42l4.03-3.15z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
                  />
                </svg>
                <span>Continue with Google</span>
              </button>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  margin: '22px 0',
                }}
              >
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: '#9CA3AF',
                    letterSpacing: '0.08em',
                  }}
                >
                  OR CONTINUE WITH EMAIL
                </span>
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
              </div>

              <form onSubmit={handleSignIn}>
                <div style={{ marginBottom: '16px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Email
                  </label>
                  <input
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    style={{
                      width: '100%',
                      height: '42px',
                      padding: '0 12px',
                      borderRadius: '8px',
                      border: '1px solid #D1D5DB',
                      fontSize: '0.88rem',
                      color: '#111827',
                      background: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '22px' }}>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '6px',
                    }}
                  >
                    <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#374151' }}>
                      Password
                    </label>
                    <button
                      type="button"
                      onClick={() => handleSwitchView('forgot-password')}
                      style={{
                        background: 'none',
                        border: 'none',
                        fontSize: '0.78rem',
                        color: '#6B7280',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      Forgot password?
                    </button>
                  </div>

                  <div style={{ position: 'relative' }}>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="password"
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      style={{
                        width: '100%',
                        height: '42px',
                        padding: '0 40px 0 12px',
                        borderRadius: '8px',
                        border: '1px solid #D1D5DB',
                        fontSize: '0.88rem',
                        color: '#111827',
                        background: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      style={{
                        position: 'absolute',
                        right: '12px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        color: '#9CA3AF',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  style={{
                    width: '100%',
                    height: '44px',
                    borderRadius: '10px',
                    background: isLoading ? '#F0D49D' : '#F6C878',
                    color: '#2B2516',
                    border: 'none',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                >
                  {isLoading ? 'Signing in...' : 'Sign in'}
                </button>
              </form>

              <div style={{ textAlign: 'center', marginTop: '22px' }}>
                <p style={{ fontSize: '0.82rem', color: '#6B7280', margin: 0 }}>
                  Don't have an account?{' '}
                  <button
                    type="button"
                    onClick={() => handleSwitchView('signup-options')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#8A6B29',
                      fontWeight: 700,
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    Sign up
                  </button>
                </p>
              </div>
            </div>
          )}

          {/* VIEW: SIGN UP OPTIONS */}
          {view === 'signup-options' && (
            <div>
              <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Create your account
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  Start your first research study in under a minute.
                </p>
              </div>

              <button
                type="button"
                onClick={handleGoogleAuth}
                disabled={isLoading}
                style={{
                  width: '100%',
                  height: '42px',
                  borderRadius: '10px',
                  background: '#18181B',
                  color: '#FFFFFF',
                  border: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.34 24 12 24z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 9.96 0 12s.45 3.83 1.25 5.42l4.03-3.15z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.34 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
                  />
                </svg>
                <span>Continue with Google</span>
              </button>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  margin: '20px 0',
                }}
              >
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    color: '#9CA3AF',
                    letterSpacing: '0.08em',
                  }}
                >
                  MORE WAYS
                </span>
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
              </div>

              <button
                type="button"
                onClick={() => handleSwitchView('signup-email')}
                style={{
                  width: '100%',
                  padding: '14px 16px',
                  borderRadius: '12px',
                  border: '1px solid #E5E7EB',
                  background: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div
                    style={{
                      width: '36px',
                      height: '36px',
                      borderRadius: '8px',
                      background: '#F3F4F6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#4B5563',
                    }}
                  >
                    <Mail size={18} />
                  </div>
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1E2319' }}>
                      Sign up with email
                    </div>
                    <div style={{ fontSize: '0.74rem', color: '#6B7280' }}>
                      Use a work email and password with instant OTP
                    </div>
                  </div>
                </div>
                <ChevronRight size={18} color="#9CA3AF" />
              </button>

              <div style={{ textAlign: 'center', marginTop: '16px' }}>
                <p style={{ fontSize: '0.74rem', color: '#9CA3AF', lineHeight: 1.4, margin: '0 0 10px 0' }}>
                  By continuing, you agree to our{' '}
                  <button
                    type="button"
                    onClick={() => setLegalModal('terms')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#6B7280',
                      textDecoration: 'underline',
                      cursor: 'pointer',
                      padding: 0,
                      fontSize: 'inherit',
                    }}
                  >
                    Terms of Service
                  </button>{' '}
                  and{' '}
                  <button
                    type="button"
                    onClick={() => setLegalModal('privacy')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#6B7280',
                      textDecoration: 'underline',
                      cursor: 'pointer',
                      padding: 0,
                      fontSize: 'inherit',
                    }}
                  >
                    Privacy Policy
                  </button>
                </p>
                <p style={{ fontSize: '0.82rem', color: '#6B7280', margin: 0 }}>
                  Already have an account?{' '}
                  <button
                    type="button"
                    onClick={() => handleSwitchView('signin')}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#8A6B29',
                      fontWeight: 700,
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    Sign in
                  </button>
                </p>
              </div>
            </div>
          )}

          {/* VIEW: SIGN UP EMAIL */}
          {view === 'signup-email' && (
            <div>
              <button
                type="button"
                onClick={() => handleSwitchView('signup-options')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'none',
                  border: 'none',
                  color: '#6B7280',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                  marginBottom: '16px',
                }}
              >
                <ArrowLeft size={14} />
                <span>Back</span>
              </button>

              <div style={{ marginBottom: '20px' }}>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Sign up with email
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  We'll send a 6-digit verification code to your email.
                </p>
              </div>

              <form onSubmit={handleSignUp}>
                <div style={{ marginBottom: '14px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Full name
                  </label>
                  <input
                    type="text"
                    name="fullName"
                    autoComplete="name"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="John Doe"
                    style={{
                      width: '100%',
                      height: '42px',
                      padding: '0 12px',
                      borderRadius: '8px',
                      border: '1px solid #D1D5DB',
                      fontSize: '0.88rem',
                      color: '#111827',
                      background: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Work email
                  </label>
                  <input
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    style={{
                      width: '100%',
                      height: '42px',
                      padding: '0 12px',
                      borderRadius: '8px',
                      border: '1px solid #D1D5DB',
                      fontSize: '0.88rem',
                      color: '#111827',
                      background: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '22px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Password
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="password"
                      autoComplete="new-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Create a password"
                      style={{
                        width: '100%',
                        height: '42px',
                        padding: '0 40px 0 12px',
                        borderRadius: '8px',
                        border: '1px solid #D1D5DB',
                        fontSize: '0.88rem',
                        color: '#111827',
                        background: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      style={{
                        position: 'absolute',
                        right: '12px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        color: '#9CA3AF',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  style={{
                    width: '100%',
                    height: '44px',
                    borderRadius: '10px',
                    background: isLoading ? '#F0D49D' : '#F6C878',
                    color: '#2B2516',
                    border: 'none',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                >
                  {isLoading ? 'Creating account...' : 'Create account'}
                </button>

                <div style={{ textAlign: 'center', marginTop: '16px' }}>
                  <p style={{ fontSize: '0.74rem', color: '#9CA3AF', lineHeight: 1.4, margin: 0 }}>
                    By creating an account, you agree to our{' '}
                    <button
                      type="button"
                      onClick={() => setLegalModal('terms')}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#6B7280',
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: 'inherit',
                      }}
                    >
                      Terms of Service
                    </button>{' '}
                    and{' '}
                    <button
                      type="button"
                      onClick={() => setLegalModal('privacy')}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: '#6B7280',
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: 'inherit',
                      }}
                    >
                      Privacy Policy
                    </button>
                  </p>
                </div>
              </form>
            </div>
          )}

          {/* VIEW: VERIFY OTP */}
          {view === 'verify-otp' && (
            <div>
              <button
                type="button"
                onClick={() => handleSwitchView('signup-email')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'none',
                  border: 'none',
                  color: '#6B7280',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                  marginBottom: '16px',
                }}
              >
                <ArrowLeft size={14} />
                <span>Back</span>
              </button>

              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: 'var(--accent-subtle)',
                    color: 'var(--accent-teal)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 12px auto',
                  }}
                >
                  <ShieldCheck size={24} />
                </div>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Enter verification code
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  We sent a 6-digit code to <strong style={{ color: '#111827' }}>{email}</strong>.
                </p>
              </div>

              <form onSubmit={handleVerifyOtp}>
                <OtpInput value={otp} onChange={setOtp} disabled={isLoading} />

                <button
                  type="submit"
                  disabled={isLoading || otp.length < 6}
                  style={{
                    width: '100%',
                    height: '44px',
                    borderRadius: '10px',
                    background: (isLoading || otp.length < 6) ? '#F0D49D' : '#F6C878',
                    color: '#2B2516',
                    border: 'none',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    cursor: (isLoading || otp.length < 6) ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                >
                  {isLoading ? 'Verifying...' : 'Verify & Continue'}
                </button>
              </form>

              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <p style={{ fontSize: '0.82rem', color: '#6B7280', margin: 0 }}>
                  Didn't receive the code?{' '}
                  <button
                    type="button"
                    disabled={countdown > 0 || isResending}
                    onClick={async () => {
                      if (countdown > 0 || !email) return;
                      setIsResending(true);
                      await sendOtp(email, 'email-verification').catch(() => {});
                      setIsResending(false);
                      setCountdown(30);
                      setSuccessMessage(`New code sent to ${email}.`);
                    }}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: countdown > 0 ? '#9CA3AF' : '#8A6B29',
                      fontWeight: 700,
                      cursor: countdown > 0 ? 'not-allowed' : 'pointer',
                      padding: 0,
                    }}
                  >
                    {countdown > 0 ? `Resend in ${countdown}s` : 'Resend code'}
                  </button>
                </p>
              </div>
            </div>
          )}

          {/* VIEW: FORGOT PASSWORD */}
          {view === 'forgot-password' && (
            <div>
              <button
                type="button"
                onClick={() => handleSwitchView('signin')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'none',
                  border: 'none',
                  color: '#6B7280',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                  marginBottom: '16px',
                }}
              >
                <ArrowLeft size={14} />
                <span>Back to sign in</span>
              </button>

              <div style={{ marginBottom: '20px' }}>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Reset password
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  Enter your email to receive a 6-digit reset code.
                </p>
              </div>

              <form onSubmit={handleForgotPassword}>
                <div style={{ marginBottom: '20px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Email address
                  </label>
                  <input
                    type="email"
                    name="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    style={{
                      width: '100%',
                      height: '42px',
                      padding: '0 12px',
                      borderRadius: '8px',
                      border: '1px solid #D1D5DB',
                      fontSize: '0.88rem',
                      color: '#111827',
                      background: '#FFFFFF',
                      outline: 'none',
                    }}
                  />
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  style={{
                    width: '100%',
                    height: '44px',
                    borderRadius: '10px',
                    background: isLoading ? '#F0D49D' : '#F6C878',
                    color: '#2B2516',
                    border: 'none',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isLoading ? 'Sending code...' : 'Send reset code'}
                </button>
              </form>
            </div>
          )}

          {/* VIEW: RESET PASSWORD WITH OTP */}
          {view === 'reset-password-otp' && (
            <div>
              <button
                type="button"
                onClick={() => handleSwitchView('forgot-password')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'none',
                  border: 'none',
                  color: '#6B7280',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                  marginBottom: '16px',
                }}
              >
                <ArrowLeft size={14} />
                <span>Back</span>
              </button>

              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: 'var(--accent-subtle)',
                    color: 'var(--accent-teal)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    margin: '0 auto 12px auto',
                  }}
                >
                  <KeyRound size={24} />
                </div>
                <h2
                  style={{
                    fontSize: '1.45rem',
                    fontWeight: 600,
                    color: '#1E2319',
                    letterSpacing: '-0.02em',
                    marginBottom: '6px',
                  }}
                >
                  Set new password
                </h2>
                <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                  Enter the 6-digit code sent to <strong style={{ color: '#111827' }}>{email}</strong>.
                </p>
              </div>

              <form onSubmit={handleResetPasswordWithOtp}>
                <div style={{ marginBottom: '12px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '4px',
                      textAlign: 'center',
                    }}
                  >
                    6-digit reset code
                  </label>
                  <OtpInput value={otp} onChange={setOtp} disabled={isLoading} />
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    New password
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="password"
                      autoComplete="new-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="At least 8 characters"
                      style={{
                        width: '100%',
                        height: '42px',
                        padding: '0 40px 0 12px',
                        borderRadius: '8px',
                        border: '1px solid #D1D5DB',
                        fontSize: '0.88rem',
                        color: '#111827',
                        background: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      style={{
                        position: 'absolute',
                        right: '12px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        color: '#9CA3AF',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                <div style={{ marginBottom: '22px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: '#374151',
                      marginBottom: '6px',
                    }}
                  >
                    Confirm new password
                  </label>
                  <div style={{ position: 'relative' }}>
                    <input
                      type={showConfirmPassword ? 'text' : 'password'}
                      name="confirmPassword"
                      autoComplete="new-password"
                      required
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat new password"
                      style={{
                        width: '100%',
                        height: '42px',
                        padding: '0 40px 0 12px',
                        borderRadius: '8px',
                        border: '1px solid #D1D5DB',
                        fontSize: '0.88rem',
                        color: '#111827',
                        background: '#FFFFFF',
                        outline: 'none',
                      }}
                    />
                    <button
                      type="button"
                      onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                      style={{
                        position: 'absolute',
                        right: '12px',
                        top: '50%',
                        transform: 'translateY(-50%)',
                        background: 'none',
                        border: 'none',
                        color: '#9CA3AF',
                        cursor: 'pointer',
                        padding: 0,
                      }}
                    >
                      {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading || otp.length < 6}
                  style={{
                    width: '100%',
                    height: '44px',
                    borderRadius: '10px',
                    background: (isLoading || otp.length < 6) ? '#F0D49D' : '#F6C878',
                    color: '#2B2516',
                    border: 'none',
                    fontSize: '0.9rem',
                    fontWeight: 700,
                    cursor: (isLoading || otp.length < 6) ? 'not-allowed' : 'pointer',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                >
                  {isLoading ? 'Resetting...' : 'Reset Password & Sign In'}
                </button>
              </form>
            </div>
          )}
        </div>
      </div>

      <LegalModal
        isOpen={Boolean(legalModal)}
        onClose={() => setLegalModal(null)}
        type={legalModal || 'terms'}
      />
    </div>
  );
};

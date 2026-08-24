import React, { useState } from 'react';
import {
  X,
  Mail,
  Eye,
  EyeOff,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialView?: 'signin' | 'signup-options' | 'signup-email';
  onSuccess?: () => void;
}

type AuthView = 'signin' | 'signup-options' | 'signup-email' | 'forgot-password';

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  initialView = 'signin',
  onSuccess,
}) => {
  const { signin, signup, googleAuth } = useAuth();
  const [view, setView] = useState<AuthView>(initialView);

  // Form states
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Loading & Error states
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const resetForm = () => {
    setFullName('');
    setEmail('');
    setPassword('');
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
    setErrorMessage(null);
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
      setErrorMessage(err.message || 'Invalid email or password.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    if (!fullName || !email || !password) {
      setErrorMessage('Please fill in all fields.');
      return;
    }
    if (password.length < 8) {
      setErrorMessage('Password must be at least 8 characters.');
      return;
    }

    try {
      setIsLoading(true);
      await signup(fullName, email, password);
      onSuccess?.();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Registration failed. Email might already exist.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    try {
      setIsLoading(true);
      await googleAuth({
        email: email || 'alex.founder@bebshax.io',
        name: fullName || 'Alex Founder',
      });
      onSuccess?.();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Google sign in failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setErrorMessage('Please enter your email address.');
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      setSuccessMessage('Password reset link sent to your email.');
    }, 800);
  };

  return (
    <div
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
      {/* Background Ambience & Dotted Texture */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          maxWidth: '460px',
          margin: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Brand Logo & Wordmark at top */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '10px',
            marginBottom: '20px',
          }}
        >
          {/* Geometric Triangle Node Logo */}
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M16 4L28 26H4L16 4Z"
              stroke="#2B3024"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="16" cy="4" r="2.5" fill="#2B3024" />
            <circle cx="28" cy="26" r="2.5" fill="#2B3024" />
            <circle cx="4" cy="26" r="2.5" fill="#2B3024" />
            <circle cx="16" cy="18" r="2" fill="#2B3024" />
            <line x1="16" y1="4" x2="16" y2="18" stroke="#2B3024" strokeWidth="1.8" />
            <line x1="4" y1="26" x2="16" y2="18" stroke="#2B3024" strokeWidth="1.8" />
            <line x1="28" y1="26" x2="16" y2="18" stroke="#2B3024" strokeWidth="1.8" />
          </svg>
          <span
            style={{
              fontSize: '1.75rem',
              fontWeight: 700,
              letterSpacing: '-0.03em',
              color: '#2B3024',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Bebsha<span style={{ color: '#2B3024' }}>X</span>
          </span>
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

          {/* Feedback alerts */}
          {errorMessage && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                borderRadius: '10px',
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
                color: '#DC2626',
                fontSize: '0.82rem',
                marginBottom: '18px',
              }}
            >
              <AlertCircle size={16} />
              <span>{errorMessage}</span>
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

          {/* ============================================================
              VIEW 1: SIGN IN
             ============================================================ */}
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
                  transition: 'background 0.2s ease',
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

              {/* Divider */}
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
                    fontSize: '0.66rem',
                    fontWeight: 700,
                    color: '#9CA3AF',
                    letterSpacing: '0.08em',
                  }}
                >
                  OR CONTINUE WITH EMAIL
                </span>
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
              </div>

              {/* Form */}
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
                      transition: 'border 0.2s, box-shadow 0.2s',
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = '#F6C878';
                      e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = '#D1D5DB';
                      e.target.style.boxShadow = 'none';
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
                    <label
                      style={{
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        color: '#374151',
                      }}
                    >
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
                        transition: 'border 0.2s, box-shadow 0.2s',
                      }}
                      onFocus={(e) => {
                        e.target.style.borderColor = '#F6C878';
                        e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                      }}
                      onBlur={(e) => {
                        e.target.style.borderColor = '#D1D5DB';
                        e.target.style.boxShadow = 'none';
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
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: 0,
                      }}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>

                {/* Primary CTA Golden Button */}
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
                    transition: 'all 0.2s ease',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isLoading) (e.target as HTMLElement).style.background = '#E5B45F';
                  }}
                  onMouseLeave={(e) => {
                    if (!isLoading) (e.target as HTMLElement).style.background = '#F6C878';
                  }}
                >
                  {isLoading ? 'Signing in...' : 'Sign in'}
                </button>
              </form>

              {/* Footer Switch */}
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

          {/* ============================================================
              VIEW 2: SIGN UP OPTIONS
             ============================================================ */}
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
                  transition: 'background 0.2s ease',
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
                  justifyContent: 'center',
                  gap: '4px',
                  marginTop: '8px',
                  color: '#9CA3AF',
                  fontSize: '0.72rem',
                }}
              >
                <span>⚡ Fastest way in</span>
              </div>

              {/* Divider */}
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
                    fontSize: '0.66rem',
                    fontWeight: 700,
                    color: '#9CA3AF',
                    letterSpacing: '0.08em',
                  }}
                >
                  MORE WAYS
                </span>
                <div style={{ flex: 1, height: '1px', background: '#E5E7EB' }} />
              </div>

              {/* Sign up with email option card */}
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
                  transition: 'all 0.2s ease',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = '#F9FAFB';
                  (e.currentTarget as HTMLElement).style.borderColor = '#D1D5DB';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = '#FFFFFF';
                  (e.currentTarget as HTMLElement).style.borderColor = '#E5E7EB';
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
                      Use a work email and password
                    </div>
                  </div>
                </div>
                <ChevronRight size={18} color="#9CA3AF" />
              </button>

              {/* Footer Switch */}
              <div style={{ textAlign: 'center', marginTop: '26px' }}>
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

          {/* ============================================================
              VIEW 3: EMAIL SIGN UP FORM
             ============================================================ */}
          {view === 'signup-email' && (
            <div>
              {/* Back to all options */}
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
                <span>Back to all options</span>
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
                  We'll send a verification link to confirm your address.
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
                      transition: 'border 0.2s, box-shadow 0.2s',
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = '#F6C878';
                      e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = '#D1D5DB';
                      e.target.style.boxShadow = 'none';
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
                      transition: 'border 0.2s, box-shadow 0.2s',
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = '#F6C878';
                      e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = '#D1D5DB';
                      e.target.style.boxShadow = 'none';
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
                        transition: 'border 0.2s, box-shadow 0.2s',
                      }}
                      onFocus={(e) => {
                        e.target.style.borderColor = '#F6C878';
                        e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                      }}
                      onBlur={(e) => {
                        e.target.style.borderColor = '#D1D5DB';
                        e.target.style.boxShadow = 'none';
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
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: 0,
                      }}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  <div style={{ fontSize: '0.74rem', color: '#9CA3AF', marginTop: '6px' }}>
                    At least 8 characters, alphanumeric.
                  </div>
                </div>

                {/* Create account button */}
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
                    transition: 'all 0.2s ease',
                    boxShadow: '0 2px 8px rgba(246, 200, 120, 0.35)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isLoading) (e.target as HTMLElement).style.background = '#E5B45F';
                  }}
                  onMouseLeave={(e) => {
                    if (!isLoading) (e.target as HTMLElement).style.background = '#F6C878';
                  }}
                >
                  {isLoading ? 'Creating account...' : 'Create account'}
                </button>
              </form>

              {/* Footer Switch */}
              <div style={{ textAlign: 'center', marginTop: '22px' }}>
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

          {/* ============================================================
              VIEW 4: FORGOT PASSWORD
             ============================================================ */}
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
                  Enter your email and we'll send you a password reset link.
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
                    onFocus={(e) => {
                      e.target.style.borderColor = '#F6C878';
                      e.target.style.boxShadow = '0 0 0 3px rgba(246, 200, 120, 0.35)';
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = '#D1D5DB';
                      e.target.style.boxShadow = 'none';
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
                  {isLoading ? 'Sending...' : 'Send reset link'}
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Global Footer Disclaimer */}
        <div style={{ textAlign: 'center', marginTop: '18px' }}>
          <p style={{ fontSize: '0.72rem', color: '#9CA3AF', lineHeight: 1.4 }}>
            By creating an account, you agree to our{' '}
            <a href="#" style={{ color: '#6B7280', textDecoration: 'underline' }}>
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="#" style={{ color: '#6B7280', textDecoration: 'underline' }}>
              Privacy Policy
            </a>
          </p>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import {
  Mail,
  Eye,
  EyeOff,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface AuthPageProps {
  initialMode?: 'signin' | 'signup' | 'signup-email' | 'forgot-password';
}

export const AuthPage: React.FC<AuthPageProps> = ({ initialMode = 'signin' }) => {
  const { signin, signup, googleAuth, isAuthenticated } = useAuth();
  const { currentPath, navigate } = useNavigation();

  // Determine current view from URL path or prop
  const [view, setView] = useState<'signin' | 'signup' | 'signup-email' | 'forgot-password'>(() => {
    if (currentPath.includes('/signup/email')) return 'signup-email';
    if (currentPath.includes('/signup') || currentPath.includes('/register')) return 'signup';
    if (currentPath.includes('/forgot-password') || currentPath.includes('/reset')) return 'forgot-password';
    return initialMode;
  });

  useEffect(() => {
    if (currentPath.includes('/signup/email')) {
      setView('signup-email');
    } else if (currentPath.includes('/signup') || currentPath.includes('/register')) {
      setView('signup');
    } else if (currentPath.includes('/forgot-password') || currentPath.includes('/reset')) {
      setView('forgot-password');
    } else if (currentPath.includes('/signin') || currentPath.includes('/login')) {
      setView('signin');
    }
  }, [currentPath]);

  // If already authenticated, redirect to /
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
    }
  }, [isAuthenticated, navigate]);

  // Form fields
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // States
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const resetMessages = () => {
    setErrorMessage(null);
    setSuccessMessage(null);
  };

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    resetMessages();
    if (!email || !password) {
      setErrorMessage('Please enter both email and password.');
      return;
    }

    try {
      setIsLoading(true);
      await signin(email, password);
      navigate('/');
    } catch (err: any) {
      setErrorMessage(err.message || 'Invalid email or password.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    resetMessages();
    if (!fullName || !email || !password) {
      setErrorMessage('Please fill in all required fields.');
      return;
    }
    if (password.length < 8) {
      setErrorMessage('Password must be at least 8 characters.');
      return;
    }

    try {
      setIsLoading(true);
      await signup(fullName, email, password);
      navigate('/');
    } catch (err: any) {
      setErrorMessage(err.message || 'Registration failed. Email may already be in use.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    resetMessages();
    try {
      setIsLoading(true);
      await googleAuth({
        email: email || 'alex.founder@bebshax.io',
        name: fullName || 'Alex Founder',
      });
      navigate('/');
    } catch (err: any) {
      setErrorMessage(err.message || 'Google authentication failed.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    resetMessages();
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
        minHeight: '100vh',
        width: '100%',
        backgroundColor: '#F8F9FA',
        backgroundImage: `
          radial-gradient(circle at 50% 35%, rgba(246, 200, 120, 0.12) 0%, rgba(246, 200, 120, 0.03) 45%, transparent 75%),
          radial-gradient(circle, #D1D5DB 1.15px, transparent 1.15px)
        `,
        backgroundSize: '100% 100%, 18px 18px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 16px',
        position: 'relative',
        color: '#1E2319',
      }}
    >
      {/* Back to Home Button at Top-Left */}
      <button
        onClick={() => navigate('/')}
        style={{
          position: 'absolute',
          top: '24px',
          left: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'rgba(255, 255, 255, 0.8)',
          backdropFilter: 'blur(10px)',
          border: '1px solid #E5E7EB',
          borderRadius: '10px',
          padding: '8px 14px',
          fontSize: '0.82rem',
          fontWeight: 600,
          color: '#4B5563',
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.03)',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = '#FFFFFF';
          e.currentTarget.style.borderColor = '#D1D5DB';
          e.currentTarget.style.color = '#111827';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.8)';
          e.currentTarget.style.borderColor = '#E5E7EB';
          e.currentTarget.style.color = '#4B5563';
        }}
      >
        <ArrowLeft size={15} />
        <span>Back to BebshaX</span>
      </button>

      {/* Brand Header */}
      <div
        onClick={() => navigate('/')}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '24px',
          cursor: 'pointer',
        }}
      >
        {/* Geometric Star/Triangle Logo Node */}
        <svg width="34" height="34" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
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
            fontSize: '1.85rem',
            fontWeight: 700,
            letterSpacing: '-0.03em',
            color: '#2B3024',
          }}
        >
          BebshaX
        </span>
      </div>

      {/* Centered Floating White Card */}
      <div
        style={{
          width: '100%',
          maxWidth: '440px',
          background: '#FFFFFF',
          borderRadius: '24px',
          border: '1px solid #EAEAEA',
          boxShadow: '0 20px 40px -15px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.02)',
          padding: '38px 32px',
          position: 'relative',
        }}
      >
        {/* Error / Success Banners */}
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
            VIEW 1: SIGN IN (/auth/signin)
           ============================================================ */}
        {view === 'signin' && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <h1
                style={{
                  fontSize: '1.45rem',
                  fontWeight: 600,
                  color: '#1E2319',
                  letterSpacing: '-0.02em',
                  marginBottom: '6px',
                }}
              >
                Welcome back
              </h1>
              <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                Sign in to your account to continue
              </p>
            </div>

            {/* Google Pill Button */}
            <button
              type="button"
              onClick={handleGoogleAuth}
              disabled={isLoading}
              style={{
                width: '100%',
                height: '42px',
                borderRadius: '8px',
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
                    onClick={() => {
                      resetMessages();
                      navigate('/auth/forgot-password');
                    }}
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

              {/* Golden CTA Button */}
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
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signup');
                  }}
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
            VIEW 2: SIGN UP OPTIONS (/auth/signup)
           ============================================================ */}
        {view === 'signup' && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <h1
                style={{
                  fontSize: '1.45rem',
                  fontWeight: 600,
                  color: '#1E2319',
                  letterSpacing: '-0.02em',
                  marginBottom: '6px',
                }}
              >
                Create your account
              </h1>
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
                borderRadius: '8px',
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

            {/* Sign up with email button */}
            <button
              type="button"
              onClick={() => {
                resetMessages();
                setView('signup-email');
              }}
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
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signin');
                  }}
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
            VIEW 3: DETAILED EMAIL SIGN UP
           ============================================================ */}
        {view === 'signup-email' && (
          <div>
            <button
              type="button"
              onClick={() => {
                resetMessages();
                setView('signup');
              }}
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
              <h1
                style={{
                  fontSize: '1.45rem',
                  fontWeight: 600,
                  color: '#1E2319',
                  letterSpacing: '-0.02em',
                  marginBottom: '6px',
                }}
              >
                Sign up with email
              </h1>
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

              {/* Create account golden button */}
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
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signin');
                  }}
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
              onClick={() => {
                resetMessages();
                navigate('/auth/signin');
              }}
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
              <h1
                style={{
                  fontSize: '1.45rem',
                  fontWeight: 600,
                  color: '#1E2319',
                  letterSpacing: '-0.02em',
                  marginBottom: '6px',
                }}
              >
                Reset password
              </h1>
              <p style={{ fontSize: '0.84rem', color: '#6B7280', margin: 0 }}>
                Enter your email to receive a password reset link.
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

      {/* Global Terms & Privacy Disclaimer */}
      <div style={{ textAlign: 'center', marginTop: '20px' }}>
        <p style={{ fontSize: '0.74rem', color: '#9CA3AF', lineHeight: 1.4 }}>
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
  );
};

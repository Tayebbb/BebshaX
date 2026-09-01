import React, { useState, useEffect } from 'react';
import {
  Mail,
  Eye,
  EyeOff,
  ChevronRight,
  ArrowLeft,
  AlertCircle,
  CheckCircle2,
  KeyRound,
  ShieldCheck,
  Sun,
  Moon,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { useTheme } from '../../context/ThemeContext';
import { api } from '../../services/api';
import { neonAuth, isNeonAuthConfigured } from '../../services/neonAuth';
import { OtpInput } from './OtpInput';
import { BebshaXLogo } from '../common/BebshaXLogo';
import { LegalModal } from './LegalModal';

interface AuthPageProps {
  initialMode?: 'signin' | 'signup' | 'signup-email' | 'forgot-password' | 'verify-otp' | 'reset-password-otp';
}

// Dark-theme tokens matching the app shell (DashboardLayout / StudyWorkflowView).
const headingStyle: React.CSSProperties = {
  fontSize: '1.45rem',
  fontWeight: 600,
  color: 'var(--text-main)',
  letterSpacing: '-0.02em',
  marginBottom: '6px',
};
const subtitleStyle: React.CSSProperties = { fontSize: '0.84rem', color: 'var(--text-secondary)', margin: 0 };
const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '0.8rem',
  fontWeight: 600,
  color: 'var(--text-label)',
  marginBottom: '6px',
};
const inputStyle: React.CSSProperties = {
  width: '100%',
  height: '42px',
  padding: '0 12px',
  borderRadius: '8px',
  border: '1px solid var(--border-subtle)',
  fontSize: '0.88rem',
  color: 'var(--text-main)',
  background: 'var(--bg-secondary)',
  outline: 'none',
  transition: 'border 0.2s, box-shadow 0.2s',
};
const passwordInputStyle: React.CSSProperties = { ...inputStyle, padding: '0 40px 0 12px' };
const focusInput = (e: React.FocusEvent<HTMLInputElement>) => {
  e.target.style.borderColor = 'var(--accent-teal)';
  e.target.style.boxShadow = '0 0 0 3px var(--accent-glow)';
};
const blurInput = (e: React.FocusEvent<HTMLInputElement>) => {
  e.target.style.borderColor = 'var(--border-subtle)';
  e.target.style.boxShadow = 'none';
};
const ctaStyle = (disabled: boolean): React.CSSProperties => ({
  width: '100%',
  height: '44px',
  borderRadius: '10px',
  background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
  color: 'var(--text-on-accent)',
  border: 'none',
  fontSize: '0.9rem',
  fontWeight: 700,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.55 : 1,
  transition: 'all 0.2s ease',
  boxShadow: '0 2px 14px var(--accent-glow)',
});
const linkStyle: React.CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--accent-teal-bright)',
  fontWeight: 700,
  cursor: 'pointer',
  padding: 0,
};
const backLinkStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  background: 'none',
  border: 'none',
  color: 'var(--text-secondary)',
  fontSize: '0.82rem',
  fontWeight: 500,
  cursor: 'pointer',
  padding: 0,
  marginBottom: '16px',
};
const eyeButtonStyle: React.CSSProperties = {
  position: 'absolute',
  right: '12px',
  top: '50%',
  transform: 'translateY(-50%)',
  background: 'none',
  border: 'none',
  color: 'var(--text-muted)',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 0,
};
const dividerLineStyle: React.CSSProperties = { flex: 1, height: '1px', background: 'var(--border-subtle)' };
const dividerTextStyle: React.CSSProperties = {
  fontSize: '0.72rem',
  fontWeight: 700,
  color: 'var(--text-muted)',
  letterSpacing: '0.08em',
};
const googleButtonStyle: React.CSSProperties = {
  width: '100%',
  height: '42px',
  borderRadius: '8px',
  background: 'var(--google-btn-bg)',
  color: 'var(--google-btn-fg)',
  border: '1px solid var(--border-subtle)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '10px',
  fontSize: '0.85rem',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'background 0.2s ease',
  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.35)',
};
const footerSwitchTextStyle: React.CSSProperties = { fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0 };

export const AuthPage: React.FC<AuthPageProps> = ({ initialMode = 'signin' }) => {
  const { currentPath, navigate } = useNavigation();
  const { theme, toggleTheme } = useTheme();
  const {
    signin,
    signup,
    googleAuth,
    sendOtp,
    verifyEmailOtp,
    resetPasswordWithOtp,
    isAuthenticated,
  } = useAuth();

  // Determine current view
  const [view, setView] = useState<
    'signin' | 'signup' | 'signup-email' | 'forgot-password' | 'verify-otp' | 'reset-password-otp'
  >(() => {
    if (currentPath.includes('/signup/email')) return 'signup-email';
    if (currentPath.includes('/verify') || currentPath.includes('/otp')) return 'verify-otp';
    if (currentPath.includes('/signup') || currentPath.includes('/register')) return 'signup';
    if (currentPath.includes('/forgot-password') || currentPath.includes('/reset')) return 'forgot-password';
    return initialMode;
  });

  useEffect(() => {
    if (currentPath.includes('/signup/email')) {
      setView('signup-email');
    } else if (currentPath.includes('/verify') || currentPath.includes('/otp')) {
      setView('verify-otp');
    } else if (currentPath.includes('/signup') || currentPath.includes('/register')) {
      setView('signup');
    } else if (currentPath.includes('/forgot-password') || currentPath.includes('/reset')) {
      setView('forgot-password');
    } else if (currentPath.includes('/signin') || currentPath.includes('/login')) {
      setView('signin');
    }
  }, [currentPath]);

  // If already authenticated, redirect to /app
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/app');
    }
  }, [isAuthenticated, navigate]);

  // Form fields
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [otp, setOtp] = useState('');
  const [legalModal, setLegalModal] = useState<'terms' | 'privacy' | null>(null);

  // Resend Countdown
  const [countdown, setCountdown] = useState(0);

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  // States
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // One-shot flag set by AuthContext when the OAuth-return /auth/sync
  // exchange fails — read once, cleared, shown in the standard error banner.
  useEffect(() => {
    if (window.sessionStorage.getItem('bebshax_oauth_error')) {
      window.sessionStorage.removeItem('bebshax_oauth_error');
      setErrorMessage("Google sign-in couldn't complete — try again or sign in with email.");
    }
  }, []);

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
      navigate('/app');
    } catch (err: any) {
      if (err.code === 'EMAIL_NOT_VERIFIED' || err.message?.includes('Email not verified')) {
        const sent = await sendOtp(email, 'email-verification').catch(() => false);
        if (sent) {
          setSuccessMessage(`We sent a 6-digit verification code to ${email}. Please enter it below.`);
          setCountdown(30);
        } else {
          setErrorMessage(
            `Your email is not verified and we could not send a code to ${email}. Use "Resend" to retry.`
          );
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
    resetMessages();
    if (!fullName || !email || !password) {
      setErrorMessage('Please fill in all required fields.');
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
      // Verification wall: send the OTP and say honestly whether it went out.
      const sent = await sendOtp(email, 'email-verification').catch(() => false);
      if (sent) {
        setSuccessMessage(`Account created! We've sent a 6-digit verification code to ${email}.`);
        setCountdown(30);
      } else {
        setErrorMessage(
          `Account created, but we could not send a verification code to ${email}. Use "Resend" to retry — you cannot sign in until the email is verified.`
        );
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
        setErrorMessage(err.message || 'Registration failed. Please check your information.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    resetMessages();
    if (!otp || otp.length < 6) {
      setErrorMessage('Please enter the full 6-digit verification code.');
      return;
    }

    try {
      setIsLoading(true);
      await verifyEmailOtp(email, otp);
      navigate('/app');
    } catch (err: any) {
      setErrorMessage(err.message || 'Invalid verification code. Please check and try again.');
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
    resetMessages();
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
      // Auto sign in with new password
      await signin(email, password);
      navigate('/app');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reset password. Please check the OTP code.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleResendOtp = async (type: 'email-verification' | 'forget-password') => {
    if (countdown > 0 || isResending || !email) return;
    try {
      setIsResending(true);
      resetMessages();
      const sent = await sendOtp(email, type);
      if (sent) {
        setSuccessMessage(`New 6-digit code sent to ${email}.`);
        setCountdown(30);
      } else {
        setErrorMessage('Failed to resend code. Please try again.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to resend code.');
    } finally {
      setIsResending(false);
    }
  };

  // Federated sign-in is only offered when the Neon Auth endpoint is
  // configured (mock/test builds keep the button for the mocked flow).
  const googleSignInAvailable = api.isMockMode() || isNeonAuthConfigured();

  const handleGoogleAuth = async () => {
    resetMessages();
    if (!googleSignInAvailable) {
      setErrorMessage('Google sign-in requires Neon Auth configuration.');
      return;
    }
    try {
      setIsLoading(true);
      if (api.isMockMode()) {
        // Test/mock builds: clearly-mock local session (same gate as email signin).
        await googleAuth({});
        navigate('/app');
        return;
      }
      // Real federated flow: Neon-hosted Google OAuth. This navigates away;
      // on return, AuthContext exchanges the verified Neon session for a
      // backend JWT via server-verified /auth/sync. No identity is ever
      // fabricated client-side.
      await neonAuth.signInWithGoogle(`${window.location.origin}/app`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Google authentication failed.');
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        width: '100%',
        backgroundColor: 'var(--bg-pure)',
        backgroundImage: `
          radial-gradient(circle at 50% 35%, var(--accent-subtle) 0%, var(--accent-subtle) 45%, transparent 75%),
          radial-gradient(circle, var(--fill-soft-2) 1.15px, transparent 1.15px)
        `,
        backgroundSize: '100% 100%, 18px 18px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px 16px',
        position: 'relative',
        color: 'var(--text-main)',
      }}
    >
      {/* Back to Home Button at Top-Left */}
      <button
        type="button"
        onClick={() => navigate('/')}
        style={{
          position: 'absolute',
          top: '24px',
          left: '24px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'var(--fill-soft-2)',
          backdropFilter: 'blur(10px)',
          border: '1px solid var(--border-soft)',
          borderRadius: '10px',
          padding: '8px 14px',
          fontSize: '0.82rem',
          fontWeight: 600,
          color: 'var(--text-primary)',
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
          transition: 'all 0.2s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'var(--border-soft)';
          e.currentTarget.style.borderColor = 'var(--border-soft)';
          e.currentTarget.style.color = 'var(--text-main)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'var(--fill-soft-2)';
          e.currentTarget.style.borderColor = 'var(--border-soft)';
          e.currentTarget.style.color = 'var(--text-primary)';
        }}
      >
        <ArrowLeft size={15} />
        <span>Back to BebshaX</span>
      </button>

      {/* Theme toggle at Top-Right */}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        style={{
          position: 'absolute',
          top: '24px',
          right: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '38px',
          height: '38px',
          background: 'var(--fill-soft-2)',
          backdropFilter: 'blur(10px)',
          border: '1px solid var(--border-soft)',
          borderRadius: '10px',
          color: 'var(--text-primary)',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
      >
        {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {/* Brand Header */}
      <div style={{ marginBottom: '24px' }}>
        <BebshaXLogo
          size={36}
          textSize="1.85rem"
          onClick={() => navigate('/')}
        />
      </div>

      {/* Centered Floating Card */}
      <div
        className="bx-modal"
        style={{
          width: '100%',
          maxWidth: '440px',
          background: 'var(--glass-mid)',
          backdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          WebkitBackdropFilter: 'blur(var(--glass-blur)) saturate(var(--glass-saturate))',
          borderRadius: '24px',
          border: '1px solid var(--border-soft)',
          boxShadow: 'inset 0 1px 0 var(--reflect-strong), var(--shadow-lg)',
          padding: '38px 32px',
          position: 'relative',
        }}
      >
        {/* Error / Success Banners */}
        {errorMessage && (
          <div
            role="alert"
            style={{
              padding: '12px 14px',
              borderRadius: '10px',
              background: 'rgba(239, 68, 68, 0.08)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              color: 'var(--status-error-text)',
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
            role="status"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '10px 14px',
              borderRadius: '10px',
              background: 'rgba(16, 185, 129, 0.08)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              color: 'var(--status-success-text)',
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
              <h1 style={headingStyle}>
                Welcome back
              </h1>
              <p style={subtitleStyle}>
                Sign in to your account to continue
              </p>
            </div>

            {/* Google Pill Button */}
            <button
              type="button"
              onClick={handleGoogleAuth}
              disabled={isLoading || !googleSignInAvailable}
              title={googleSignInAvailable ? undefined : 'Google sign-in requires Neon Auth configuration'}
              style={{ ...googleButtonStyle, ...(googleSignInAvailable ? {} : { opacity: 0.5, cursor: 'not-allowed' }) }}
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
              <div style={dividerLineStyle} />
              <span style={dividerTextStyle}>
                OR CONTINUE WITH EMAIL
              </span>
              <div style={dividerLineStyle} />
            </div>

            {/* Form */}
            <form onSubmit={handleSignIn}>
              <div style={{ marginBottom: '16px' }}>
                <label htmlFor="signin-email" style={labelStyle}>
                  Email
                </label>
                <input
                  id="signin-email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  style={inputStyle}
                  onFocus={focusInput}
                  onBlur={blurInput}
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
                    htmlFor="signin-password"
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: 'var(--text-label)',
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
                      color: 'var(--text-secondary)',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    Forgot password?
                  </button>
                </div>

                <div style={{ position: 'relative' }}>
                  <input
                    id="signin-password"
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    style={passwordInputStyle}
                    onFocus={focusInput}
                    onBlur={blurInput}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    style={eyeButtonStyle}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {/* Primary CTA Button */}
              <button
                type="submit"
                disabled={isLoading}
                style={ctaStyle(isLoading)}
              >
                {isLoading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            {/* Footer Switch */}
            <div style={{ textAlign: 'center', marginTop: '22px' }}>
              <p style={footerSwitchTextStyle}>
                Don't have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signup');
                  }}
                  style={linkStyle}
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
              <h1 style={headingStyle}>
                Create your account
              </h1>
              <p style={subtitleStyle}>
                Start your first research study in under a minute.
              </p>
            </div>

            {/* Google Button */}
            <button
              type="button"
              onClick={handleGoogleAuth}
              disabled={isLoading || !googleSignInAvailable}
              title={googleSignInAvailable ? undefined : 'Google sign-in requires Neon Auth configuration'}
              style={{ ...googleButtonStyle, ...(googleSignInAvailable ? {} : { opacity: 0.5, cursor: 'not-allowed' }) }}
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
                color: 'var(--text-muted)',
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
              <div style={dividerLineStyle} />
              <span style={dividerTextStyle}>
                MORE WAYS
              </span>
              <div style={dividerLineStyle} />
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
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-secondary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                textAlign: 'left',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)';
                (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-medium)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'var(--bg-secondary)';
                (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-subtle)';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    background: 'var(--accent-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--accent-teal-bright)',
                  }}
                >
                  <Mail size={18} />
                </div>
                <div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Sign up with email
                  </div>
                  <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                    Use a work email and password with instant OTP
                  </div>
                </div>
              </div>
              <ChevronRight size={18} color="var(--text-muted)" />
            </button>

            {/* Footer Switch */}
            <div style={{ textAlign: 'center', marginTop: '26px' }}>
              <p style={footerSwitchTextStyle}>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signin');
                  }}
                  style={linkStyle}
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
              style={backLinkStyle}
            >
              <ArrowLeft size={14} />
              <span>Back to all options</span>
            </button>

            <div style={{ marginBottom: '20px' }}>
              <h1 style={headingStyle}>
                Sign up with email
              </h1>
              <p style={subtitleStyle}>
                We'll send a 6-digit verification code to confirm your address.
              </p>
            </div>

            <form onSubmit={handleSignUp}>
              <div style={{ marginBottom: '14px' }}>
                <label htmlFor="signup-name" style={labelStyle}>
                  Full name
                </label>
                <input
                  id="signup-name"
                  type="text"
                  name="fullName"
                  autoComplete="name"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="John Doe"
                  style={inputStyle}
                  onFocus={focusInput}
                  onBlur={blurInput}
                />
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label htmlFor="signup-email" style={labelStyle}>
                  Work email
                </label>
                <input
                  id="signup-email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  style={inputStyle}
                  onFocus={focusInput}
                  onBlur={blurInput}
                />
              </div>

              <div style={{ marginBottom: '22px' }}>
                <label htmlFor="signup-password" style={labelStyle}>
                  Password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    id="signup-password"
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    autoComplete="new-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Create a password"
                    style={passwordInputStyle}
                    onFocus={focusInput}
                    onBlur={blurInput}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    style={eyeButtonStyle}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '6px' }}>
                  At least 8 characters, alphanumeric.
                </div>
              </div>

              {/* Create account button */}
              <button
                type="submit"
                disabled={isLoading}
                style={ctaStyle(isLoading)}
              >
                {isLoading ? 'Creating account...' : 'Create account'}
              </button>
            </form>

            {/* Footer Switch */}
            <div style={{ textAlign: 'center', marginTop: '22px' }}>
              <p style={footerSwitchTextStyle}>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    resetMessages();
                    navigate('/auth/signin');
                  }}
                  style={linkStyle}
                >
                  Sign in
                </button>
              </p>
            </div>
          </div>
        )}

        {/* ============================================================
            VIEW 4: VERIFY EMAIL OTP (/auth/verify-otp)
           ============================================================ */}
        {view === 'verify-otp' && (
          <div>
            <button
              type="button"
              onClick={() => {
                resetMessages();
                setView('signup-email');
              }}
              style={backLinkStyle}
            >
              <ArrowLeft size={14} />
              <span>Back / Change email</span>
            </button>

            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'var(--accent-subtle)',
                  color: 'var(--accent-teal-bright)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px auto',
                }}
              >
                <ShieldCheck size={24} />
              </div>
              <h1 style={headingStyle}>
                Enter verification code
              </h1>
              <p style={{ ...subtitleStyle, lineHeight: 1.5 }}>
                We sent a 6-digit code to <strong style={{ color: 'var(--text-main)' }}>{email || 'your email'}</strong>.
              </p>
            </div>

            <form onSubmit={handleVerifyOtp}>
              <OtpInput value={otp} onChange={setOtp} disabled={isLoading} />

              <button
                type="submit"
                disabled={isLoading || otp.length < 6}
                style={ctaStyle(isLoading || otp.length < 6)}
              >
                {isLoading ? 'Verifying...' : 'Verify & Continue'}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <p style={footerSwitchTextStyle}>
                Didn't receive the code?{' '}
                <button
                  type="button"
                  disabled={countdown > 0 || isResending}
                  onClick={() => handleResendOtp('email-verification')}
                  style={{
                    ...linkStyle,
                    color: countdown > 0 ? 'var(--text-muted)' : 'var(--accent-teal-bright)',
                    cursor: countdown > 0 ? 'not-allowed' : 'pointer',
                  }}
                >
                  {countdown > 0 ? `Resend in ${countdown}s` : isResending ? 'Sending...' : 'Resend code'}
                </button>
              </p>
            </div>
          </div>
        )}

        {/* ============================================================
            VIEW 5: FORGOT PASSWORD (REQUEST OTP)
           ============================================================ */}
        {view === 'forgot-password' && (
          <div>
            <button
              type="button"
              onClick={() => {
                resetMessages();
                navigate('/auth/signin');
              }}
              style={backLinkStyle}
            >
              <ArrowLeft size={14} />
              <span>Back to sign in</span>
            </button>

            <div style={{ marginBottom: '20px' }}>
              <h1 style={headingStyle}>
                Reset password
              </h1>
              <p style={subtitleStyle}>
                Enter your email to receive a 6-digit reset code.
              </p>
            </div>

            <form onSubmit={handleForgotPassword}>
              <div style={{ marginBottom: '20px' }}>
                <label htmlFor="forgot-email" style={labelStyle}>
                  Email address
                </label>
                <input
                  id="forgot-email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  style={inputStyle}
                  onFocus={focusInput}
                  onBlur={blurInput}
                />
              </div>

              <button
                type="submit"
                disabled={isLoading}
                style={ctaStyle(isLoading)}
              >
                {isLoading ? 'Sending code...' : 'Send reset code'}
              </button>
            </form>
          </div>
        )}

        {/* ============================================================
            VIEW 6: RESET PASSWORD WITH OTP
           ============================================================ */}
        {view === 'reset-password-otp' && (
          <div>
            <button
              type="button"
              onClick={() => {
                resetMessages();
                setView('forgot-password');
              }}
              style={backLinkStyle}
            >
              <ArrowLeft size={14} />
              <span>Back / Change email</span>
            </button>

            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '12px',
                  background: 'var(--accent-subtle)',
                  color: 'var(--accent-teal-bright)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px auto',
                }}
              >
                <KeyRound size={24} />
              </div>
              <h1 style={headingStyle}>
                Set new password
              </h1>
              <p style={{ ...subtitleStyle, lineHeight: 1.5 }}>
                Enter the 6-digit code sent to <strong style={{ color: 'var(--text-main)' }}>{email}</strong> and your new password.
              </p>
            </div>

            <form onSubmit={handleResetPasswordWithOtp}>
              <div style={{ marginBottom: '12px' }}>
                <label id="reset-otp-label" style={{ ...labelStyle, marginBottom: '4px', textAlign: 'center' }}>
                  6-digit reset code
                </label>
                <OtpInput value={otp} onChange={setOtp} disabled={isLoading} aria-labelledby="reset-otp-label" />
              </div>

              <div style={{ marginBottom: '14px' }}>
                <label htmlFor="reset-password" style={labelStyle}>
                  New password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    id="reset-password"
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    autoComplete="new-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    style={passwordInputStyle}
                    onFocus={focusInput}
                    onBlur={blurInput}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Hide new password' : 'Show new password'}
                    style={eyeButtonStyle}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <div style={{ marginBottom: '22px' }}>
                <label htmlFor="reset-confirm-password" style={labelStyle}>
                  Confirm new password
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    id="reset-confirm-password"
                    type={showConfirmPassword ? 'text' : 'password'}
                    name="confirmPassword"
                    autoComplete="new-password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                    style={passwordInputStyle}
                    onFocus={focusInput}
                    onBlur={blurInput}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    aria-label={showConfirmPassword ? 'Hide password confirmation' : 'Show password confirmation'}
                    style={eyeButtonStyle}
                  >
                    {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading || otp.length < 6}
                style={ctaStyle(isLoading || otp.length < 6)}
              >
                {isLoading ? 'Resetting...' : 'Reset Password & Sign In'}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <p style={footerSwitchTextStyle}>
                Didn't receive the code?{' '}
                <button
                  type="button"
                  disabled={countdown > 0 || isResending}
                  onClick={() => handleResendOtp('forget-password')}
                  style={{
                    ...linkStyle,
                    color: countdown > 0 ? 'var(--text-muted)' : 'var(--accent-teal-bright)',
                    cursor: countdown > 0 ? 'not-allowed' : 'pointer',
                  }}
                >
                  {countdown > 0 ? `Resend in ${countdown}s` : isResending ? 'Sending...' : 'Resend code'}
                </button>
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Global Terms & Privacy Disclaimer */}
      <div style={{ textAlign: 'center', marginTop: '20px' }}>
        <p style={{ fontSize: '0.74rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
          By creating an account, you agree to our{' '}
          <button
            type="button"
            onClick={() => setLegalModal('terms')}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
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
              color: 'var(--text-secondary)',
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

      <LegalModal
        isOpen={Boolean(legalModal)}
        onClose={() => setLegalModal(null)}
        type={legalModal || 'terms'}
      />
    </div>
  );
};

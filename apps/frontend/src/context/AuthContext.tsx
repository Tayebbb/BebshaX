import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { User, GoogleAuthData } from '../types/auth';
import { api } from '../services/api';
import { neonAuth } from '../services/neonAuth';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  signin: (email: string, password: string) => Promise<void>;
  signup: (fullName: string, email: string, password: string) => Promise<void>;
  googleAuth: (data?: GoogleAuthData) => Promise<void>;
  resendVerification: (email: string) => Promise<boolean>;
  sendOtp: (email: string, type?: 'email-verification' | 'forget-password') => Promise<boolean>;
  verifyEmailOtp: (email: string, otp: string) => Promise<void>;
  resetPasswordWithOtp: (email: string, otp: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => api.getAuthToken());
  const [user, setUser] = useState<User | null>(() => {
    const stored = api.getStoredUser();
    if (stored) return stored;
    if (api.isMockMode() && api.getAuthToken()) {
      return {
        id: 'usr_test',
        email: 'user@example.com',
        full_name: 'Test User',
        avatar_url: null,
        is_active: true,
        is_verified: true,
        auth_provider: 'email',
        created_at: new Date().toISOString(),
      };
    }
    return null;
  });
  const [isLoading, setIsLoading] = useState<boolean>(false);
  // H9: credentials held in memory only until OTP verification commits the
  // session (needed for the Neon sign-in that proves emailVerified).
  const pendingCredsRef = useRef<{ email: string; password: string } | null>(null);

  useEffect(() => {
    let isMounted = true;

    const initAuth = async () => {
      try {
        // 1. Check query params for token if redirected from OAuth callback
        if (typeof window !== 'undefined') {
          const urlParams = new URLSearchParams(window.location.search);
          const urlToken = urlParams.get('token') || urlParams.get('access_token');
          if (urlToken) {
            api.setAuthToken(urlToken);
            if (isMounted) setToken(urlToken);
            window.history.replaceState({}, document.title, window.location.pathname);
          }
        }

        // 2. OAuth return: after Neon-hosted Google sign-in redirects back,
        // there is no app token yet — only Neon's session cookie. Exchange it
        // through server-verified /auth/sync (backend re-verifies the Neon
        // token; identity never comes from client claims).
        if (!api.isMockMode() && !api.getAuthToken()) {
          const neonSession = await neonAuth.getSession(null);
          if (neonSession?.token) {
            await api.syncUser({ neon_token: neonSession.token });
          }
        }

        // 3. Query live Neon Auth session & backend /auth/me
        if (!api.isMockMode()) {
          const profile = await api.getMe();
          if (profile && isMounted) {
            setUser(profile);
            const activeToken = api.getAuthToken();
            if (activeToken) setToken(activeToken);
          } else if (!profile && isMounted) {
            setUser(null);
            setToken(null);
            api.setStoredUser(null);
            api.setAuthToken(null);
          }
        }
      } catch (err) {
        console.error('Session initialization error:', err);
        if (isMounted) {
          setUser(null);
          setToken(null);
          api.setStoredUser(null);
          api.setAuthToken(null);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    initAuth();

    return () => {
      isMounted = false;
    };
  }, []);

  const signin = async (email: string, password: string) => {
    try {
      const res = await api.signin({ email, password });
      setToken(res.access_token);
      setUser(res.user);
    } catch (err: any) {
      if (err?.code === 'EMAIL_NOT_VERIFIED') {
        pendingCredsRef.current = { email, password };
      }
      throw err;
    }
  };

  const signup = async (fullName: string, email: string, password: string) => {
    const res = await api.signup({ full_name: fullName, email, password });
    // H9: no session until the email is verified — keep credentials pending
    // so verifyEmailOtp can complete the Neon sign-in + backend sync.
    pendingCredsRef.current = { email, password };
    if (!res.verification_required && res.access_token && res.user?.is_verified) {
      // demo_mode backend issues a session directly.
      api.setAuthToken(res.access_token);
      api.setStoredUser(res.user);
      setToken(res.access_token);
      setUser(res.user);
    }
  };

  const googleAuth = async (data?: GoogleAuthData) => {
    const res = await api.googleAuth(data || {});
    setToken(res.access_token);
    setUser(res.user);
  };

  const resendVerification = async (email: string): Promise<boolean> => {
    return await api.resendVerificationEmail(email);
  };

  const sendOtp = async (
    email: string,
    type: 'email-verification' | 'forget-password' = 'email-verification'
  ): Promise<boolean> => {
    return await api.sendOtp(email, type);
  };

  const verifyEmailOtp = async (email: string, otp: string): Promise<void> => {
    // 1. Prove the code against Neon (the real OTP authority).
    const res = await api.verifyEmailOtp(email, otp);

    // 2. Obtain a Neon session token: the verify response may carry one;
    // otherwise sign in with the pending credentials.
    let neonToken = res.token || null;
    if (!neonToken && pendingCredsRef.current?.email === email) {
      try {
        const neonRes = await neonAuth.signIn({
          email,
          password: pendingCredsRef.current.password,
        });
        neonToken = neonRes.token || null;
      } catch {
        neonToken = null;
      }
    }

    // 3. Server-side sync: backend verifies the Neon token + emailVerified
    // and mints the real app JWT. No sync → no session (honest failure).
    if (neonToken) {
      const synced = await api.syncUser({ neon_token: neonToken });
      if (synced) {
        pendingCredsRef.current = null;
        setToken(synced.access_token);
        setUser(synced.user);
        return;
      }
    }

    // 4. Fallback: retry the normal backend signin — works once /auth/sync
    // (or a previous verification) has flipped is_verified.
    if (pendingCredsRef.current?.email === email) {
      const retry = await api.signin({
        email,
        password: pendingCredsRef.current.password,
      });
      pendingCredsRef.current = null;
      setToken(retry.access_token);
      setUser(retry.user);
      return;
    }

    throw new Error(
      'Email verified, but no session could be established. Please sign in.'
    );
  };

  const resetPasswordWithOtp = async (
    email: string,
    otp: string,
    password: string
  ): Promise<boolean> => {
    return await api.resetPasswordWithOtp(email, otp, password);
  };

  const logout = () => {
    api.signout().catch(() => {});
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        signin,
        signup,
        googleAuth,
        resendVerification,
        sendOtp,
        verifyEmailOtp,
        resetPasswordWithOtp,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, GoogleAuthData } from '../types/auth';
import { api } from '../services/api';

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
    const storedToken = api.getAuthToken();
    if (storedToken) {
      return {
        id: 'usr_stored',
        email: 'user@example.com',
        full_name: 'Authenticated User',
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

        // 2. Query live Neon Auth session & backend /auth/me
        if (!api.isMockMode()) {
          const profile = await api.getMe();
          if (profile && isMounted) {
            setUser(profile);
            const activeToken = api.getAuthToken();
            if (activeToken) setToken(activeToken);
          } else if (!profile && isMounted) {
            const storedToken = api.getAuthToken();
            if (!storedToken) {
              setUser(null);
              setToken(null);
              api.setStoredUser(null);
            }
          }
        }
      } catch (err) {
        console.error('Session initialization error:', err);
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
    const res = await api.signin({ email, password });
    setToken(res.access_token);
    setUser(res.user);
  };

  const signup = async (fullName: string, email: string, password: string) => {
    const res = await api.signup({ full_name: fullName, email, password });
    if (res.user?.is_verified) {
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
    const res = await api.verifyEmailOtp(email, otp);
    if (res.token) setToken(res.token);
    setUser(res.user);
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

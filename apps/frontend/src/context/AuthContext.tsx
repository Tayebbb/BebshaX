import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { User, GoogleAuthData, AuthResponse } from '../types/auth';
import { api, SIGNOUT_BROADCAST_KEY } from '../services/api';
import { advanceSession, getRefreshCredential, getSessionEpoch, hasCookieSession, SESSION_CHANGED } from '../services/session';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  sessionEpoch: number;
  signin: (email: string, password: string) => Promise<void>;
  signup: (fullName: string, email: string, password: string) => Promise<AuthResponse>;
  googleAuth: (data?: GoogleAuthData) => Promise<void>;
  resendVerification: (email: string) => Promise<boolean>;
  sendOtp: (email: string, type?: 'email-verification' | 'forget-password') => Promise<boolean>;
  verifyEmailOtp: (email: string, otp: string) => Promise<void>;
  resetPasswordWithOtp: (email: string, otp: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  authError: string | null;
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
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [sessionEpoch, setSessionEpoch] = useState(getSessionEpoch);
  const currentUserIdRef = useRef<string | null>(user?.id ?? null);
  useEffect(() => {
    currentUserIdRef.current = user?.id ?? null;
  }, [user?.id]);

  useEffect(() => {
    let isMounted = true;
    let initialization = 0;

    const initAuth = async () => {
      const current = ++initialization;
      const expectedSession = getSessionEpoch();
      const isCurrent = () => isMounted && current === initialization && expectedSession === getSessionEpoch();
      try {
        if (typeof window !== 'undefined') {
          const urlParams = new URLSearchParams(window.location.search);
          if (urlParams.has('token') || urlParams.has('access_token')) {
            urlParams.delete('token');
            urlParams.delete('access_token');
            const search = urlParams.toString();
            window.history.replaceState(window.history.state, '', `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`);
          }
        }

        if (!api.isMockMode()) {
          // Only a tab that actually held credentials may clear the shared identity:
          // a bystander tab rewriting it would broadcast a sign-out back and forth.
          const heldCredentials = api.hasSession() || getRefreshCredential() !== null;
          await api.completeOAuthReturn();
          const profile = await api.getMe();
          if (profile && isCurrent()) {
            setUser(profile);
            const activeToken = api.getAuthToken();
            if (activeToken) setToken(activeToken);
          } else if (!profile && isCurrent()) {
            setUser(null);
            setToken(null);
            if (heldCredentials) {
              api.setStoredUser(null);
              api.setAuthToken(null);
            }
          }
        }
      } catch {
        if (isCurrent()) {
          setUser(null);
          setToken(null);
          setAuthError('Session verification is unavailable. Please sign in again.');
        }
      } finally {
        if (isCurrent()) {
          setIsLoading(false);
        }
      }
    };

    const syncSession = () => {
      if (!isMounted) return;
      initialization += 1;
      setSessionEpoch(getSessionEpoch());
      setToken(api.getAuthToken());
      setUser(api.getAuthToken() || hasCookieSession() ? api.getStoredUser() : null);
      setIsLoading(false);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === 'bebshax_auth_token' || event.key === 'bebshax_auth_user' || event.key === 'bebshax_cookie_session'
          || event.key === 'bebshax_session_generation' || event.key === SIGNOUT_BROADCAST_KEY) {
        // The same account signing in from another tab is not a switch: this
        // tab's credentials stay valid. (Dropping them here used to sign out the
        // first tab, whose cleanup then broadcast a sign-out to the second.)
        const broadcastId = api.getStoredUser()?.id ?? null;
        if (!api.isMockMode() && event.key !== null && event.key !== 'bebshax_auth_token' && event.key !== SIGNOUT_BROADCAST_KEY
            && broadcastId !== null && broadcastId === currentUserIdRef.current && api.hasSession()) {
          return;
        }
        // Another tab *losing* its session (expired or rotated away) says nothing
        // about ours, which is tab-scoped: verify it instead of dropping it. An
        // explicit sign-out arrives on its own key and still ends every tab.
        const lostElsewhere = event.key !== null && event.key !== SIGNOUT_BROADCAST_KEY && event.newValue === null
          && (event.key === 'bebshax_auth_user' || event.key === 'bebshax_session_generation');
        if (!api.isMockMode() && lostElsewhere && currentUserIdRef.current !== null
            && (api.hasSession() || getRefreshCredential() !== null)) {
          setIsLoading(true);
          void initAuth();
          return;
        }
        if (!api.isMockMode()) api.invalidateTabSession();
        else advanceSession(false);
        if (api.isMockMode() && (event.key === null || (event.key === 'bebshax_auth_user' && event.newValue === null) ||
          (event.key === 'bebshax_session_generation' && event.newValue === null))) {
          api.clearSession();
        }
        syncSession();
        if (!api.isMockMode() && api.hasSession()) {
          setUser(null);
          setIsLoading(true);
          void initAuth();
        }
      }
    };
    window.addEventListener(SESSION_CHANGED, syncSession);
    window.addEventListener('storage', onStorage);
    void initAuth();

    return () => {
      isMounted = false;
      window.removeEventListener(SESSION_CHANGED, syncSession);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const signin = async (email: string, password: string) => {
    const res = await api.signin({ email, password });
    setToken(api.getAuthToken());
    setUser(res.user);
  };

  const signup = async (fullName: string, email: string, password: string): Promise<AuthResponse> => {
    const res = await api.signup({ full_name: fullName, email, password });
    if (!res.verification_required && (res.access_token || res.csrf_token) && res.user) {
      api.acceptAuthResponse(res);
      setToken(api.getAuthToken());
      setUser(res.user);
    }
    return res;
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
    setToken(api.getAuthToken());
    setUser(res.user);
  };

  const resetPasswordWithOtp = async (
    email: string,
    otp: string,
    password: string
  ): Promise<boolean> => {
    return await api.resetPasswordWithOtp(email, otp, password);
  };

  const logout = async () => {
    setAuthError(null);
    setToken(null);
    setUser(null);
    try {
      await api.signout();
    } catch {
      setAuthError('Signed out on this device. Server session revocation could not be confirmed.');
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        sessionEpoch,
        signin,
        signup,
        googleAuth,
        resendVerification,
        sendOtp,
        verifyEmailOtp,
        resetPasswordWithOtp,
        logout,
        authError,
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

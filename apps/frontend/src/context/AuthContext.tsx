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
  const [user, setUser] = useState<User | null>(() => api.getStoredUser());
  const [token, setToken] = useState<string | null>(() => api.getAuthToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = api.getAuthToken();
      try {
        const profile = await api.getMe();
        if (profile) {
          setUser(profile);
          if (storedToken) setToken(storedToken);
        } else if (!storedToken) {
          setUser(null);
          setToken(null);
        }
      } catch {
        // preserve offline/mock session if available
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const signin = async (email: string, password: string) => {
    const res = await api.signin({ email, password });
    setToken(res.access_token);
    setUser(res.user);
  };

  const signup = async (fullName: string, email: string, password: string) => {
    const res = await api.signup({ full_name: fullName, email, password });
    setToken(res.access_token);
    setUser(res.user);
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

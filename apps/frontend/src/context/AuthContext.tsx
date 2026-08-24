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
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(() => api.getAuthToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = api.getAuthToken();
      if (storedToken) {
        try {
          const profile = await api.getMe();
          if (profile) {
            setUser(profile);
            setToken(storedToken);
          } else {
            api.setAuthToken(null);
            setToken(null);
            setUser(null);
          }
        } catch {
          api.setAuthToken(null);
          setToken(null);
          setUser(null);
        }
      }
      setIsLoading(false);
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

  const logout = () => {
    api.setAuthToken(null);
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

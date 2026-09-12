import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { startRouteTiming } from '../performance/routeTiming';

interface NavigationContextType {
  currentPath: string;
  currentSearch: string;
  navigate: (path: string) => void;
}

const NavigationContext = createContext<NavigationContextType | undefined>(undefined);

export const NavigationProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [location, setLocation] = useState(() => ({ pathname: window.location.pathname || '/', search: window.location.search }));

  useEffect(() => {
    const handlePopState = () => {
      startRouteTiming(`${window.location.pathname}${window.location.search}`);
      setLocation({ pathname: window.location.pathname || '/', search: window.location.search });
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((path: string) => {
    const target = new URL(path, window.location.origin);
    if (target.origin !== window.location.origin) throw new Error('Navigation must stay on this site');
    const destination = `${target.pathname}${target.search}${target.hash}`;
    if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== destination) {
      startRouteTiming(destination);
      window.history.pushState({}, '', destination);
      setLocation({ pathname: target.pathname, search: target.search });
      if (typeof window !== 'undefined' && typeof window.scrollTo === 'function') {
        try {
          window.scrollTo({ top: 0, behavior: 'auto' });
        } catch {
          // ignore unsupported options
        }
      }
    }
  }, []);

  return (
    <NavigationContext.Provider value={{ currentPath: location.pathname, currentSearch: location.search, navigate }}>
      {children}
    </NavigationContext.Provider>
  );
};

export const useNavigation = (): NavigationContextType => {
  const context = useContext(NavigationContext);
  if (!context) {
    return {
      currentPath: typeof window !== 'undefined' ? window.location.pathname || '/' : '/',
      currentSearch: typeof window !== 'undefined' ? window.location.search : '',
      navigate: (path: string) => {
        if (typeof window !== 'undefined') {
          window.history.pushState({}, '', path);
        }
      },
    };
  }
  return context;
};

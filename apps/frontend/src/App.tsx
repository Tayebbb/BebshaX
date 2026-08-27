import React, { useEffect, useState } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { AuthPage } from './components/auth/AuthPage';
import { AuthModal } from './components/auth/AuthModal';
import { AuthProvider, useAuth } from './context/AuthContext';
import { NavigationProvider, useNavigation } from './context/NavigationContext';
import { ThemeProvider } from './context/ThemeContext';

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authInitialView, setAuthInitialView] = useState<
    'signin' | 'signup-options' | 'signup-email'
  >('signin');

  const { isAuthenticated, isLoading } = useAuth();
  const { currentPath, navigate } = useNavigation();

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await api.getHealth();
        setHealth(res);
      } catch (err) {
        console.error('Backend health ping failed:', err);
      }
    };
    fetchHealth();
  }, []);

  const handleOpenAuth = (
    view: 'signin' | 'signup-options' | 'signup-email' = 'signin'
  ) => {
    if (view === 'signin') {
      navigate('/auth/signin');
    } else if (view === 'signup-options' || view === 'signup-email') {
      navigate('/auth/signup');
    } else {
      setAuthInitialView(view);
      setIsAuthModalOpen(true);
    }
  };

  const handleOpenApp = () => {
    if (isAuthenticated) {
      navigate('/app');
    } else {
      navigate('/auth/signin');
    }
  };

  // 1. Session verification loading screen
  if (isLoading) {
    return (
      <div
        style={{
          minHeight: '100vh',
          backgroundColor: 'var(--bg-pure)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--status-warn-text)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              border: '3px solid rgba(246, 200, 120, 0.15)',
              borderTopColor: 'var(--status-warn-text)',
              borderRadius: '50%',
              animation: 'authSpin 0.7s linear infinite',
            }}
          />
          <style>{`@keyframes authSpin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
          <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', letterSpacing: '0.03em' }}>
            Checking authentication...
          </span>
        </div>
      </div>
    );
  }

  // Check if current URL is a dedicated Auth page route
  const isAuthRoute =
    currentPath.startsWith('/auth') ||
    currentPath === '/signin' ||
    currentPath === '/signup' ||
    currentPath === '/login' ||
    currentPath === '/register';

  if (isAuthRoute) {
    if (isAuthenticated) {
      return (
        <DashboardLayout onOpenLandingPage={() => navigate('/')} />
      );
    }
    return <AuthPage />;
  }

  // Check if current URL is an App / Dashboard route
  const isAppRoute =
    currentPath.startsWith('/app') ||
    currentPath.startsWith('/dashboard') ||
    currentPath.startsWith('/create-study') ||
    currentPath.startsWith('/new-study') ||
    currentPath.startsWith('/persona-library') ||
    currentPath.startsWith('/personas') ||
    currentPath.startsWith('/research') ||
    currentPath.startsWith('/study') ||
    currentPath.startsWith('/router') ||
    currentPath.startsWith('/provenance');

  if (isAppRoute) {
    if (!isAuthenticated) {
      return <AuthPage initialMode="signin" />;
    }
    return (
      <>
        {/* Screen-reader accessible identity */}
        <div
          style={{
            position: 'absolute',
            width: '1px',
            height: '1px',
            padding: 0,
            margin: '-1px',
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            borderWidth: 0,
          }}
        >
          <h1>BebshaX</h1>
          <p>Synthetic Persona Research Platform</p>
          <div>Backend Status: {health?.status || 'Connecting...'}</div>
        </div>

        {/* Dashboard Shell Application */}
        <DashboardLayout onOpenLandingPage={() => navigate('/')} />
      </>
    );
  }

  return (
    <>
      {/* Screen-reader / programmatic accessible platform identity container */}
      <div
        style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          borderWidth: 0,
        }}
      >
        <h1>BebshaX</h1>
        <p>Synthetic Persona Research Platform</p>
        <div>Backend Status: {health?.status || 'Connecting...'}</div>
      </div>

      {/* Main SaaS Decision Intelligence Landing Page */}
      <LandingPage
        onOpenApp={handleOpenApp}
        onOpenAuth={handleOpenAuth}
      />

      {/* Modal Fallback */}
      <AuthModal
        isOpen={isAuthModalOpen}
        initialView={authInitialView}
        onClose={() => setIsAuthModalOpen(false)}
      />
    </>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <NavigationProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </NavigationProvider>
    </ThemeProvider>
  );
};

export default App;

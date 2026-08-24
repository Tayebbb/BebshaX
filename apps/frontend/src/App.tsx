import React, { useEffect, useState } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { DashboardLayout } from './components/dashboard/DashboardLayout';
import { AuthPage } from './components/auth/AuthPage';
import { AuthModal } from './components/auth/AuthModal';
import { AuthProvider, useAuth } from './context/AuthContext';
import { NavigationProvider, useNavigation } from './context/NavigationContext';

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authInitialView, setAuthInitialView] = useState<
    'signin' | 'signup-options' | 'signup-email'
  >('signin');
  const [showLandingPreview, setShowLandingPreview] = useState<boolean>(false);

  const { isAuthenticated } = useAuth();
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

  // Check if current URL is a dedicated Auth page route
  const isAuthRoute =
    currentPath.startsWith('/auth') ||
    currentPath === '/signin' ||
    currentPath === '/signup' ||
    currentPath === '/login' ||
    currentPath === '/register';

  if (isAuthRoute) {
    return <AuthPage />;
  }

  // Check if current URL is an App / Dashboard route
  const isAppRoute =
    currentPath.startsWith('/app') ||
    currentPath.startsWith('/dashboard') ||
    currentPath.startsWith('/new-study') ||
    currentPath.startsWith('/personas') ||
    currentPath.startsWith('/organisation');

  if (isAppRoute) {
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
    <NavigationProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </NavigationProvider>
  );
};

export default App;

import React, { useEffect, useState } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { AppModal } from './components/app/AppModal';
import { AuthPage } from './components/auth/AuthPage';
import { AuthModal } from './components/auth/AuthModal';
import { AuthProvider } from './context/AuthContext';
import { NavigationProvider, useNavigation } from './context/NavigationContext';

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAppModalOpen, setIsAppModalOpen] = useState<boolean>(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authInitialView, setAuthInitialView] = useState<
    'signin' | 'signup-options' | 'signup-email'
  >('signin');

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
    setIsAppModalOpen(true);
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

      {/* Live App Platform Console Modal */}
      <AppModal
        isOpen={isAppModalOpen}
        onClose={() => setIsAppModalOpen(false)}
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

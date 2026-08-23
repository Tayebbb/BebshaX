import React, { useEffect, useState } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { AppModal } from './components/app/AppModal';
import { AuthModal } from './components/auth/AuthModal';
import { AuthProvider } from './context/AuthContext';

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAppModalOpen, setIsAppModalOpen] = useState<boolean>(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authInitialView, setAuthInitialView] = useState<
    'signin' | 'signup-options' | 'signup-email'
  >('signin');

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
    setAuthInitialView(view);
    setIsAuthModalOpen(true);
  };

  const handleOpenApp = () => {
    // If not authenticated, open sign in modal or allow demo exploration
    setIsAppModalOpen(true);
  };

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

      {/* Main SaaS Luxury Obsidian & Champagne Gold Landing Page */}
      <LandingPage
        onOpenApp={handleOpenApp}
        onOpenAuth={handleOpenAuth}
      />

      {/* Live App Platform Console Modal */}
      <AppModal
        isOpen={isAppModalOpen}
        onClose={() => setIsAppModalOpen(false)}
      />

      {/* Warm Minimal Authentication Modal */}
      <AuthModal
        isOpen={isAuthModalOpen}
        onClose={() => setIsAuthModalOpen(false)}
        initialView={authInitialView}
        onSuccess={() => {
          setIsAuthModalOpen(false);
          setIsAppModalOpen(true);
        }}
      />
    </>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;

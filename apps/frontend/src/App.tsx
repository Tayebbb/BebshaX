import React, { useEffect, useState, Suspense } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { NavigationProvider, useNavigation } from './context/NavigationContext';
import { ThemeProvider } from './context/ThemeContext';
import { initScrollReveal } from './utils/scrollReveal';
import { ErrorBoundary } from './components/common/ErrorBoundary';

// Route roots are split out of the first paint: a visitor on the landing page
// should never download the dashboard bundle. Named exports are re-mapped
// because React.lazy resolves the module's `default`.
const DashboardLayout = React.lazy(() =>
  import('./components/dashboard/DashboardLayout').then((m) => ({ default: m.DashboardLayout }))
);
const AuthPage = React.lazy(() =>
  import('./components/auth/AuthPage').then((m) => ({ default: m.AuthPage }))
);
const AuthModal = React.lazy(() =>
  import('./components/auth/AuthModal').then((m) => ({ default: m.AuthModal }))
);

// Painted while a route chunk streams in. Deliberately just the page
// background: a spinner that shows for 40ms reads as a flash, not as progress.
const RouteFallback: React.FC = () => (
  <div style={{ minHeight: '100vh', backgroundColor: 'var(--bg-pure)' }} />
);

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState<boolean>(false);
  const [authInitialView, setAuthInitialView] = useState<
    'signin' | 'signup-options' | 'signup-email'
  >('signin');

  const { isAuthenticated, isLoading } = useAuth();
  const { currentPath, navigate } = useNavigation();

  useEffect(() => {
    initScrollReveal();
  }, []);

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
    // Verification is reachable while signed in: the backend already
    // authenticated this user, verifying is a follow-up, not a gate.
    if (isAuthenticated && !currentPath.includes('/verify') && !currentPath.includes('/otp')) {
      return (
        <Suspense fallback={<RouteFallback />}>
          <DashboardLayout onOpenLandingPage={() => navigate('/')} health={health} />
        </Suspense>
      );
    }
    return (
      <Suspense fallback={<RouteFallback />}>
        <AuthPage />
      </Suspense>
    );
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
    currentPath.startsWith('/provenance') ||
    // Study-scoped tabs opened without an active study render their own
    // "pick a study" empty state inside the dashboard shell.
    currentPath.startsWith('/interviews') ||
    currentPath.startsWith('/behavioral-tests') ||
    currentPath.startsWith('/evidence') ||
    currentPath.startsWith('/segmentation');

  // Only the authenticated app waits on the session check — the landing and
  // auth pages must paint immediately, without blocking on a network call.
  // Skipping this for a locally-hydrated user was measured as a win but lets a
  // server-side-revoked session mount the whole dashboard, fire a burst of
  // doomed requests and flash the cached identity before bouncing. Not worth it.
  if (isLoading && isAppRoute) {
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

  if (isAppRoute) {
    if (!isAuthenticated) {
      return (
        <Suspense fallback={<RouteFallback />}>
          <AuthPage initialMode="signin" />
        </Suspense>
      );
    }
    return (
      <>
        {/* Screen-reader accessible identity. Not a heading: every view supplies
            its own h1, and two h1s per page confused the outline. */}
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
          <p>BebshaX</p>
          <p>Synthetic Persona Research Platform</p>
          <div>Backend Status: {health?.status || 'Connecting...'}</div>
        </div>

        {/* Dashboard Shell Application */}
        <Suspense fallback={<RouteFallback />}>
          <DashboardLayout onOpenLandingPage={() => navigate('/')} health={health} />
        </Suspense>
      </>
    );
  }

  return (
    <>
      {/* Screen-reader / programmatic platform identity. Not a heading — the
          landing hero owns the page's single h1. */}
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
        <p>BebshaX</p>
        <p>Synthetic Persona Research Platform</p>
        <div>Backend Status: {health?.status || 'Connecting...'}</div>
      </div>

      {/* Main SaaS Decision Intelligence Landing Page */}
      <LandingPage
        onOpenApp={handleOpenApp}
        onOpenAuth={handleOpenAuth}
      />

      {/* Modal Fallback */}
      {isAuthModalOpen && (
        <Suspense fallback={null}>
          <AuthModal
            isOpen={isAuthModalOpen}
            initialView={authInitialView}
            onClose={() => setIsAuthModalOpen(false)}
          />
        </Suspense>
      )}
    </>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <NavigationProvider>
        <AuthProvider>
          <ErrorBoundary>
            <AppContent />
          </ErrorBoundary>
        </AuthProvider>
      </NavigationProvider>
    </ThemeProvider>
  );
};

export default App;

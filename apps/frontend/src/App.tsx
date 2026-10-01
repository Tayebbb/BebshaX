import React, { useEffect, useState, Suspense } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';
import { LandingPage } from './components/landing/LandingPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { NavigationProvider, useNavigation } from './context/NavigationContext';
import { ThemeProvider } from './context/ThemeContext';
import { initScrollReveal } from './utils/scrollReveal';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { isDashboardPath, isKnownDashboardPath } from './utils/dashboardRoute';

// Named exports are re-mapped because React.lazy resolves the module's `default`.
const loadDashboard = () =>
  import('./components/dashboard/DashboardLayout').then((module) => ({ default: module.DashboardLayout }));
const DashboardLayout = React.lazy(loadDashboard);
const AuthPage = React.lazy(() =>
  import('./components/auth/AuthPage').then((m) => ({ default: m.AuthPage }))
);

// Painted while a route chunk streams in. Deliberately just the page
// background: a spinner that shows for 40ms reads as a flash, not as progress.
const RouteFallback: React.FC = () => (
  <div style={{ minHeight: '100vh', backgroundColor: 'var(--bg-pure)' }} />
);

const NotFound: React.FC<{ onHome: () => void }> = ({ onHome }) => (
  <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--bg-pure)', color: 'var(--text-main)' }}>
    <section style={{ maxWidth: 520, textAlign: 'center' }}>
      <p style={{ color: 'var(--accent-cyan)', fontWeight: 700 }}>404</p>
      <h1>Page not found</h1>
      <p style={{ color: 'var(--text-secondary)' }}>That BebshaX address does not exist.</p>
      <button type="button" onClick={onHome}>Return home</button>
    </section>
  </main>
);

const AppContent: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const { isAuthenticated, isLoading, sessionEpoch } = useAuth();
  const { currentPath, currentSearch, navigate } = useNavigation();

  const isAuthRoute =
    /^\/auth(?:\/|$)/.test(currentPath) ||
    currentPath === '/signin' ||
    currentPath === '/signup' ||
    currentPath === '/login' ||
    currentPath === '/register';
  const isAppRoute = isDashboardPath(currentPath) && isKnownDashboardPath(`${currentPath}${currentSearch}`);
  const isUnknownRoute = !isAuthRoute && currentPath !== '/' && !isAppRoute;
  const needsSignIn = isAppRoute && !isLoading && !isAuthenticated;

  // A signed-out visit to an app URL lands on the sign-in route (replacing the
  // entry, so Back does not bounce) with the destination kept for afterwards.
  // Live 2026-09-14: the form rendered under /persona-library etc., so
  // bookmarks and the back button carried an app URL that showed a login.
  useEffect(() => {
    if (!needsSignIn) return;
    const next = `${currentPath}${currentSearch}`;
    navigate(`/auth/signin${next && next !== '/app' ? `?next=${encodeURIComponent(next)}` : ''}`, { replace: true });
  }, [needsSignIn, currentPath, currentSearch, navigate]);

  useEffect(() => {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || connection?.effectiveType === '2g') return;
    if (isAuthenticated || isAuthRoute || isAppRoute) {
      void loadDashboard().catch(() => undefined);
    }
  }, [isAuthenticated, isAuthRoute, isAppRoute]);

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
    }
  };

  const handleOpenApp = () => {
    if (isAuthenticated) {
      navigate('/app');
    } else {
      navigate('/auth/signin');
    }
  };

  if (isAuthRoute) {
    // Verification is reachable while signed in: the backend already
    // authenticated this user, verifying is a follow-up, not a gate.
    return (
      <Suspense fallback={<RouteFallback />}>
        <AuthPage />
      </Suspense>
    );
  }

  if (isUnknownRoute) return <NotFound onHome={() => navigate('/')} />;

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
      <Suspense fallback={<RouteFallback />}>
        <DashboardLayout key={sessionEpoch} onOpenLandingPage={() => navigate('/')} health={health} />
      </Suspense>
    );
  }

  return (
    <LandingPage
      onOpenApp={handleOpenApp}
      onOpenAuth={handleOpenAuth}
    />
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

import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, ChevronDown, LogOut, Menu, Moon, Sun, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { useTheme } from '../../context/ThemeContext';
import { getSessionEpoch } from '../../services/session';
import { useDialogA11y } from '../../utils/useDialogA11y';

interface NavbarProps {
  onOpenApp?: () => void;
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

const navigationLinks = [
  { label: 'Workspace', href: '#product' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Pricing', href: '#pricing' },
  { label: 'FAQ', href: '#faq' },
];

export const Navbar: React.FC<NavbarProps> = ({ onOpenApp, onOpenAuth }) => {
  const { user, isAuthenticated, logout, sessionEpoch } = useAuth();
  const { navigate } = useNavigation();
  const { theme, toggleTheme } = useTheme();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [signoutError, setSignoutError] = useState<string | null>(null);
  const mobileTriggerRef = useRef<HTMLButtonElement>(null);
  const mobileRef = useRef<HTMLElement>(null);
  const accountRef = useRef<HTMLDivElement>(null);
  const accountTriggerRef = useRef<HTMLButtonElement>(null);
  const activeRef = useRef(true);
  const signoutRequestRef = useRef(0);

  const closeMobileMenu = () => {
    setMobileMenuOpen(false);
    mobileTriggerRef.current?.focus();
  };
  useDialogA11y(mobileRef, mobileMenuOpen, closeMobileMenu, { returnFocus: false });

  useEffect(() => {
    activeRef.current = true;
    const media = window.matchMedia('(max-width: 60rem)');
    const closeOnDesktop = (event: MediaQueryListEvent) => {
      if (!event.matches) setMobileMenuOpen(false);
    };
    media.addEventListener('change', closeOnDesktop);
    return () => {
      activeRef.current = false;
      media.removeEventListener('change', closeOnDesktop);
    };
  }, []);

  useEffect(() => {
    signoutRequestRef.current += 1;
    setAccountOpen(false);
    setSignoutError(null);
  }, [sessionEpoch, user?.id]);

  useEffect(() => {
    if (!accountOpen) return;
    accountRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const dismissOutside = (event: MouseEvent) => {
      if (!accountRef.current?.contains(event.target as Node)) setAccountOpen(false);
    };
    const handleKeys = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setAccountOpen(false);
        accountTriggerRef.current?.focus();
      } else if (event.key === 'Tab') {
        setAccountOpen(false);
      } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        const items = Array.from(accountRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
        if (!items.length) return;
        event.preventDefault();
        const currentIndex = items.indexOf(document.activeElement as HTMLElement);
        const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
          : (currentIndex + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[nextIndex].focus();
      }
    };
    document.addEventListener('mousedown', dismissOutside);
    document.addEventListener('keydown', handleKeys);
    return () => {
      document.removeEventListener('mousedown', dismissOutside);
      document.removeEventListener('keydown', handleKeys);
    };
  }, [accountOpen]);

  const openWorkspace = () => {
    setAccountOpen(false);
    setMobileMenuOpen(false);
    if (onOpenApp) onOpenApp();
    else navigate(isAuthenticated ? '/app' : '/auth/signin');
  };
  const openSignIn = () => {
    setMobileMenuOpen(false);
    if (onOpenAuth) onOpenAuth('signin');
    else navigate('/auth/signin');
  };
  const signOut = () => {
    const expectedSession = getSessionEpoch();
    const request = ++signoutRequestRef.current;
    setAccountOpen(false);
    setMobileMenuOpen(false);
    setSignoutError(null);
    void logout().catch(() => {
      if (activeRef.current && request === signoutRequestRef.current && expectedSession === getSessionEpoch()) {
        setSignoutError('Sign out could not be completed. Please try again.');
      }
    });
  };
  const followSection = (event: React.MouseEvent<HTMLAnchorElement>) => {
    setMobileMenuOpen(false);
    document.getElementById(event.currentTarget.hash.slice(1))?.focus({ preventScroll: true });
  };

  return (
    <header className="studio-header">
      <div className="studio-container studio-header-inner">
        <a href="#top" className="studio-brand" aria-label="BebshaX home">
          <img src="/logobebshax.jpeg" alt="" width="28" height="28" />
          <span>BebshaX</span>
        </a>
        <nav className="studio-desktop-nav" aria-label="Main navigation">
          {navigationLinks.map((link) => <a key={link.href} href={link.href}>{link.label}</a>)}
        </nav>
        <div className="studio-header-actions">
          <button type="button" className="studio-icon-button" onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? <Sun size={19} aria-hidden="true" /> : <Moon size={19} aria-hidden="true" />}
          </button>
          {isAuthenticated && user ? (
            <div className="studio-account" ref={accountRef}>
              <button ref={accountTriggerRef} type="button" className="studio-account-trigger"
                aria-label="Account menu" aria-haspopup="menu" aria-expanded={accountOpen}
                aria-controls="studio-account-menu" onClick={() => {
                  setMobileMenuOpen(false);
                  setAccountOpen(!accountOpen);
                }}>
                <span className="studio-avatar" aria-hidden="true">{user.full_name?.charAt(0).toUpperCase() || 'U'}</span>
                <span className="studio-account-name">{user.full_name?.split(' ')[0] || 'Account'}</span>
                <ChevronDown size={14} aria-hidden="true" />
              </button>
              {accountOpen && (
                <div id="studio-account-menu" className="studio-account-menu" role="menu" aria-label="Account">
                  <div role="presentation" className="studio-account-details">
                    <strong>{user.full_name || 'Your account'}</strong><span>{user.email}</span>
                  </div>
                  <button type="button" role="menuitem" onClick={openWorkspace}>
                    <ArrowRight size={17} aria-hidden="true" /> Open workspace
                  </button>
                  <button type="button" role="menuitem" onClick={signOut}>
                    <LogOut size={17} aria-hidden="true" /> Sign out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button type="button" className="studio-signin" onClick={openSignIn}>Sign in</button>
          )}
          <button ref={mobileTriggerRef} type="button" className="studio-icon-button studio-mobile-toggle"
            aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
            aria-expanded={mobileMenuOpen} aria-controls="studio-mobile-navigation"
            onClick={() => {
              setAccountOpen(false);
              if (mobileMenuOpen) closeMobileMenu();
              else setMobileMenuOpen(true);
            }}>
            {mobileMenuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
          </button>
        </div>
      </div>
      {mobileMenuOpen && (
        <nav ref={mobileRef} id="studio-mobile-navigation" className="studio-mobile-nav" aria-label="Mobile navigation">
          {navigationLinks.map((link) => (
            <a key={link.href} href={link.href} onClick={followSection}>{link.label}<ArrowRight size={17} aria-hidden="true" /></a>
          ))}
          <button type="button" className="studio-button" onClick={openWorkspace}>Open workspace <ArrowRight size={18} aria-hidden="true" /></button>
          <button type="button" className="studio-text-link" onClick={closeMobileMenu}>Close menu <X size={16} aria-hidden="true" /></button>
        </nav>
      )}
      {signoutError && <p className="studio-error" role="alert">{signoutError}</p>}
    </header>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import {
  Menu,
  X,
  ArrowRight,
  Activity,
  ChevronDown,
  Building2,
  Briefcase,
  Search,
  Lightbulb,
  Zap,
  Layers,
  LogOut,
  Sun,
  Moon,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';
import { useTheme } from '../../context/ThemeContext';
import { BebshaXLogo } from '../common/BebshaXLogo';

interface NavbarProps {
  onOpenApp?: () => void;
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenApp, onOpenAuth }) => {
  const { user, isAuthenticated, logout } = useAuth();
  const { navigate } = useNavigation();
  const { theme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [solutionsDropdownOpen, setSolutionsDropdownOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);
  const userDropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setSolutionsDropdownOpen(false);
      }
      if (userDropdownRef.current && !userDropdownRef.current.contains(event.target as Node)) {
        setUserDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    setSolutionsDropdownOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 50,
        height: '68px',
        display: 'flex',
        alignItems: 'center',
        background: scrolled
          ? 'rgba(var(--lp-bg-rgb), 0.72)'
          : 'rgba(var(--lp-bg-rgb), 0)',
        // The blur is declared unconditionally so the compositor allocates the
        // header's backdrop layer once at load instead of creating/destroying
        // it at the scroll threshold, which is a visible hitch. At rest the
        // radius is 0 — backdrop-filter blurs what is *behind* the element
        // regardless of its own background, so leaving 22px on would blur the
        // top of the hero. 0px keeps the layer without the visual change, and
        // the radius interpolates cleanly.
        backdropFilter: scrolled ? 'blur(22px) saturate(160%)' : 'blur(0px) saturate(100%)',
        WebkitBackdropFilter: scrolled ? 'blur(22px) saturate(160%)' : 'blur(0px) saturate(100%)',
        border: 'none',
        borderBottom: scrolled ? '1px solid var(--border-soft)' : '1px solid transparent',
        // Enumerated, so the browser never tries to interpolate layout
        // properties on this element.
        transition:
          'background-color 0.25s ease, border-bottom-color 0.25s ease, backdrop-filter 0.25s ease, -webkit-backdrop-filter 0.25s ease',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        {/* Brand Wordmark & Icon */}
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            textDecoration: 'none',
            color: 'var(--lp-text)',
            border: 'none',
          }}
        >
          <BebshaXLogo size={32} showIcon={false} />
          <span
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              padding: '2px 6px',
              borderRadius: '9999px',
              background: 'rgba(var(--lp-fill-rgb), 0.08)',
              color: 'var(--lp-text-dim)',
              border: 'none',
              letterSpacing: '0.05em',
            }}
          >
            PRO
          </span>
        </a>

        {/* Center Minimal Navigation */}
        <nav
          className="desktop-nav"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '28px',
            position: 'relative',
          }}
        >
          <button
            onClick={() => scrollToSection('product')}
            className="nav-link-btn"
          >
            Console
          </button>

          {/* Solutions Dropdown Menu */}
          <div ref={dropdownRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setSolutionsDropdownOpen(!solutionsDropdownOpen)}
              onMouseEnter={() => setSolutionsDropdownOpen(true)}
              className="nav-link-btn"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                color: solutionsDropdownOpen ? 'var(--lp-text)' : 'var(--text-secondary)',
              }}
            >
              <span>Who It Is For</span>
              <ChevronDown
                size={13}
                style={{
                  transform: solutionsDropdownOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                  transition: 'transform 0.2s ease',
                }}
              />
            </button>

            {/* Dropdown Card */}
            {solutionsDropdownOpen && (
              <div
                onMouseLeave={() => setSolutionsDropdownOpen(false)}
                style={{
                  position: 'absolute',
                  top: '40px',
                  left: '-120px',
                  width: '520px',
                  background: 'var(--lp-elevated)',
                  border: 'none',
                  borderRadius: '16px',
                  padding: '20px',
                  boxShadow: 'var(--lp-shadow-lg)',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '20px',
                  zIndex: 60,
                }}
              >
                {/* Column 1: Industries */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--lp-gold)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    AUDIENCES
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {[
                      { title: 'Founders', desc: 'Interview a persona before you build', icon: <Briefcase size={14} color="var(--lp-gold)" /> },
                      { title: 'Product & UX research', desc: 'Directional input with labelled attributes', icon: <Layers size={14} color="var(--lp-gold)" /> },
                      { title: 'Researchers & students', desc: 'A testbed for multi-model routing', icon: <Building2 size={14} color="var(--lp-gold)" /> },
                    ].map((item, i) => (
                      <div
                        key={i}
                        onClick={() => scrollToSection('solutions')}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          padding: '8px 10px',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background: 'rgba(var(--lp-fill-rgb), 0.03)',
                          border: 'none',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(var(--lp-fill-rgb), 0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(var(--lp-fill-rgb), 0.03)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(var(--lp-gold-rgb), 0.12)', border: 'none' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--lp-text)' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--lp-text-muted)' }}>{item.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Column 2: Use Cases */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--lp-gold)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    THE LOOP
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {[
                      { title: 'Define your goal', desc: 'A plain-English chat with the Study Design Copilot', icon: <Search size={14} color="var(--lp-blue)" /> },
                      { title: 'Generate personas', desc: 'With a label on every attribute', icon: <Lightbulb size={14} color="var(--lp-blue)" /> },
                      { title: 'Interview, then decide', desc: 'Multi-turn interviews, then a decision report', icon: <Zap size={14} color="var(--lp-blue)" /> },
                    ].map((item, i) => (
                      <div
                        key={i}
                        onClick={() => scrollToSection('solutions')}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          padding: '8px 10px',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background: 'rgba(var(--lp-fill-rgb), 0.03)',
                          border: 'none',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(var(--lp-fill-rgb), 0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(var(--lp-fill-rgb), 0.03)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(var(--lp-blue-rgb), 0.12)', border: 'none' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--lp-text)' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--lp-text-muted)' }}>{item.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <button
            onClick={() => scrollToSection('how-it-works')}
            className="nav-link-btn"
          >
            How It Works
          </button>
          <button
            onClick={() => scrollToSection('intelligence')}
            className="nav-link-btn"
          >
            Routing
          </button>
          <button
            onClick={() => scrollToSection('demo')}
            className="nav-link-btn"
          >
            Task Map
          </button>
          <button
            onClick={() => scrollToSection('pricing')}
            className="nav-link-btn"
          >
            Pricing
          </button>
          <button
            onClick={() => scrollToSection('faq')}
            className="nav-link-btn"
          >
            FAQ
          </button>
        </nav>

        {/* Right Action CTA Group */}
        <div
          className="desktop-cta"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
          }}
        >
          <button
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              transition: 'color 0.2s ease',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--lp-text)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-secondary)')}
          >
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          {isAuthenticated && user ? (
            /* Logged-In User Profile Pill */
            <div style={{ position: 'relative' }} ref={userDropdownRef}>
              <button
                onClick={() => setUserDropdownOpen(!userDropdownOpen)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '5px 12px 5px 6px',
                  borderRadius: '9999px',
                  background: 'rgba(var(--lp-fill-rgb), 0.08)',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--lp-text)',
                  fontSize: '0.84rem',
                  fontWeight: 600,
                }}
              >
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: 'var(--lp-contrast-bg)',
                    color: 'var(--lp-contrast-fg)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.72rem',
                    fontWeight: 800,
                    border: 'none',
                  }}
                >
                  {user.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
                </div>
                <span>{user.full_name.split(' ')[0]}</span>
                <ChevronDown size={13} color="var(--lp-text-muted)" />
              </button>

              {/* User Dropdown */}
              {userDropdownOpen && (
                <div
                  style={{
                    position: 'absolute',
                    top: '40px',
                    right: 0,
                    width: '220px',
                    background: 'var(--lp-elevated)',
                    borderRadius: '14px',
                    padding: '12px',
                    boxShadow: 'var(--lp-shadow-md)',
                    zIndex: 70,
                    border: 'none',
                  }}
                >
                  <div style={{ paddingBottom: '10px', marginBottom: '8px' }}>
                    <div style={{ fontSize: '0.84rem', fontWeight: 700, color: 'var(--lp-text)' }}>
                      {user.full_name}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--lp-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {user.email}
                    </div>
                  </div>

                  <button
                    onClick={() => {
                      setUserDropdownOpen(false);
                      onOpenApp?.();
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      background: 'none',
                      border: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      color: 'var(--lp-text)',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(var(--lp-fill-rgb), 0.06)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                  >
                    <Activity size={14} color="var(--lp-gold)" />
                    <span>Launch Console</span>
                  </button>

                  <button
                    onClick={() => {
                      setUserDropdownOpen(false);
                      logout();
                    }}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '8px',
                      background: 'none',
                      border: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      fontSize: '0.82rem',
                      fontWeight: 600,
                      color: 'var(--lp-red)',
                      cursor: 'pointer',
                      textAlign: 'left',
                      marginTop: '4px',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(var(--lp-red-rgb), 0.12)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                  >
                    <LogOut size={14} color="var(--lp-red)" />
                    <span>Sign Out</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Guest Auth Buttons */
            <>
              <button
                onClick={() => (onOpenAuth ? onOpenAuth('signin') : navigate('/auth/signin'))}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '0.86rem',
                  fontWeight: 500,
                  color: 'var(--lp-text-dim)',
                  cursor: 'pointer',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  transition: 'color 0.2s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--lp-text)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--lp-text-dim)')}
              >
                Sign In
              </button>

              <button
                onClick={() => (onOpenAuth ? onOpenAuth('signup-options') : navigate('/auth/signup'))}
                style={{
                  padding: '8px 16px',
                  fontSize: '0.86rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  borderRadius: '9999px',
                  background: 'var(--lp-contrast-bg)',
                  color: 'var(--lp-contrast-fg)',
                  border: 'none',
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--lp-contrast-bg-hover)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--lp-contrast-bg)')}
              >
                <span>Try Free</span>
                <ArrowRight size={14} color="var(--lp-contrast-fg)" />
              </button>
            </>
          )}
        </div>

        {/* Mobile Hamburger Toggle */}
        <button
          className="mobile-toggle"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--lp-text)',
            cursor: 'pointer',
            padding: '8px',
            display: 'none',
          }}
          aria-label="Toggle navigation"
        >
          {mobileMenuOpen ? <X size={22} color="var(--lp-text)" /> : <Menu size={22} color="var(--lp-text)" />}
        </button>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div
          style={{
            position: 'absolute',
            top: '68px',
            left: 0,
            right: 0,
            background: 'var(--lp-drawer)',
            border: 'none',
            padding: '20px 20px 32px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '14px',
            boxShadow: 'var(--lp-shadow-drawer)',
            maxHeight: 'calc(100vh - 68px)',
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch',
            zIndex: 60,
          }}
        >
          <button
            onClick={() => scrollToSection('product')}
            className="mobile-nav-btn"
          >
            Console
          </button>
          <button
            onClick={() => scrollToSection('solutions')}
            className="mobile-nav-btn"
          >
            Who It Is For
          </button>
          <button
            onClick={() => scrollToSection('how-it-works')}
            className="mobile-nav-btn"
          >
            How It Works
          </button>
          <button
            onClick={() => scrollToSection('intelligence')}
            className="mobile-nav-btn"
          >
            Routing
          </button>
          <button
            onClick={() => scrollToSection('demo')}
            className="mobile-nav-btn"
          >
            Task Map
          </button>
          <button
            onClick={() => scrollToSection('pricing')}
            className="mobile-nav-btn"
          >
            Pricing
          </button>
          <button
            onClick={() => scrollToSection('faq')}
            className="mobile-nav-btn"
          >
            FAQ
          </button>

          <button
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            className="mobile-nav-btn"
            style={{ display: 'flex', alignItems: 'center', gap: '10px' }}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            <span>{theme === 'dark' ? 'Light theme' : 'Dark theme'}</span>
          </button>

          <div style={{ height: '1px', background: 'var(--lp-line)', margin: '8px 0' }} />

          {isAuthenticated && user ? (
            <>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  onOpenApp?.();
                }}
                className="secondary-btn"
                style={{
                  padding: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  border: 'none',
                }}
              >
                <Activity size={16} color="var(--lp-gold)" />
                <span>Launch Console</span>
              </button>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  logout();
                }}
                style={{
                  padding: '12px',
                  fontWeight: 600,
                  border: 'none',
                  borderRadius: '9999px',
                  background: 'rgba(var(--lp-red-rgb), 0.12)',
                  color: 'var(--lp-red)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <LogOut size={16} color="var(--lp-red)" />
                <span>Sign Out</span>
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  if (onOpenAuth) onOpenAuth('signin');
                  else navigate('/auth/signin');
                }}
                className="secondary-btn"
                style={{
                  padding: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  border: 'none',
                }}
              >
                <span>Sign In</span>
              </button>
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  if (onOpenAuth) onOpenAuth('signup-options');
                  else navigate('/auth/signup');
                }}
                style={{
                  padding: '12px',
                  fontWeight: 700,
                  border: 'none',
                  borderRadius: '9999px',
                  background: 'var(--lp-contrast-bg)',
                  color: 'var(--lp-contrast-fg)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <span>Try Free</span>
                <ArrowRight size={16} color="var(--lp-contrast-fg)" />
              </button>
            </>
          )}
        </div>
      )}
    </header>
  );
};

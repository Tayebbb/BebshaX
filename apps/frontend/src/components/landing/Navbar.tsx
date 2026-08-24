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
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useNavigation } from '../../context/NavigationContext';

interface NavbarProps {
  onOpenApp?: () => void;
  onOpenAuth?: (view?: 'signin' | 'signup-options' | 'signup-email') => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenApp, onOpenAuth }) => {
  const { user, isAuthenticated, logout } = useAuth();
  const { navigate } = useNavigation();
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
          ? 'rgba(0, 0, 0, 0.9)'
          : 'transparent',
        backdropFilter: scrolled ? 'blur(16px)' : 'none',
        WebkitBackdropFilter: scrolled ? 'blur(16px)' : 'none',
        border: 'none',
        transition: 'all 0.25s ease',
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
            gap: '10px',
            textDecoration: 'none',
            color: '#FFFFFF',
            border: 'none',
          }}
        >
          <div
            style={{
              width: '30px',
              height: '30px',
              borderRadius: '8px',
              background: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
            }}
          >
            <Activity size={17} color="#000000" strokeWidth={2.5} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.03em', color: '#FFFFFF' }}>
              Bebsha<span style={{ color: '#F6C878' }}>X</span>
            </span>
            <span
              style={{
                fontSize: '0.62rem',
                fontWeight: 700,
                padding: '2px 6px',
                borderRadius: '9999px',
                background: 'rgba(255, 255, 255, 0.08)',
                color: '#A1A1AA',
                border: 'none',
                letterSpacing: '0.05em',
              }}
            >
              PRO
            </span>
          </div>
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
                color: solutionsDropdownOpen ? '#FFFFFF' : 'var(--text-secondary)',
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
                  background: '#0D0D11',
                  border: 'none',
                  borderRadius: '16px',
                  padding: '20px',
                  boxShadow: '0 25px 60px rgba(0, 0, 0, 0.85)',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '20px',
                  zIndex: 60,
                }}
              >
                {/* Column 1: Industries */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F6C878', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    AUDIENCES
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {[
                      { title: 'Founders', desc: 'Interview a persona before you build', icon: <Briefcase size={14} color="#F6C878" /> },
                      { title: 'Product & UX research', desc: 'Directional input with labelled attributes', icon: <Layers size={14} color="#F6C878" /> },
                      { title: 'Researchers & students', desc: 'A testbed for multi-model routing', icon: <Building2 size={14} color="#F6C878" /> },
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
                          background: 'rgba(255, 255, 255, 0.03)',
                          border: 'none',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(246, 200, 120, 0.12)', border: 'none' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#FFFFFF' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: '#8E8E93' }}>{item.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Column 2: Use Cases */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F6C878', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '12px' }}>
                    THE LOOP
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {[
                      { title: 'Describe a business', desc: 'Name, industry, target market — no data connection', icon: <Search size={14} color="#3B82F6" /> },
                      { title: 'Generate a persona', desc: 'Grounded, with a class on every attribute', icon: <Lightbulb size={14} color="#3B82F6" /> },
                      { title: 'Interview it', desc: 'Multi-turn, same identity card every turn', icon: <Zap size={14} color="#3B82F6" /> },
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
                          background: 'rgba(255, 255, 255, 0.03)',
                          border: 'none',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(59, 130, 246, 0.12)', border: 'none' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#FFFFFF' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: '#8E8E93' }}>{item.desc}</div>
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
                  background: 'rgba(255, 255, 255, 0.08)',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#FFFFFF',
                  fontSize: '0.84rem',
                  fontWeight: 600,
                }}
              >
                <div
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: '#FFFFFF',
                    color: '#000000',
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
                <ChevronDown size={13} color="#8E8E93" />
              </button>

              {/* User Dropdown */}
              {userDropdownOpen && (
                <div
                  style={{
                    position: 'absolute',
                    top: '40px',
                    right: 0,
                    width: '220px',
                    background: '#0D0D11',
                    borderRadius: '14px',
                    padding: '12px',
                    boxShadow: '0 15px 40px rgba(0, 0, 0, 0.7)',
                    zIndex: 70,
                    border: 'none',
                  }}
                >
                  <div style={{ paddingBottom: '10px', marginBottom: '8px' }}>
                    <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#FFFFFF' }}>
                      {user.full_name}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: '#8E8E93', overflow: 'hidden', textOverflow: 'ellipsis' }}>
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
                      color: '#FFFFFF',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                  >
                    <Activity size={14} color="#F6C878" />
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
                      color: '#EF4444',
                      cursor: 'pointer',
                      textAlign: 'left',
                      marginTop: '4px',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(239, 68, 68, 0.12)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                  >
                    <LogOut size={14} color="#EF4444" />
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
                  color: '#A1A1AA',
                  cursor: 'pointer',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  transition: 'color 0.2s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = '#FFFFFF')}
                onMouseLeave={(e) => (e.currentTarget.style.color = '#A1A1AA')}
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
                  background: '#FFFFFF',
                  color: '#000000',
                  border: 'none',
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#E4E4E7')}
                onMouseLeave={(e) => (e.currentTarget.style.background = '#FFFFFF')}
              >
                <span>Try Free</span>
                <ArrowRight size={14} color="#000000" />
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
            color: '#FFFFFF',
            cursor: 'pointer',
            padding: '8px',
            display: 'none',
          }}
          aria-label="Toggle navigation"
        >
          {mobileMenuOpen ? <X size={22} color="#FFFFFF" /> : <Menu size={22} color="#FFFFFF" />}
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
            background: '#070709',
            border: 'none',
            padding: '24px 32px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            boxShadow: '0 20px 50px rgba(0, 0, 0, 0.9)',
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
            onClick={() => scrollToSection('faq')}
            className="mobile-nav-btn"
          >
            FAQ
          </button>

          <div style={{ height: '1px', background: 'rgba(255, 255, 255, 0.08)', margin: '8px 0' }} />

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
                <Activity size={16} color="#F6C878" />
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
                  background: 'rgba(239, 68, 68, 0.12)',
                  color: '#EF4444',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <LogOut size={16} color="#EF4444" />
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
                  background: '#FFFFFF',
                  color: '#000000',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <span>Try Free</span>
                <ArrowRight size={16} color="#000000" />
              </button>
            </>
          )}
        </div>
      )}
    </header>
  );
};

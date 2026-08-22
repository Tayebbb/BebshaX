import React, { useState, useEffect, useRef } from 'react';
import {
  Menu,
  X,
  ArrowRight,
  Activity,
  ShieldCheck,
  ChevronDown,
  Building2,
  Briefcase,
  Search,
  Lightbulb,
  Zap,
  Layers,
} from 'lucide-react';

interface NavbarProps {
  onOpenApp?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenApp }) => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [solutionsDropdownOpen, setSolutionsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

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
        top: '16px',
        left: 0,
        right: 0,
        zIndex: 50,
        display: 'flex',
        justifyContent: 'center',
        padding: '0 16px',
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: '100%',
          maxWidth: '1240px',
          height: '68px',
          borderRadius: '20px',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: scrolled
            ? 'rgba(255, 255, 255, 0.82)'
            : 'rgba(255, 255, 255, 0.65)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid rgba(255, 255, 255, 0.85)',
          boxShadow: '0 10px 35px rgba(15, 23, 42, 0.08), 0 1px 3px rgba(15, 23, 42, 0.04)',
          transition: 'all 0.3s ease',
        }}
      >
        {/* Brand Logo */}
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
            color: '#0F172A',
          }}
        >
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)',
              position: 'relative',
            }}
          >
            <Activity size={20} color="#FFFFFF" strokeWidth={2.5} />
            <div
              style={{
                position: 'absolute',
                top: '-2px',
                right: '-2px',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: '#60A5FA',
                boxShadow: '0 0 6px #60A5FA',
              }}
            />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.03em', color: '#0F172A' }}>
                Bebsha<span style={{ color: '#2563EB' }}>X</span>
              </span>
              <span
                style={{
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  padding: '2px 6px',
                  borderRadius: '9999px',
                  background: 'rgba(37, 99, 235, 0.1)',
                  color: '#2563EB',
                  border: '1px solid rgba(37, 99, 235, 0.25)',
                  letterSpacing: '0.05em',
                }}
              >
                PRO
              </span>
            </div>
          </div>
        </a>

        {/* Center Desktop Navigation */}
        <nav
          className="desktop-nav"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '32px',
            position: 'relative',
          }}
        >
          <button
            onClick={() => scrollToSection('product')}
            className="nav-link-btn"
          >
            Product
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
                color: solutionsDropdownOpen ? '#2563EB' : '#0F172A',
              }}
            >
              <span>Solutions</span>
              <ChevronDown
                size={14}
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
                className="glass-panel"
                style={{
                  position: 'absolute',
                  top: '40px',
                  left: '-120px',
                  width: '540px',
                  background: 'rgba(255, 255, 255, 0.92)',
                  backdropFilter: 'blur(28px)',
                  WebkitBackdropFilter: 'blur(28px)',
                  border: '1px solid rgba(255, 255, 255, 0.95)',
                  borderRadius: '20px',
                  padding: '24px',
                  boxShadow: '0 20px 50px rgba(15, 23, 42, 0.12), 0 0 1px rgba(15, 23, 42, 0.15)',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '24px',
                  zIndex: 60,
                }}
              >
                {/* Column 1: Industries */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '14px' }}>
                    INDUSTRIES
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {[
                      { title: 'SaaS & Cloud', desc: 'Predictive cohort & churn intelligence', icon: <Layers size={14} color="#2563EB" /> },
                      { title: 'Agencies & Consultancies', desc: 'Evidence-grounded strategy deliverables', icon: <Briefcase size={14} color="#2563EB" /> },
                      { title: 'Commerce & Retail', desc: 'Basket size & checkout optimization', icon: <Building2 size={14} color="#2563EB" /> },
                    ].map((item, i) => (
                      <div
                        key={i}
                        onClick={() => scrollToSection('solutions')}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          padding: '10px',
                          borderRadius: '10px',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background: 'rgba(37, 99, 235, 0.03)',
                          border: '1px solid rgba(37, 99, 235, 0.08)',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(37, 99, 235, 0.08)';
                          e.currentTarget.style.borderColor = 'rgba(37, 99, 235, 0.25)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(37, 99, 235, 0.03)';
                          e.currentTarget.style.borderColor = 'rgba(37, 99, 235, 0.08)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(37, 99, 235, 0.1)' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#0F172A' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: '#64748B' }}>{item.desc}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Column 2: Use Cases */}
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '14px' }}>
                    USE CASES
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {[
                      { title: 'Discover & Map', desc: 'Map hidden operational friction & bottlenecks', icon: <Search size={14} color="#2563EB" /> },
                      { title: 'Validate & Simulate', desc: 'Test business bets before spending', icon: <Lightbulb size={14} color="#2563EB" /> },
                      { title: 'Automate Playbooks', desc: 'Execute multi-step tactical workflows', icon: <Zap size={14} color="#2563EB" /> },
                    ].map((item, i) => (
                      <div
                        key={i}
                        onClick={() => scrollToSection('solutions')}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                          padding: '10px',
                          borderRadius: '10px',
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          background: 'rgba(37, 99, 235, 0.03)',
                          border: '1px solid rgba(37, 99, 235, 0.08)',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background = 'rgba(37, 99, 235, 0.08)';
                          e.currentTarget.style.borderColor = 'rgba(37, 99, 235, 0.25)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'rgba(37, 99, 235, 0.03)';
                          e.currentTarget.style.borderColor = 'rgba(37, 99, 235, 0.08)';
                        }}
                      >
                        <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(37, 99, 235, 0.1)' }}>
                          {item.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#0F172A' }}>{item.title}</div>
                          <div style={{ fontSize: '0.72rem', color: '#64748B' }}>{item.desc}</div>
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
            Intelligence
          </button>
          <button
            onClick={() => scrollToSection('demo')}
            className="nav-link-btn"
          >
            Live Demo
          </button>
          <button
            onClick={() => scrollToSection('faq')}
            className="nav-link-btn"
          >
            FAQ
          </button>
        </nav>

        {/* Right CTA Group */}
        <div
          className="desktop-cta"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <button
            onClick={onOpenApp}
            className="secondary-btn"
            style={{
              padding: '8px 16px',
              fontSize: '0.875rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <ShieldCheck size={16} color="#2563EB" />
            <span>Platform App</span>
          </button>

          <button
            onClick={() => scrollToSection('demo')}
            className="primary-gradient-btn"
            style={{
              padding: '9px 20px',
              fontSize: '0.875rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              border: 'none',
            }}
          >
            <span>Get Started</span>
            <ArrowRight size={15} color="#FFFFFF" />
          </button>
        </div>

        {/* Mobile Hamburger Toggle */}
        <button
          className="mobile-toggle"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          style={{
            background: 'none',
            border: 'none',
            color: '#0F172A',
            cursor: 'pointer',
            padding: '8px',
            display: 'none',
          }}
          aria-label="Toggle navigation"
        >
          {mobileMenuOpen ? <X size={24} color="#2563EB" /> : <Menu size={24} color="#0F172A" />}
        </button>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div
          className="glass-panel"
          style={{
            position: 'absolute',
            top: '76px',
            left: '16px',
            right: '16px',
            background: 'rgba(255, 255, 255, 0.95)',
            backdropFilter: 'blur(28px)',
            WebkitBackdropFilter: 'blur(28px)',
            border: '1px solid rgba(255, 255, 255, 0.9)',
            borderRadius: '20px',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            boxShadow: '0 20px 40px rgba(15, 23, 42, 0.12)',
            zIndex: 60,
          }}
        >
          <button
            onClick={() => scrollToSection('product')}
            className="mobile-nav-btn"
          >
            Product
          </button>
          <button
            onClick={() => scrollToSection('solutions')}
            className="mobile-nav-btn"
          >
            Solutions
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
            Intelligence
          </button>
          <button
            onClick={() => scrollToSection('demo')}
            className="mobile-nav-btn"
          >
            Live Demo
          </button>
          <button
            onClick={() => scrollToSection('faq')}
            className="mobile-nav-btn"
          >
            FAQ
          </button>

          <div style={{ height: '1px', background: 'rgba(15, 23, 42, 0.08)', margin: '8px 0' }} />

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
            }}
          >
            <ShieldCheck size={16} color="#2563EB" />
            <span>Platform Dashboard</span>
          </button>
          <button
            onClick={() => scrollToSection('demo')}
            className="primary-gradient-btn"
            style={{
              padding: '12px',
              fontWeight: 700,
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
            }}
          >
            <span>Get Started</span>
            <ArrowRight size={16} color="#FFFFFF" />
          </button>
        </div>
      )}
    </header>
  );
};

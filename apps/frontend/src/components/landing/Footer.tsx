import React from 'react';
import { Activity, Globe, MessageSquare, Share2 } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer
      className="glass-panel"
      style={{
        margin: '0 16px 24px 16px',
        borderRadius: '28px',
        background: 'rgba(255, 255, 255, 0.72)',
        backdropFilter: 'blur(28px)',
        WebkitBackdropFilter: 'blur(28px)',
        border: '1px solid rgba(255, 255, 255, 0.85)',
        padding: '60px 40px 32px 40px',
        position: 'relative',
        zIndex: 1,
        boxShadow: 'var(--shadow-md)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          maxWidth: '1200px',
          margin: '0 auto',
          position: 'relative',
        }}
      >
        {/* Main Footer Navigation Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '40px',
            marginBottom: '32px',
          }}
        >
          {/* Brand Column */}
          <div style={{ gridColumn: 'span 1' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
              <div
                style={{
                  width: '34px',
                  height: '34px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Activity size={18} color="#FFFFFF" strokeWidth={2.5} />
              </div>
              <span style={{ fontSize: '1.25rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.03em' }}>
                Bebsha<span style={{ color: '#2563EB' }}>X</span>
              </span>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#475569', lineHeight: '1.6', marginBottom: '20px' }}>
              Continuous decision intelligence and evidence-grounded operational telemetry for high-velocity teams.
            </p>

            <div style={{ display: 'flex', gap: '12px' }}>
              <a
                href="#"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'rgba(37, 99, 235, 0.08)',
                  border: '1px solid rgba(37, 99, 235, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#2563EB',
                  transition: 'all 0.2s ease',
                }}
              >
                <Globe size={16} />
              </a>
              <a
                href="#"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'rgba(37, 99, 235, 0.08)',
                  border: '1px solid rgba(37, 99, 235, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#2563EB',
                  transition: 'all 0.2s ease',
                }}
              >
                <MessageSquare size={16} />
              </a>
              <a
                href="#"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'rgba(37, 99, 235, 0.08)',
                  border: '1px solid rgba(37, 99, 235, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#2563EB',
                  transition: 'all 0.2s ease',
                }}
              >
                <Share2 size={16} />
              </a>
            </div>
          </div>

          {/* Nav Column 1 */}
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 800, color: '#0F172A', marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Product
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.88rem' }}>
              <a href="#product" style={{ color: '#475569', textDecoration: 'none' }}>Executive Cockpit</a>
              <a href="#product" style={{ color: '#475569', textDecoration: 'none' }}>Diagnostic Engine</a>
              <a href="#product" style={{ color: '#475569', textDecoration: 'none' }}>Action Playbooks</a>
              <a href="#product" style={{ color: '#475569', textDecoration: 'none' }}>Predictive Forecaster</a>
              <a href="#demo" style={{ color: '#475569', textDecoration: 'none' }}>ROI Simulator</a>
            </div>
          </div>

          {/* Nav Column 2 */}
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 800, color: '#0F172A', marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Solutions
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.88rem' }}>
              <a href="#solutions" style={{ color: '#475569', textDecoration: 'none' }}>Founders & CEOs</a>
              <a href="#solutions" style={{ color: '#475569', textDecoration: 'none' }}>Operations Leads</a>
              <a href="#solutions" style={{ color: '#475569', textDecoration: 'none' }}>Growth & Marketing</a>
              <a href="#solutions" style={{ color: '#475569', textDecoration: 'none' }}>Finance & Strategy</a>
            </div>
          </div>

          {/* Nav Column 3 */}
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 800, color: '#0F172A', marginBottom: '16px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Resources & Legal
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.88rem' }}>
              <a href="#how-it-works" style={{ color: '#475569', textDecoration: 'none' }}>How It Works</a>
              <a href="#faq" style={{ color: '#475569', textDecoration: 'none' }}>Documentation & FAQ</a>
              <a href="#" style={{ color: '#475569', textDecoration: 'none' }}>Privacy Policy</a>
              <a href="#" style={{ color: '#475569', textDecoration: 'none' }}>Terms of Service</a>
              <a href="#" style={{ color: '#475569', textDecoration: 'none' }}>Security & Compliance</a>
            </div>
          </div>
        </div>

        {/* Large Decorative Brand Signature Wordmark */}
        <div
          style={{
            textAlign: 'center',
            overflow: 'hidden',
            userSelect: 'none',
            pointerEvents: 'none',
            padding: '32px 0 20px 0',
            position: 'relative',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          <span className="footer-wordmark">
            Bebsha<span style={{ color: '#2563EB', WebkitTextFillColor: '#2563EB' }}>X</span>
          </span>
        </div>

        {/* Bottom Bar */}
        <div
          style={{
            borderTop: '1px solid rgba(15, 23, 42, 0.08)',
            paddingTop: '24px',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '16px',
            fontSize: '0.82rem',
            color: '#64748B',
          }}
        >
          <div>
            © {new Date().getFullYear()} BebshaX Intelligence Inc. All rights reserved.
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#10B981' }} />
            <span style={{ color: '#0F172A', fontWeight: 600 }}>All Systems Fully Operational</span>
          </div>
        </div>
      </div>
    </footer>
  );
};

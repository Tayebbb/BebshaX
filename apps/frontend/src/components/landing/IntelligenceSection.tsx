import React from 'react';
import {
  Search,
  Brain,
  Zap,
  ArrowRight,
  TrendingDown,
  Sparkles,
} from 'lucide-react';

export const IntelligenceSection: React.FC = () => {
  return (
    <section
      id="intelligence"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
      }}
    >
      <div
        style={{
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {/* Section Header */}
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 64px auto' }}>
          <div
            className="glass-panel"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(37, 99, 235, 0.08)',
              border: '1px solid rgba(37, 99, 235, 0.2)',
              color: '#2563EB',
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            Verifiable Decision Intelligence
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: '#0F172A',
            }}
          >
            Data → Diagnostic Insight →{' '}
            <span className="text-gradient-blue">
              Actionable Playbook.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Unlike generic dashboards that stop at reporting numbers, BebshaX tells you exactly why changes happen and gives you the playbook to respond.
          </p>
        </div>

        {/* Insight Cards Grid in Translucent Glass */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
            position: 'relative',
          }}
        >
          {/* Card 1: Observation */}
          <div
            className="glass-card"
            style={{
              padding: '32px 28px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.68)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              border: '1px solid rgba(255, 255, 255, 0.85)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(37, 99, 235, 0.1)',
                color: '#2563EB',
                border: '1px solid rgba(37, 99, 235, 0.25)',
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Search size={13} />
              <span>1. WHAT IS HAPPENING</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
              <div style={{ padding: '8px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.1)' }}>
                <TrendingDown size={20} color="#DC2626" />
              </div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A' }}>
                Conversion Drop in Tier 2
              </h3>
            </div>

            <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.6', marginBottom: '20px' }}>
              Observed telemetry: Signup-to-paid conversion decreased from <strong style={{ color: '#0F172A' }}>6.2% to 4.1%</strong> among self-serve users over the last 14 days.
            </p>

            <div style={{ padding: '14px', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.8)', border: '1px solid rgba(15, 23, 42, 0.08)', fontSize: '0.78rem', color: '#64748B' }}>
              Data source: PostHog event logs & Stripe billing webhooks (Verified 100% complete)
            </div>
          </div>

          {/* Card 2: Root Cause Diagnosis */}
          <div
            className="glass-card"
            style={{
              padding: '32px 28px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.75)',
              backdropFilter: 'blur(24px)',
              WebkitBackdropFilter: 'blur(24px)',
              border: '1.5px solid rgba(37, 99, 235, 0.35)',
              boxShadow: '0 10px 30px rgba(37, 99, 235, 0.1)',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(59, 130, 246, 0.12)',
                color: '#1D4ED8',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Brain size={13} />
              <span>2. WHY IT IS HAPPENING</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
              <div style={{ padding: '8px', borderRadius: '10px', background: 'rgba(37, 99, 235, 0.1)' }}>
                <Sparkles size={20} color="#2563EB" />
              </div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A' }}>
                Onboarding Step 3 Friction
              </h3>
            </div>

            <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.6', marginBottom: '20px' }}>
              Diagnostic link: 78% of abandoned users stalled at database credential entry. The mandatory TLS cert upload caused 3.8× drop-off compared to previous OAuth flow.
            </p>

            <div style={{ padding: '14px', borderRadius: '12px', background: 'rgba(239, 246, 255, 0.9)', border: '1px solid rgba(191, 219, 254, 0.8)', fontSize: '0.78rem', color: '#2563EB', fontWeight: 600 }}>
              Confidence: 96.4% statistical significance (p &lt; 0.001)
            </div>
          </div>

          {/* Card 3: Actionable Playbook */}
          <div
            className="glass-card"
            style={{
              padding: '32px 28px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.82)',
              backdropFilter: 'blur(28px)',
              WebkitBackdropFilter: 'blur(28px)',
              border: '2px solid #2563EB',
              boxShadow: '0 20px 45px rgba(37, 99, 235, 0.15)',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(37, 99, 235, 0.15)',
                color: '#2563EB',
                border: '1px solid rgba(37, 99, 235, 0.35)',
                fontSize: '0.72rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Zap size={13} />
              <span>3. WHAT TO DO NEXT</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
              <div style={{ padding: '8px', borderRadius: '10px', background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)' }}>
                <Zap size={20} color="#FFFFFF" />
              </div>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A' }}>
                Deploy Fallback Connector
              </h3>
            </div>

            <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.6', marginBottom: '20px' }}>
              Playbook ready: Toggle 1-click cloud connector wizard, defer TLS cert to settings, and trigger re-engagement email to 142 stalled users.
            </p>

            <a
              href="#demo"
              className="primary-hero-btn"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontSize: '0.88rem',
                textDecoration: 'none',
              }}
            >
              <span>Execute Simulated Playbook</span>
              <ArrowRight size={15} color="#FFFFFF" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

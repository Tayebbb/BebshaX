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
        background: '#000000',
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
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: 'none',
              outline: 'none',
              color: '#FFFFFF',
              fontSize: '0.75rem',
              fontWeight: 700,
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
              color: '#FFFFFF',
            }}
          >
            Data → Diagnostic Insight →{' '}
            <span className="text-gradient-blue">
              Actionable Playbook.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Unlike generic dashboards that stop at reporting numbers, BebshaX tells you exactly why changes happen and gives you the playbook to respond.
          </p>
        </div>

        {/* Insight Cards Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '20px',
            position: 'relative',
          }}
        >
          {/* Card 1: Observation */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
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
                color: '#93C5FD',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Search size={12} />
              <span>1. WHAT IS HAPPENING</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', border: 'none' }}>
                <TrendingDown size={18} color="#EF4444" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                Conversion Drop in Tier 2
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              Observed telemetry: Signup-to-paid conversion decreased from <strong style={{ color: '#FFFFFF' }}>6.2% to 4.1%</strong> among self-serve users over the last 14 days.
            </p>

            <div style={{ padding: '12px', borderRadius: '8px', background: '#040406', border: 'none', fontSize: '0.75rem', color: '#71717A' }}>
              Data source: PostHog event logs & Stripe billing webhooks (Verified 100% complete)
            </div>
          </div>

          {/* Card 2: Root Cause Diagnosis */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(168, 85, 247, 0.12)',
                color: '#D8B4FE',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Brain size={12} />
              <span>2. WHY IT IS HAPPENING</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', border: 'none' }}>
                <Sparkles size={18} color="#60A5FA" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                Onboarding Step 3 Friction
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              Diagnostic link: 78% of abandoned users stalled at database credential entry. The mandatory TLS cert upload caused 3.8× drop-off compared to previous OAuth flow.
            </p>

            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.08)', border: 'none', fontSize: '0.75rem', color: '#93C5FD', fontWeight: 500 }}>
              Confidence: 96.4% statistical significance (p &lt; 0.001)
            </div>
          </div>

          {/* Card 3: Actionable Playbook */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#0D0D12',
              border: 'none',
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(246, 200, 120, 0.12)',
                color: '#F6C878',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Zap size={12} />
              <span>3. WHAT TO DO NEXT</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: '#F6C878', border: 'none' }}>
                <Zap size={18} color="#000000" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                Deploy Fallback Connector
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              Playbook ready: Toggle 1-click cloud connector wizard, defer TLS cert to settings, and trigger re-engagement email to 142 stalled users.
            </p>

            <a
              href="#demo"
              className="primary-hero-btn"
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: '9999px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                fontSize: '0.86rem',
                textDecoration: 'none',
                border: 'none',
                outline: 'none',
              }}
            >
              <span>Execute Simulated Playbook</span>
              <ArrowRight size={14} color="#000000" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

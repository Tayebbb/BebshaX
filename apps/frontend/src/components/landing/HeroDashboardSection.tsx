import React from 'react';
import { HeroDashboardPreview } from './HeroDashboardPreview';

export const HeroDashboardSection: React.FC = () => {
  return (
    <section
      id="dashboard-preview"
      style={{
        position: 'relative',
        padding: '100px 0 80px 0',
        zIndex: 1,
        background: 'var(--lp-bg)',
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
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 48px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(var(--lp-fill-rgb), 0.05)',
              color: 'var(--lp-gold)',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            The Console
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: 'var(--lp-text)',
            }}
          >
            Personas, interviews, memory{' '}
            <span className="text-gradient-gold">
              and the routing behind them.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            Read a persona attribute by attribute, see the class behind each one, and follow the exact route the request took to a provider.
          </p>
        </div>

        {/* Persona + Routing Console Preview */}
        <HeroDashboardPreview />
      </div>
    </section>
  );
};

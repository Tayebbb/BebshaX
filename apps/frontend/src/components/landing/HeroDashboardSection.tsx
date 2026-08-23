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
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 48px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#F6C878',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            Live Diagnostic Operations
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
            Real-Time Unified{' '}
            <span className="text-gradient-gold">
              Intelligence Cockpit.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Continuous multi-channel sync diagnosing root causes and generating automated playbooks.
          </p>
        </div>

        {/* The Full Command Center Dashboard View Matching Image 2 */}
        <HeroDashboardPreview />
      </div>
    </section>
  );
};

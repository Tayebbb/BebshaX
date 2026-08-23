import React, { useState } from 'react';
import {
  Users,
  Briefcase,
  DollarSign,
  CheckCircle,
  TrendingUp,
} from 'lucide-react';

export const UseCases: React.FC = () => {
  const [activeRole, setActiveRole] = useState<'founders' | 'ops' | 'growth' | 'finance'>('founders');

  const roles = [
    {
      id: 'founders' as const,
      label: 'Founders & CEOs',
      icon: <Briefcase size={18} />,
      headline: 'A single, trusted heartbeat of the entire business.',
      pain: 'Tired of conflicting answers from different team leads when asking why revenue shifted.',
      gain: 'Instant holistic clarity across churn, cash runway, and expansion velocity without waiting for weekly syncs.',
      metrics: ['100% executive alignment', '4.5 hrs saved weekly', 'Sub-second real-time queries'],
      quote: '"BebshaX gives me executive-level diagnostic clarity in 30 seconds every morning."',
      author: 'David Vance, Founder & CEO at CloudPeak',
    },
    {
      id: 'ops' as const,
      label: 'Operations Leads',
      icon: <Users size={18} />,
      headline: 'Automate manual cross-tool data gathering and reconciliation.',
      pain: 'Spending half of every week manually matching CRM IDs, billing invoices, and support tickets.',
      gain: 'Continuous automated organizational graph that connects all operational signals automatically.',
      metrics: ['Zero manual CSV exports', 'Instant anomaly alerts', 'Pre-built playbooks'],
      quote: '"We eliminated our monthly spreadsheet reconciliation scramble completely."',
      author: 'Sarah Chen, VP Operations at SwiftLogistics',
    },
    {
      id: 'growth' as const,
      label: 'Growth & Marketing',
      icon: <TrendingUp size={18} />,
      headline: 'Attribute real customer lifetime value to actual channels.',
      pain: 'Attribution models relying on last-click data that misdirect performance spend.',
      gain: 'True multi-touch attribution grounded in actual downstream retention and expansion behavior.',
      metrics: ['+28% ROI on paid spend', 'Precise cohort analysis', '1-click re-engagement'],
      quote: '"We reallocated $45k in ad spend based on verified expansion data in week two."',
      author: 'Marcus Brody, Head of Growth at ScaleWave',
    },
    {
      id: 'finance' as const,
      label: 'Finance & Strategy',
      icon: <DollarSign size={18} />,
      headline: 'Predictive scenario planning with verifiable audit trails.',
      pain: 'Board models based on static assumptions that break down when market dynamics shift.',
      gain: 'Live dynamic what-if simulation engine citing exact historical event rows.',
      metrics: ['Deterministic scenario models', 'Full provenance audit trail', 'Faster board prep'],
      quote: '"Audit-ready forecasts with complete provenance. Our board was blown away."',
      author: 'Elena Rostova, CFO at Vertex Holdings',
    },
  ];

  const current = roles.find((r) => r.id === activeRole)!;

  return (
    <section
      id="solutions"
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px auto' }}>
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
            Tailored Solutions
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
            Built for everyone who{' '}
            <span className="text-gradient-blue">
              drives business forward.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Explore how BebshaX solves critical challenges for your specific functional discipline.
          </p>
        </div>

        {/* Role Tab Navigation in Translucent Glass */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '40px',
          }}
        >
          <div
            className="glass-panel"
            style={{
              display: 'inline-flex',
              flexWrap: 'wrap',
              gap: '8px',
              padding: '8px',
              borderRadius: '16px',
              background: 'rgba(255, 255, 255, 0.65)',
              border: '1px solid rgba(255, 255, 255, 0.8)',
            }}
          >
            {roles.map((r) => {
              const isActive = activeRole === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => setActiveRole(r.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 20px',
                    borderRadius: '12px',
                    border: 'none',
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    background: isActive
                      ? 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)'
                      : 'transparent',
                    color: isActive ? '#FFFFFF' : '#475569',
                    boxShadow: isActive ? '0 4px 15px rgba(37, 99, 235, 0.3)' : 'none',
                  }}
                >
                  {React.cloneElement(r.icon, {
                    color: isActive ? '#FFFFFF' : '#2563EB',
                  })}
                  <span>{r.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Role Case Study Card in Multi-Layer White Glass */}
        <div
          className="glass-panel"
          style={{
            borderRadius: '28px',
            background: 'rgba(255, 255, 255, 0.78)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            border: '1px solid rgba(255, 255, 255, 0.9)',
            padding: '40px',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '40px',
              alignItems: 'center',
            }}
          >
            <div>
              <h3
                style={{
                  fontSize: '1.85rem',
                  fontWeight: 800,
                  letterSpacing: '-0.02em',
                  color: '#0F172A',
                  marginBottom: '20px',
                  lineHeight: 1.25,
                }}
              >
                {current.headline}
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '28px' }}>
                <div style={{ padding: '16px', borderRadius: '14px', background: 'rgba(254, 242, 242, 0.8)', border: '1px solid rgba(254, 202, 202, 0.7)' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#DC2626', textTransform: 'uppercase', marginBottom: '4px' }}>
                    THE BOTTLENECK
                  </div>
                  <div style={{ fontSize: '0.88rem', color: '#475569' }}>{current.pain}</div>
                </div>

                <div style={{ padding: '16px', borderRadius: '14px', background: 'rgba(239, 246, 255, 0.9)', border: '1px solid rgba(191, 219, 254, 0.8)' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#2563EB', textTransform: 'uppercase', marginBottom: '4px' }}>
                    THE BEBSHAX GAIN
                  </div>
                  <div style={{ fontSize: '0.88rem', color: '#475569' }}>{current.gain}</div>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                {current.metrics.map((m, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 14px',
                      borderRadius: '8px',
                      background: 'rgba(37, 99, 235, 0.08)',
                      border: '1px solid rgba(37, 99, 235, 0.2)',
                      fontSize: '0.8rem',
                      color: '#0F172A',
                      fontWeight: 600,
                    }}
                  >
                    <CheckCircle size={14} color="#2563EB" />
                    <span>{m}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Testimonial Quote in White Glass */}
            <div
              className="glass-card"
              style={{
                borderRadius: '20px',
                background: 'rgba(255, 255, 255, 0.88)',
                border: '1.5px solid rgba(37, 99, 235, 0.3)',
                padding: '32px',
                boxShadow: '0 20px 45px rgba(15, 23, 42, 0.1)',
              }}
            >
              <div style={{ fontSize: '1.08rem', fontStyle: 'italic', color: '#0F172A', lineHeight: '1.65', marginBottom: '20px' }}>
                {current.quote}
              </div>
              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#2563EB' }}>
                {current.author}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

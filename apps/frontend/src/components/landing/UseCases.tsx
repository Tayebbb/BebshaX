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
      icon: <Briefcase size={16} />,
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
      icon: <Users size={16} />,
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
      icon: <TrendingUp size={16} />,
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
      icon: <DollarSign size={16} />,
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px auto' }}>
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
            Tailored Solutions
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
            Built for everyone who{' '}
            <span className="text-gradient-blue">
              drives business forward.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Explore how BebshaX solves critical challenges for your specific functional discipline.
          </p>
        </div>

        {/* Role Tab Navigation (No outline) */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '36px',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              flexWrap: 'wrap',
              gap: '6px',
              padding: '6px',
              borderRadius: '9999px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
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
                    gap: '6px',
                    padding: '8px 18px',
                    borderRadius: '9999px',
                    border: 'none',
                    outline: 'none',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    background: isActive ? '#FFFFFF' : 'transparent',
                    color: isActive ? '#000000' : '#8E8E93',
                  }}
                >
                  {React.cloneElement(r.icon, {
                    color: isActive ? '#000000' : '#8E8E93',
                  })}
                  <span>{r.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Role Case Study Card (No outline) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '24px',
            background: '#09090C',
            border: 'none',
            outline: 'none',
            padding: '36px',
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
                  fontSize: '1.75rem',
                  fontWeight: 800,
                  letterSpacing: '-0.02em',
                  color: '#FFFFFF',
                  marginBottom: '18px',
                  lineHeight: 1.25,
                }}
              >
                {current.headline}
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
                <div style={{ padding: '14px', borderRadius: '10px', background: 'rgba(239, 68, 68, 0.1)', border: 'none' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F87171', textTransform: 'uppercase', marginBottom: '2px' }}>
                    THE BOTTLENECK
                  </div>
                  <div style={{ fontSize: '0.84rem', color: '#D4D4D8' }}>{current.pain}</div>
                </div>

                <div style={{ padding: '14px', borderRadius: '10px', background: 'rgba(255, 255, 255, 0.04)', border: 'none' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F6C878', textTransform: 'uppercase', marginBottom: '2px' }}>
                    THE BEBSHAX GAIN
                  </div>
                  <div style={{ fontSize: '0.84rem', color: '#D4D4D8' }}>{current.gain}</div>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {current.metrics.map((m, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '5px 12px',
                      borderRadius: '9999px',
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: 'none',
                      fontSize: '0.78rem',
                      color: '#FFFFFF',
                      fontWeight: 500,
                    }}
                  >
                    <CheckCircle size={13} color="#F6C878" />
                    <span>{m}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Testimonial Quote (No outline) */}
            <div
              style={{
                borderRadius: '16px',
                background: '#040406',
                border: 'none',
                outline: 'none',
                padding: '28px',
              }}
            >
              <div style={{ fontSize: '1.02rem', fontStyle: 'italic', color: '#FFFFFF', lineHeight: '1.6', marginBottom: '18px' }}>
                {current.quote}
              </div>
              <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#F6C878' }}>
                {current.author}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

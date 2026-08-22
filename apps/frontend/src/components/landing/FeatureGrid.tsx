import React from 'react';
import {
  ShieldAlert,
  Cpu,
  Layers,
  GitBranch,
  Gauge,
} from 'lucide-react';

export const FeatureGrid: React.FC = () => {
  const features = [
    {
      title: 'Provenance & Verifiability',
      description: 'Every recommendation cites the exact underlying event rows, timestamps, and confidence scores. Zero black-box guesswork.',
      icon: <ShieldAlert size={22} color="#2563EB" />,
      tag: 'Core Reliability',
      span: 'span 7',
    },
    {
      title: 'Continuous Autonomous Sync',
      description: 'Ingests from databases, CRM, billing, and logs in real-time with sub-second change detection.',
      icon: <Cpu size={22} color="#2563EB" />,
      tag: 'Real-time',
      span: 'span 5',
    },
    {
      title: 'Predictive What-If Sandbox',
      description: 'Simulate business decisions before investing capital or making irreversible strategic changes.',
      icon: <Gauge size={22} color="#2563EB" />,
      tag: 'Simulation',
      span: 'span 4',
    },
    {
      title: 'Pre-Built Executive Playbooks',
      description: 'Deploy battle-tested action workflows designed specifically for SaaS, agencies, commerce, and digital operations.',
      icon: <GitBranch size={22} color="#2563EB" />,
      tag: 'Execution',
      span: 'span 4',
    },
    {
      title: 'Multi-Department Unified Model',
      description: 'Unify sales, product, marketing, and finance into one synchronized organizational graph.',
      icon: <Layers size={22} color="#2563EB" />,
      tag: 'Architecture',
      span: 'span 4',
    },
  ];

  return (
    <section
      id="features"
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 64px auto' }}>
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
            Core Capabilities
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
            Built for modern operators who{' '}
            <span className="text-gradient-blue">
              demand precision.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Every feature in BebshaX is engineered to remove guesswork and provide actionable clarity.
          </p>
        </div>

        {/* Bento Grid in Translucent Glass */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(12, 1fr)',
            gap: '20px',
          }}
        >
          {features.map((f, i) => (
            <div
              key={i}
              className="glass-card"
              style={{
                gridColumn: f.span,
                padding: '32px 28px',
                borderRadius: '24px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: 'rgba(255, 255, 255, 0.65)',
                backdropFilter: 'blur(20px)',
                WebkitBackdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.8)',
                boxShadow: 'var(--shadow-sm)',
                minHeight: '220px',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      background: 'rgba(37, 99, 235, 0.1)',
                      border: '1px solid rgba(37, 99, 235, 0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {f.icon}
                  </div>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      padding: '4px 10px',
                      borderRadius: '6px',
                      background: 'rgba(37, 99, 235, 0.08)',
                      color: '#2563EB',
                      border: '1px solid rgba(37, 99, 235, 0.2)',
                    }}
                  >
                    {f.tag}
                  </span>
                </div>

                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A', marginBottom: '8px' }}>
                  {f.title}
                </h3>
              </div>

              <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.6' }}>
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

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
      icon: <ShieldAlert size={20} color="#F6C878" />,
      tag: 'Core Reliability',
      span: 'span 7',
    },
    {
      title: 'Continuous Autonomous Sync',
      description: 'Ingests from databases, CRM, billing, and logs in real-time with sub-second change detection.',
      icon: <Cpu size={20} color="#FFFFFF" />,
      tag: 'Real-time',
      span: 'span 5',
    },
    {
      title: 'Predictive What-If Sandbox',
      description: 'Simulate business decisions before investing capital or making irreversible strategic changes.',
      icon: <Gauge size={20} color="#F6C878" />,
      tag: 'Simulation',
      span: 'span 4',
    },
    {
      title: 'Pre-Built Executive Playbooks',
      description: 'Deploy battle-tested action workflows designed specifically for SaaS, agencies, commerce, and digital operations.',
      icon: <GitBranch size={20} color="#FFFFFF" />,
      tag: 'Execution',
      span: 'span 4',
    },
    {
      title: 'Multi-Department Unified Model',
      description: 'Unify sales, product, marketing, and finance into one synchronized organizational graph.',
      icon: <Layers size={20} color="#F6C878" />,
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 64px auto' }}>
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
            Core Capabilities
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
            Built for modern operators who{' '}
            <span className="text-gradient-blue">
              demand precision.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Every feature in BebshaX is engineered to remove guesswork and provide actionable clarity.
          </p>
        </div>

        {/* Bento Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(12, 1fr)',
            gap: '16px',
          }}
        >
          {features.map((f, i) => (
            <div
              key={i}
              className="clean-card"
              style={{
                gridColumn: f.span,
                padding: '32px 28px',
                borderRadius: '18px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: '#09090C',
                border: 'none',
                outline: 'none',
                minHeight: '200px',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div
                    style={{
                      width: '38px',
                      height: '38px',
                      borderRadius: '10px',
                      background: 'rgba(255, 255, 255, 0.04)',
                      border: 'none',
                      outline: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {f.icon}
                  </div>
                  <span
                    style={{
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      padding: '4px 10px',
                      borderRadius: '9999px',
                      background: 'rgba(255, 255, 255, 0.05)',
                      color: '#A1A1AA',
                      border: 'none',
                      outline: 'none',
                    }}
                  >
                    {f.tag}
                  </span>
                </div>

                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '6px' }}>
                  {f.title}
                </h3>
              </div>

              <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6' }}>
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

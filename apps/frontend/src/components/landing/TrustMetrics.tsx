import React from 'react';
import { Database, Eye, Zap, Clock } from 'lucide-react';

export const TrustMetrics: React.FC = () => {
  const metrics = [
    {
      value: '10K+',
      label: 'Businesses Analyzed',
      description: 'Operations modeled across retail, SaaS, logistics, and fintech.',
      icon: <Database size={22} color="#2563EB" />,
    },
    {
      value: '98%',
      label: 'Data Visibility',
      description: 'Silos eliminated by consolidating all business streams into one view.',
      icon: <Eye size={22} color="#2563EB" />,
    },
    {
      value: '3.2×',
      label: 'Faster Decision Making',
      description: 'Average speedup in identifying and executing operational playbooks.',
      icon: <Zap size={22} color="#2563EB" />,
    },
    {
      value: '24/7',
      label: 'Continuous Monitoring',
      description: 'Autonomous health checks alerting you before revenue leaks occur.',
      icon: <Clock size={22} color="#2563EB" />,
    },
  ];

  const partners = [
    'NEXUS LOGISTICS',
    'APEX GLOBAL',
    'VELOCITY RETAIL',
    'CLOUDSTACK',
    'SYNAPSE CAPITAL',
  ];

  return (
    <section
      style={{
        position: 'relative',
        padding: '60px 0 80px 0',
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
        {/* Metric Cards Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '20px',
            marginBottom: '64px',
          }}
        >
          {metrics.map((m, idx) => (
            <div
              key={idx}
              className="glass-card"
              style={{
                padding: '28px 24px',
                borderRadius: '20px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: 'rgba(255, 255, 255, 0.65)',
                backdropFilter: 'blur(20px)',
                WebkitBackdropFilter: 'blur(20px)',
                border: '1px solid rgba(255, 255, 255, 0.8)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div
                style={{
                  width: '46px',
                  height: '46px',
                  borderRadius: '12px',
                  background: 'rgba(37, 99, 235, 0.1)',
                  border: '1px solid rgba(37, 99, 235, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '20px',
                }}
              >
                {m.icon}
              </div>

              <div>
                <div
                  style={{
                    fontSize: '2.4rem',
                    fontWeight: 800,
                    letterSpacing: '-0.03em',
                    color: '#0F172A',
                    marginBottom: '4px',
                  }}
                >
                  {m.value}
                </div>
                <div
                  style={{
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color: '#2563EB',
                    marginBottom: '8px',
                  }}
                >
                  {m.label}
                </div>
                <p
                  style={{
                    fontSize: '0.84rem',
                    color: '#475569',
                    lineHeight: '1.5',
                  }}
                >
                  {m.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Partner Logos Bar */}
        <div
          className="glass-panel"
          style={{
            textAlign: 'center',
            padding: '32px 24px',
            borderRadius: '20px',
            background: 'rgba(255, 255, 255, 0.45)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.7)',
          }}
        >
          <p
            style={{
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: '#2563EB',
              marginBottom: '20px',
            }}
          >
            TRUSTED BY FORWARD-THINKING LEADERSHIP TEAMS
          </p>

          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '40px',
            }}
          >
            {partners.map((p, i) => (
              <span
                key={i}
                style={{
                  fontSize: '0.9rem',
                  fontWeight: 800,
                  letterSpacing: '0.08em',
                  color: '#475569',
                }}
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

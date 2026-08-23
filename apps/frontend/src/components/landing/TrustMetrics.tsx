import React from 'react';
import { Database, Eye, Zap, Clock } from 'lucide-react';

export const TrustMetrics: React.FC = () => {
  const metrics = [
    {
      value: '10K+',
      label: 'Businesses Analyzed',
      description: 'Operations modeled across retail, SaaS, logistics, and fintech.',
      icon: <Database size={20} color="#FFFFFF" />,
    },
    {
      value: '98%',
      label: 'Data Visibility',
      description: 'Silos eliminated by consolidating all business streams into one view.',
      icon: <Eye size={20} color="#FFFFFF" />,
    },
    {
      value: '3.2×',
      label: 'Faster Decision Making',
      description: 'Average speedup in identifying and executing operational playbooks.',
      icon: <Zap size={20} color="#F6C878" />,
    },
    {
      value: '24/7',
      label: 'Continuous Monitoring',
      description: 'Autonomous health checks alerting you before revenue leaks occur.',
      icon: <Clock size={20} color="#FFFFFF" />,
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
        {/* Metric Cards Grid (No outlines / borders) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '16px',
            marginBottom: '48px',
          }}
        >
          {metrics.map((m, idx) => (
            <div
              key={idx}
              className="clean-card"
              style={{
                padding: '28px 24px',
                borderRadius: '16px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                background: '#09090C',
                border: 'none',
                outline: 'none',
              }}
            >
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '10px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: 'none',
                  outline: 'none',
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
                    fontSize: '2.2rem',
                    fontWeight: 800,
                    letterSpacing: '-0.03em',
                    color: '#FFFFFF',
                    marginBottom: '4px',
                  }}
                >
                  {m.value}
                </div>
                <div
                  style={{
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    color: '#F6C878',
                    marginBottom: '6px',
                  }}
                >
                  {m.label}
                </div>
                <p
                  style={{
                    fontSize: '0.82rem',
                    color: '#8E8E93',
                    lineHeight: '1.5',
                  }}
                >
                  {m.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Partner Logos Bar (Minimal, no harsh outline) */}
        <div
          style={{
            textAlign: 'center',
            padding: '24px',
          }}
        >
          <p
            style={{
              fontSize: '0.72rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: '#71717A',
              marginBottom: '18px',
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
                  fontSize: '0.84rem',
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  color: '#52525B',
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

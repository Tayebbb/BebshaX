import React from 'react';
import { Database, Eye, Zap, Clock } from 'lucide-react';

export const TrustMetrics: React.FC = () => {
  const metrics = [
    {
      value: '7',
      label: 'Routing pools',
      description: 'Sixteen fixed task types map onto reasoning, conversation, long_context, structured, fast, local and emergency.',
      icon: <Database size={20} color="#FFFFFF" />,
    },
    {
      value: '3',
      label: 'Provenance classes',
      description: 'Every persona attribute is OBSERVED, INFERRED or SYNTHETIC. Classes are enforced in code and only ever downgraded.',
      icon: <Eye size={20} color="#FFFFFF" />,
    },
    {
      value: '14',
      label: 'Failure kinds',
      description: 'A closed taxonomy. Each kind has one policy: retry the route once, advance to the next candidate, or cool the route.',
      icon: <Zap size={20} color="#F6C878" />,
    },
    {
      value: '0',
      label: 'API keys to start',
      description: 'Keyless free provider tiers work out of the box, and every pool terminates at a local Ollama model.',
      icon: <Clock size={20} color="#FFFFFF" />,
    },
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
      </div>
    </section>
  );
};

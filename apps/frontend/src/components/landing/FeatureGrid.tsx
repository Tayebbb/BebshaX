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
      title: 'Per-attribute provenance, enforced in code',
      description: 'Every attribute is OBSERVED, INFERRED or SYNTHETIC. Fabricated citations are stripped and the attribute is downgraded. A class can only ever move down, never up.',
      icon: <ShieldAlert size={20} color="var(--lp-gold)" />,
      tag: 'Grounding',
      span: 'span 7',
    },
    {
      title: 'Never truncate context',
      description: 'Persona identity, memory and evidence are never compressed to fit a smaller model. If nothing in the pool can hold the request, it fails with ContextWindowExceeded.',
      icon: <Cpu size={20} color="var(--lp-text)" />,
      tag: 'Explicit failure',
      span: 'span 5',
    },
    {
      title: 'A closed failure taxonomy',
      description: 'Thirteen failure kinds, each with one policy: retry the route once, advance, or cool it for 60 seconds per provider and model.',
      icon: <Gauge size={20} color="var(--lp-gold)" />,
      tag: 'Routing',
      span: 'span 4',
    },
    {
      title: 'Fallback that ends on your machine',
      description: 'Every pool terminates at the local Ollama adapter, and the emergency pool is local-first.',
      icon: <GitBranch size={20} color="var(--lp-text)" />,
      tag: 'Local',
      span: 'span 4',
    },
    {
      title: 'Stable identity across turns',
      description: 'The persona is never rebuilt mid-interview. The identity card is byte-identical on every turn, and a test enforces that.',
      icon: <Layers size={20} color="var(--lp-gold)" />,
      tag: 'Interviews',
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 64px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(var(--lp-fill-rgb), 0.05)',
              border: 'none',
              outline: 'none',
              color: 'var(--lp-text)',
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
              color: 'var(--lp-text)',
            }}
          >
            Built so the failure modes are{' '}
            <span className="text-gradient-blue">
              loud, not silent.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            The guarantees below are enforced in code and covered by tests, not stated as intentions.
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
                background: 'var(--lp-surface)',
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
                      background: 'rgba(var(--lp-fill-rgb), 0.04)',
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
                      background: 'rgba(var(--lp-fill-rgb), 0.05)',
                      color: 'var(--lp-text-dim)',
                      border: 'none',
                      outline: 'none',
                    }}
                  >
                    {f.tag}
                  </span>
                </div>

                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--lp-text)', marginBottom: '6px' }}>
                  {f.title}
                </h3>
              </div>

              <p style={{ fontSize: '0.85rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
                {f.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

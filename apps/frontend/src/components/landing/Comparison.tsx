import React from 'react';
import { Check, X, Sparkles } from 'lucide-react';

export const Comparison: React.FC = () => {
  const criteria = [
    {
      feature: 'Context handling',
      bebshax: 'Never truncated — explicit ContextWindowExceeded when nothing fits',
      traditional: 'Silently trimmed or dropped to fit the model in hand',
    },
    {
      feature: 'Failure handling',
      bebshax: '14 classified kinds, one policy each: retry, advance, or cool the route',
      traditional: 'One error path — raise it, or blindly try the next key',
    },
    {
      feature: 'Route cooldown',
      bebshax: '60 seconds per provider and model, skipped then returned automatically',
      traditional: 'Rate-limited routes stay in rotation and keep failing',
    },
    {
      feature: 'Provenance',
      bebshax: 'Per attempt: provider, model, latency, failure kind, fallback reason, routing path',
      traditional: 'No record of which provider answered or why',
    },
    {
      feature: 'Identity stability',
      bebshax: 'Byte-identical identity card on every interview turn',
      traditional: 'Persona rebuilt per turn and free to drift',
    },
    {
      feature: 'Local fallback',
      bebshax: 'Every pool terminates on-machine; the emergency pool is local-first',
      traditional: 'Nothing left to try once the remote tier is exhausted',
    },
  ];

  return (
    <section
      id="comparison"
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
            The Policy Layer
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
            One key and a retry loop{' '}
            <span className="text-gradient-blue">
              is not a routing layer.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            What changes when the fallback path is a data table of pools and policies instead of a try/except around a single provider.
          </p>
        </div>

        {/* Table Container (No outer border/outline) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '20px',
            background: 'var(--lp-surface)',
            border: 'none',
            outline: 'none',
            overflow: 'hidden',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: 'var(--lp-text-muted)', fontWeight: 600, width: '28%' }}>
                    Capability
                  </th>
                  <th
                    style={{
                      padding: '20px 24px',
                      fontSize: '0.95rem',
                      color: 'var(--lp-text)',
                      fontWeight: 800,
                      background: 'rgba(var(--lp-fill-rgb), 0.04)',
                      width: '38%',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Sparkles size={16} color="var(--lp-gold)" />
                      <span>BebshaX policy layer</span>
                    </div>
                  </th>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: 'var(--lp-text-muted)', fontWeight: 500, width: '34%' }}>
                    A single free API key, or naive round-robin rotation
                  </th>
                </tr>
              </thead>
              <tbody>
                {criteria.map((c, i) => (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? 'transparent' : 'rgba(var(--lp-fill-rgb), 0.015)',
                    }}
                  >
                    <td style={{ padding: '18px 24px', fontWeight: 600, color: 'var(--lp-text)', fontSize: '0.88rem' }}>
                      {c.feature}
                    </td>
                    <td
                      style={{
                        padding: '18px 24px',
                        background: 'rgba(var(--lp-fill-rgb), 0.03)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ width: '20px', height: '20px', borderRadius: '50%', background: 'var(--lp-contrast-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: 'none' }}>
                          <Check size={12} color="var(--lp-contrast-fg)" strokeWidth={3} />
                        </div>
                        <span style={{ fontSize: '0.85rem', color: 'var(--lp-text)', fontWeight: 600 }}>{c.bebshax}</span>
                      </div>
                    </td>
                    <td style={{ padding: '18px 24px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ width: '20px', height: '20px', borderRadius: '50%', background: 'rgba(var(--lp-fill-rgb), 0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: 'none' }}>
                          <X size={12} color="var(--lp-text-faint)" />
                        </div>
                        <span style={{ fontSize: '0.85rem', color: 'var(--lp-text-faint)' }}>{c.traditional}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
};

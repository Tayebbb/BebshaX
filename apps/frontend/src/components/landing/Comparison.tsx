import React from 'react';
import { Check, X, Sparkles } from 'lucide-react';

export const Comparison: React.FC = () => {
  const criteria = [
    {
      feature: 'Your persona gets complicated',
      bebshax: 'You get the whole persona, or an honest error. Never a quietly shortened one',
      detail: 'Identity, memory and evidence are never compressed to fit a smaller model; the call fails with ContextWindowExceeded instead.',
      traditional: 'Details are silently trimmed to fit whatever model is free right now',
    },
    {
      feature: 'An AI provider goes down',
      bebshax: 'It moves to another model and keeps going. You barely notice',
      detail: '13 classified failure kinds, one policy each: retry the route once, advance to the next candidate, or cool the route.',
      traditional: 'The request fails, or it retries the same broken route',
    },
    {
      feature: 'A provider hits its free limit',
      bebshax: 'That route steps aside and comes back on its own',
      detail: '60-second cooldown per provider and model; cooling routes are skipped, then returned automatically.',
      traditional: 'The rate-limited route stays in rotation and keeps failing',
    },
    {
      feature: 'You ask "where did this come from?"',
      bebshax: 'Every answer records which AI answered it, how long it took, and what it tried first',
      detail: 'A provenance record per attempt: provider, model, latency, failure kind, fallback reason, routing path.',
      traditional: 'No record of which provider answered, or why',
    },
    {
      feature: 'A long interview goes on',
      bebshax: 'The persona is the same person on turn one and on turn twenty',
      detail: 'The identity card is byte-identical every turn, and a test enforces it.',
      traditional: 'The persona is rebuilt each turn and quietly drifts',
    },
    {
      feature: 'Every free provider is exhausted',
      bebshax: 'It falls back to a model on your own machine and still answers',
      detail: 'Every pool terminates at the local Ollama adapter, and the emergency pool is local-first.',
      traditional: 'Nothing left to try once the free tier runs out',
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
          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: 'var(--lp-text)',
            }}
          >
            When the AI fails,{' '}
            <span className="text-gradient-blue">
              you should still get an answer.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            Free AI models are unreliable. Here is what happens on a bad day with BebshaX, and what happens with a tool wired to a single provider.
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
          <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
            <table style={{ width: '100%', minWidth: '600px', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: 'var(--lp-text-muted)', fontWeight: 600, width: '28%' }}>
                    What happens when…
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
                      <span>With BebshaX</span>
                    </div>
                  </th>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: 'var(--lp-text-muted)', fontWeight: 500, width: '34%' }}>
                    With a tool wired to one free API key
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
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                        <div style={{ width: '20px', height: '20px', borderRadius: '50%', background: 'var(--lp-contrast-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: 'none', marginTop: '1px' }}>
                          <Check size={12} color="var(--lp-contrast-fg)" strokeWidth={3} />
                        </div>
                        <div>
                          <div style={{ fontSize: '0.85rem', color: 'var(--lp-text)', fontWeight: 600 }}>{c.bebshax}</div>
                          <div style={{ fontSize: '0.76rem', color: 'var(--lp-text-faint)', marginTop: '5px', lineHeight: 1.45 }}>{c.detail}</div>
                        </div>
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

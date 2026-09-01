import React, { useState } from 'react';
import {
  Users,
  Briefcase,
  Wallet,
  CheckCircle,
  GraduationCap,
} from 'lucide-react';

export const UseCases: React.FC = () => {
  const [activeRole, setActiveRole] = useState<'founders' | 'researchers' | 'students' | 'nobudget'>('founders');

  const roles = [
    {
      id: 'founders' as const,
      label: 'Founders',
      icon: <Briefcase size={16} />,
      headline: 'Interview your customers before you build for them.',
      pain: 'Validating an idea normally means recruiting and scheduling real interviews first.',
      gain: 'Describe the idea in plain English, let the copilot sharpen the question, generate the personas, and interview them the same day.',
      metrics: ['Start from one sentence, not a form', 'A guided 5-step study', 'No data connection required'],
      detail: 'You never connect your own data. The input is a conversation with the Study Design Copilot about what you want to find out.',
    },
    {
      id: 'researchers' as const,
      label: 'Product & UX research',
      icon: <Users size={16} />,
      headline: 'Directional input where every attribute is labelled.',
      pain: 'An ungrounded persona reads convincingly and hides which traits are actually supported.',
      gain: 'Each attribute is OBSERVED, INFERRED or SYNTHETIC, so you can read the persona and its confidence at the same time.',
      metrics: ['3 provenance classes', 'idf-weighted evidence retrieval', 'Downgrade-only classification'],
      detail: 'Fabricated citations are stripped in code and the attribute is downgraded. Classes never move up.',
    },
    {
      id: 'students' as const,
      label: 'Researchers & students',
      icon: <GraduationCap size={16} />,
      headline: 'A working testbed for multi-model routing.',
      pain: 'Studying routing usually means building the whole harness before you can measure anything.',
      gain: 'Seven routing strategies can be compared offline, and replay evaluation runs against RouterArena and xRouteBench.',
      metrics: ['HYBRID, ROUND_ROBIN, LEAST_USED', 'QUALITY_FIRST, LATENCY_FIRST', 'CAPABILITY_FIRST, QUOTA_AWARE'],
      detail: 'Datasets are used for grounding and evaluation only. No fine-tuning, ever — that is an explicit project rule.',
    },
    {
      id: 'nobudget' as const,
      label: 'No API budget',
      icon: <Wallet size={16} />,
      headline: 'Zero API keys is a supported configuration.',
      pain: 'Most persona tooling assumes you already pay for a frontier model.',
      gain: 'Keyless free provider tiers work out of the box, and every pool terminates at a local Ollama model.',
      metrics: ['Keyless start', 'Local model as final fallback', 'Emergency pool is local-first'],
      detail: 'The freellmpool adapter aggregates the free provider catalog behind one API — roughly 18–24 providers and 200+ routes, depending on the catalog version.',
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px auto' }}>
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
            Who It Is For
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
            Built for people who need{' '}
            <span className="text-gradient-blue">
              a persona today.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            Four ways the same loop — describe, generate, interview — gets used.
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
              background: 'var(--lp-surface)',
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
                    background: isActive ? 'var(--lp-contrast-bg)' : 'transparent',
                    color: isActive ? 'var(--lp-contrast-fg)' : 'var(--lp-text-muted)',
                  }}
                >
                  {React.cloneElement(r.icon, {
                    color: isActive ? 'var(--lp-contrast-fg)' : 'var(--lp-text-muted)',
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
            background: 'var(--lp-surface)',
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
                  color: 'var(--lp-text)',
                  marginBottom: '18px',
                  lineHeight: 1.25,
                }}
              >
                {current.headline}
              </h3>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '24px' }}>
                <div style={{ padding: '14px', borderRadius: '10px', background: 'rgba(var(--lp-red-rgb), 0.1)', border: 'none' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--lp-red-soft)', textTransform: 'uppercase', marginBottom: '2px' }}>
                    THE PROBLEM
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--lp-text-hi)' }}>{current.pain}</div>
                </div>

                <div style={{ padding: '14px', borderRadius: '10px', background: 'rgba(var(--lp-fill-rgb), 0.04)', border: 'none' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--lp-gold)', textTransform: 'uppercase', marginBottom: '2px' }}>
                    WHAT BEBSHAX DOES
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--lp-text-hi)' }}>{current.gain}</div>
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
                      background: 'rgba(var(--lp-fill-rgb), 0.04)',
                      border: 'none',
                      fontSize: '0.78rem',
                      color: 'var(--lp-text)',
                      fontWeight: 500,
                    }}
                  >
                    <CheckCircle size={13} color="var(--lp-gold)" />
                    <span>{m}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Supporting Detail Panel (No outline) */}
            <div
              style={{
                borderRadius: '16px',
                background: 'var(--lp-inset)',
                border: 'none',
                outline: 'none',
                padding: '28px',
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--lp-gold)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                HOW IT WORKS
              </div>
              <div style={{ fontSize: '1.02rem', color: 'var(--lp-text)', lineHeight: '1.6' }}>
                {current.detail}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

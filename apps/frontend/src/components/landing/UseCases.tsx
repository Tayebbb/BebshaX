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
      headline: 'Interview a persona for your idea before you build it.',
      pain: 'Validating an idea normally means recruiting and scheduling real interviews first.',
      gain: 'Describe the business, generate a grounded persona, and interview it in a multi-turn conversation the same day.',
      metrics: ['Name, description, industry, target market', 'Optional audience segment', 'No data connection required'],
      detail: 'Input is a business description and nothing else. There is no data connection of any kind.',
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
      detail: 'The freellmpool adapter aggregates roughly 18–24 free providers and 200+ routes behind one API.',
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
            Who It Is For
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
            Built for people who need{' '}
            <span className="text-gradient-blue">
              a persona today.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
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
                    THE PROBLEM
                  </div>
                  <div style={{ fontSize: '0.84rem', color: '#D4D4D8' }}>{current.pain}</div>
                </div>

                <div style={{ padding: '14px', borderRadius: '10px', background: 'rgba(255, 255, 255, 0.04)', border: 'none' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F6C878', textTransform: 'uppercase', marginBottom: '2px' }}>
                    WHAT BEBSHAX DOES
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

            {/* Supporting Detail Panel (No outline) */}
            <div
              style={{
                borderRadius: '16px',
                background: '#040406',
                border: 'none',
                outline: 'none',
                padding: '28px',
              }}
            >
              <div style={{ fontSize: '0.72rem', fontWeight: 800, color: '#F6C878', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
                HOW IT WORKS
              </div>
              <div style={{ fontSize: '1.02rem', color: '#FFFFFF', lineHeight: '1.6' }}>
                {current.detail}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

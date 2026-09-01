import React from 'react';
import {
  FileSpreadsheet,
  AlertOctagon,
  HelpCircle,
  Hourglass,
  Sparkles,
  CheckCircle,
  XCircle,
} from 'lucide-react';

export const ProblemSection: React.FC = () => {
  const problems = [
    {
      icon: <Hourglass size={18} color="var(--lp-red)" />,
      title: 'Real user research is slow and expensive',
      description: 'Recruiting, scheduling, and running interviews takes weeks before you learn anything directional.',
    },
    {
      icon: <HelpCircle size={18} color="var(--lp-red)" />,
      title: 'LLM personas drift between turns',
      description: 'Rebuild the persona on every turn and its identity quietly changes underneath the conversation.',
    },
    {
      icon: <FileSpreadsheet size={18} color="var(--lp-red)" />,
      title: 'Ungrounded personas invent their evidence',
      description: 'A model asked to justify an attribute will happily fabricate a citation for it.',
    },
    {
      icon: <AlertOctagon size={18} color="var(--lp-red)" />,
      title: 'Free provider tiers are unreliable',
      description: 'Rate limits, timeouts, and models disappearing mid-request break a naive single-provider setup.',
    },
  ];

  return (
    <section
      id="problem"
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
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 64px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(var(--lp-red-rgb), 0.1)',
              border: 'none',
              outline: 'none',
              color: 'var(--lp-red-soft)',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            What Makes Synthetic Personas Hard
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
            Asking a model for a persona is easy.{' '}
            <span className="text-gradient-red">
              Getting a stable, grounded one is not.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            A persona is only useful if it stays the same person across a conversation and if you can tell which of its traits are backed by evidence.
          </p>
        </div>

        {/* Comparison Block (No Outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
          }}
        >
          {/* Old Way Card */}
          <div
            className="clean-card"
            style={{
              padding: '36px 32px',
              borderRadius: '20px',
              background: 'var(--lp-surface)',
              border: 'none',
              outline: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'rgba(var(--lp-red-rgb), 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: 'none',
                }}
              >
                <XCircle size={18} color="var(--lp-red)" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--lp-text)' }}>
                The Unguarded Approach
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {problems.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(var(--lp-red-rgb), 0.08)', border: 'none' }}>
                    {p.icon}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--lp-text)', marginBottom: '3px' }}>
                      {p.title}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--lp-text-muted)', lineHeight: '1.5' }}>
                      {p.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* BebshaX Unified Solution Card */}
          <div
            className="clean-card"
            style={{
              padding: '36px 32px',
              borderRadius: '20px',
              background: 'var(--lp-surface-2)',
              border: 'none',
              outline: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'var(--lp-gold-bg)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: 'none',
                }}
              >
                <CheckCircle size={18} color="#000000" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--lp-text)' }}>
                The BebshaX Advantage
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {[
                {
                  title: 'An immutable identity card',
                  desc: 'The persona is never rebuilt between turns. The identity card is byte-identical on every turn, and a test enforces that.',
                },
                {
                  title: 'Provenance enforced in code',
                  desc: 'Fabricated citations are stripped and the attribute is downgraded. A class can only ever move down, never up.',
                },
                {
                  title: 'Deterministic consistency rules',
                  desc: 'Occupation against minimum plausible age, income markers against luxury markers, location against timezone. Errors block storage.',
                },
                {
                  title: 'A closed failure taxonomy',
                  desc: 'Thirteen failure kinds, each with one policy — retry, advance, or cool the route — and every pool ends at a local model.',
                },
              ].map((adv, idx) => (
                <div key={idx} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <div
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      background: 'rgba(var(--lp-gold-rgb), 0.12)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: '2px',
                      border: 'none',
                    }}
                  >
                    <Sparkles size={13} color="var(--lp-gold)" />
                  </div>
                  <div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--lp-text)', marginBottom: '3px' }}>
                      {adv.title}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--lp-text-muted)', lineHeight: '1.5' }}>
                      {adv.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

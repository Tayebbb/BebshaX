import React from 'react';
import {
  Search,
  Brain,
  Zap,
  ArrowRight,
  TrendingDown,
  Sparkles,
} from 'lucide-react';

export const IntelligenceSection: React.FC = () => {
  return (
    <section
      id="intelligence"
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
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 64px auto' }}>
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
            The Routing Layer
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
            Task → pool →{' '}
            <span className="text-gradient-blue">
              a local model, always.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Every LLM call goes through one entry point with an explicit task type. No model classifies the task — the application always declares it.
          </p>
        </div>

        {/* Insight Cards Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '20px',
            position: 'relative',
          }}
        >
          {/* Card 1: Observation */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(59, 130, 246, 0.12)',
                color: '#93C5FD',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Search size={12} />
              <span>1. WHERE THE CALL GOES</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', border: 'none' }}>
                <TrendingDown size={18} color="#60A5FA" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                16 task types, 7 pools
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              Each task type maps to one pool, and the ordering inside a pool is a <strong style={{ color: '#FFFFFF' }}>preference order</strong>. Every pool ends at the local adapter, so fallback terminates on-machine. The emergency pool is local-first.
            </p>

            <div style={{ padding: '12px', borderRadius: '8px', background: '#040406', border: 'none', fontSize: '0.75rem', color: '#71717A' }}>
              Grounding sources: PersonaHub, Google Synthetic-Persona-Chat, EmpatheticDialogues, an Amazon Reviews slice, MMLU and GSM8K micro slices, RouterArena, xRouteBench
            </div>
          </div>

          {/* Card 2: Failure Classification */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(168, 85, 247, 0.12)',
                color: '#D8B4FE',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Brain size={12} />
              <span>2. WHEN A PROVIDER FAILS</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', border: 'none' }}>
                <Sparkles size={18} color="#60A5FA" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                14 failure kinds, one policy each
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              The failure is classified, then the policy applies: retry the same route once, advance to the next candidate, or put the route on cooldown. Low answer quality is never treated as an infrastructure failure — quality belongs to the evaluation layer.
            </p>

            <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.08)', border: 'none', fontSize: '0.75rem', color: '#93C5FD', fontWeight: 500 }}>
              Cooldown: 60 seconds, in-memory, per provider and model. Cooling routes are skipped and return automatically.
            </div>
          </div>

          {/* Card 3: Explicit Failure */}
          <div
            className="clean-card"
            style={{
              padding: '32px 28px',
              borderRadius: '18px',
              background: '#0D0D12',
              border: 'none',
              outline: 'none',
            }}
          >
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '6px',
                background: 'rgba(246, 200, 120, 0.12)',
                color: '#F6C878',
                border: 'none',
                outline: 'none',
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                marginBottom: '20px',
              }}
            >
              <Zap size={12} />
              <span>3. WHEN NOTHING FITS</span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '8px', background: '#F6C878', border: 'none' }}>
                <Zap size={18} color="#000000" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                ContextWindowExceeded
              </h3>
            </div>

            <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
              Context is never truncated to fit a smaller model. If nothing in the pool can hold the request, it fails explicitly instead of quietly dropping persona identity, memory, or evidence.
            </p>

            <a
              href="#demo"
              className="primary-hero-btn"
              style={{
                width: '100%',
                padding: '10px',
                borderRadius: '9999px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                fontSize: '0.86rem',
                textDecoration: 'none',
                border: 'none',
                outline: 'none',
              }}
            >
              <span>See the task-to-pool map</span>
              <ArrowRight size={14} color="#000000" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};

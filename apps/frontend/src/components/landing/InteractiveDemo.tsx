import React, { useState } from 'react';
import {
  Sliders,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import { useNavigation } from '../../context/NavigationContext';

interface PoolInfo {
  pool: string;
  limit: number;
  candidates: string;
}

const POOLS: Record<string, PoolInfo> = {
  reasoning: { pool: 'reasoning', limit: 2, candidates: 'freellmpool → ollama (local)' },
  conversation: { pool: 'conversation', limit: 5, candidates: 'freellmpool → ollama (local)' },
  structured: { pool: 'structured', limit: 3, candidates: 'freellmpool → ollama (local)' },
  fast: { pool: 'fast', limit: 5, candidates: 'freellmpool → ollama (local)' },
  long_context: { pool: 'long_context', limit: 2, candidates: 'freellmpool → ollama (local)' },
  emergency: { pool: 'emergency', limit: 2, candidates: 'ollama (local) → freellmpool' },
};

const TASK_TYPES: { task: string; pool: keyof typeof POOLS }[] = [
  { task: 'PERSONA_GENERATION', pool: 'reasoning' },
  { task: 'PERSONA_REFINEMENT', pool: 'reasoning' },
  { task: 'PERSONA_VALIDATION', pool: 'reasoning' },
  { task: 'CONTRADICTION_CHECK', pool: 'reasoning' },
  { task: 'CRITIC', pool: 'reasoning' },
  { task: 'PERSONA_INTERVIEW', pool: 'conversation' },
  { task: 'PERSONA_RESPONSE', pool: 'conversation' },
  { task: 'EVIDENCE_EXTRACTION', pool: 'structured' },
  { task: 'EVIDENCE_CLASSIFICATION', pool: 'structured' },
  { task: 'STRUCTURED_OUTPUT', pool: 'structured' },
  { task: 'BROWSER_AGENT', pool: 'structured' },
  { task: 'TOOL_CALLING', pool: 'structured' },
  { task: 'MEMORY_RETRIEVAL', pool: 'fast' },
  { task: 'MEMORY_SUMMARIZATION', pool: 'fast' },
  { task: 'REPORT_GENERATION', pool: 'long_context' },
  { task: 'EMERGENCY_FALLBACK', pool: 'emergency' },
];

export const InteractiveDemo: React.FC = () => {
  const { navigate } = useNavigation();
  const [selectedTask, setSelectedTask] = useState<string>('PERSONA_GENERATION');

  const current = TASK_TYPES.find((t) => t.task === selectedTask)!;
  const pool = POOLS[current.pool];

  return (
    <section
      id="demo"
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
            Task → Pool Map
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
            Pick a task type and see{' '}
            <span className="text-gradient-blue">
              exactly where it routes.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            This is the real configuration: 16 fixed task types, 7 pools, preference-ordered candidates, and a local model at the end of every chain.
          </p>
        </div>

        {/* Routing Map Card (No outline) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '24px',
            background: '#09090C',
            border: 'none',
            outline: 'none',
            padding: '40px',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '48px',
              alignItems: 'center',
            }}
          >
            {/* Left Task Type List */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
                <Sliders size={18} color="#FFFFFF" />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                  Task type
                </h3>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {TASK_TYPES.map((t) => {
                  const isActive = t.task === selectedTask;
                  return (
                    <button
                      key={t.task}
                      onClick={() => setSelectedTask(t.task)}
                      style={{
                        padding: '7px 14px',
                        borderRadius: '9999px',
                        border: 'none',
                        outline: 'none',
                        cursor: 'pointer',
                        fontSize: '0.74rem',
                        fontWeight: 600,
                        fontFamily: 'var(--font-mono)',
                        transition: 'all 0.2s ease',
                        background: isActive ? '#FFFFFF' : 'rgba(255, 255, 255, 0.04)',
                        color: isActive ? '#000000' : '#8E8E93',
                      }}
                    >
                      {t.task}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Right Routing Result Panel (No outline) */}
            <div
              style={{
                borderRadius: '18px',
                background: '#040406',
                border: 'none',
                outline: 'none',
                padding: '28px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '14px' }}>
                <Sparkles size={16} color="#F6C878" />
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#F6C878', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Routes to
                </span>
              </div>

              <div
                style={{
                  fontSize: 'clamp(2.2rem, 3.8vw, 3rem)',
                  fontWeight: 800,
                  letterSpacing: '-0.03em',
                  color: '#FFFFFF',
                  marginBottom: '10px',
                }}
              >
                {pool.pool}
              </div>

              <p style={{ fontSize: '0.84rem', color: '#8E8E93', lineHeight: '1.5', marginBottom: '22px' }}>
                Ordering inside a pool is a preference order, and the chain ends at the local adapter so fallback always terminates on-machine.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.03)', border: 'none' }}>
                  <span style={{ fontSize: '0.8rem', color: '#8E8E93' }}>Concurrency limit:</span>
                  <strong style={{ fontSize: '0.84rem', color: '#F6C878' }}>{pool.limit}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.03)', border: 'none' }}>
                  <span style={{ fontSize: '0.8rem', color: '#8E8E93' }}>Candidate order:</span>
                  <strong style={{ fontSize: '0.78rem', color: '#FFFFFF', textAlign: 'right', fontFamily: 'var(--font-mono)' }}>{pool.candidates}</strong>
                </div>
              </div>

              <button
                onClick={() => navigate('/auth/signup')}
                className="primary-hero-btn"
                style={{
                  width: '100%',
                  padding: '12px',
                  borderRadius: '9999px',
                  border: 'none',
                  outline: 'none',
                  fontSize: '0.9rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                }}
              >
                <span>Generate your first persona</span>
                <ArrowRight size={15} color="#000000" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

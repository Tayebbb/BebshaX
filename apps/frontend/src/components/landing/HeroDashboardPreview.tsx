import React, { useState } from 'react';
import {
  ShieldCheck,
  Sparkles,
  Search,
  RefreshCw,
} from 'lucide-react';

const PROVENANCE_STYLES: Record<string, { bg: string; fg: string }> = {
  OBSERVED: { bg: 'rgba(16, 185, 129, 0.12)', fg: '#34D399' },
  INFERRED: { bg: 'rgba(59, 130, 246, 0.12)', fg: '#93C5FD' },
  SYNTHETIC: { bg: 'rgba(246, 200, 120, 0.12)', fg: '#F6C878' },
};

export const HeroDashboardPreview: React.FC = () => {
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);

  const attributes = [
    { label: 'Reorders office supplies on a monthly cycle', klass: 'OBSERVED' },
    { label: 'Prefers written follow-up over phone calls', klass: 'INFERRED' },
    { label: 'Trials new tools with a small team first', klass: 'SYNTHETIC' },
  ];

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        maxWidth: '1120px',
        margin: '0 auto',
      }}
    >
      {/* Ambient light glow without harsh box */}
      <div
        style={{
          position: 'absolute',
          top: '-15%',
          left: '10%',
          right: '10%',
          height: '130%',
          background: 'radial-gradient(ellipse at center, rgba(246, 200, 120, 0.08) 0%, rgba(59, 130, 246, 0.06) 40%, transparent 70%)',
          filter: 'blur(70px)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Main Container Minimalist Console (No outer box outline) */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          background: '#09090C',
          border: 'none',
          outline: 'none',
          borderRadius: '20px',
          boxShadow: '0 30px 80px rgba(0, 0, 0, 0.85)',
          overflow: 'hidden',
          padding: '20px 24px 24px 24px',
        }}
      >
        {/* Top Window Header Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: '16px',
            marginBottom: '20px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#EF4444' }} />
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#F59E0B' }} />
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#10B981' }} />
            <div style={{ marginLeft: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: '#71717A', fontWeight: 500, fontFamily: 'var(--font-mono)' }}>bebshax / personas</span>
              <span
                style={{
                  fontSize: '0.62rem',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  background: 'rgba(59, 130, 246, 0.12)',
                  color: '#93C5FD',
                  border: 'none',
                  outline: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                }}
              >
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#60A5FA' }} />
                EXAMPLE OUTPUT
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 12px',
                background: 'rgba(255, 255, 255, 0.04)',
                borderRadius: '6px',
                border: 'none',
                outline: 'none',
                fontSize: '0.75rem',
                color: '#71717A',
              }}
            >
              <Search size={13} color="#A1A1AA" />
              <span>Filter personas...</span>
            </div>
            <button
              style={{
                padding: '6px 9px',
                borderRadius: '6px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: 'none',
                outline: 'none',
                color: '#FFFFFF',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {/* Console Grid Content */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '14px' }}>

          {/* Persona Identity Card */}
          <div
            style={{
              gridColumn: 'span 12',
              background: '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '14px',
              padding: '16px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: '#8E8E93', fontWeight: 500 }}>Identity card</span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: '#F6C878',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontWeight: 700,
                }}
              >
                <ShieldCheck size={13} /> Byte-identical on every turn
              </span>
            </div>
            <div style={{ fontSize: '1.65rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              Amara Osei
            </div>
            <div style={{ fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
              34 · Office manager · Manchester, UK
            </div>
          </div>

          {/* Attribute Provenance Rows (No Outlines) */}
          <div
            style={{
              gridColumn: 'span 8',
              background: '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '16px',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#FFFFFF' }}>
                  Attributes and their provenance
                </div>
                <div style={{ fontSize: '0.75rem', color: '#71717A' }}>
                  Every attribute carries exactly one class. Classes can only be downgraded, never upgraded.
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <span style={{ padding: '3px 8px', fontSize: '0.68rem', background: 'rgba(59, 130, 246, 0.15)', color: '#93C5FD', borderRadius: '4px', fontWeight: 700, border: 'none' }}>
                  Example output
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {attributes.map((attr, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '12px',
                    padding: '13px 14px',
                    borderRadius: '10px',
                    background: '#040406',
                    border: 'none',
                    outline: 'none',
                  }}
                >
                  <span style={{ fontSize: '0.8rem', color: '#D4D4D8' }}>{attr.label}</span>
                  <span
                    style={{
                      fontSize: '0.66rem',
                      fontWeight: 800,
                      letterSpacing: '0.06em',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      whiteSpace: 'nowrap',
                      background: PROVENANCE_STYLES[attr.klass].bg,
                      color: PROVENANCE_STYLES[attr.klass].fg,
                      border: 'none',
                    }}
                  >
                    {attr.klass}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Right Routing Strip (No Outlines) */}
          <div
            style={{
              gridColumn: 'span 4',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 2px',
              }}
            >
              <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#FFFFFF', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={14} color="#F6C878" />
                <span>Routing path</span>
              </div>
              <span style={{ fontSize: '0.68rem', color: '#71717A', fontWeight: 600 }}>per request</span>
            </div>

            {/* Routing Card 1 */}
            <div
              onMouseEnter={() => setHoveredCard('c1')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c1' ? '#181822' : '#0D0D11',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: '#8E8E93', letterSpacing: '0.06em', marginBottom: '3px' }}>
                TASK
              </div>
              <p style={{ fontSize: '0.74rem', color: '#FFFFFF', lineHeight: '1.4', fontFamily: 'var(--font-mono)' }}>
                PERSONA_GENERATION
              </p>
            </div>

            {/* Routing Card 2 */}
            <div
              onMouseEnter={() => setHoveredCard('c2')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c2' ? '#181822' : '#0D0D11',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: '#8E8E93', letterSpacing: '0.06em', marginBottom: '3px' }}>
                POOL
              </div>
              <p style={{ fontSize: '0.74rem', color: '#FFFFFF', lineHeight: '1.4', fontFamily: 'var(--font-mono)' }}>
                reasoning <span style={{ color: '#71717A' }}>· max 2 concurrent</span>
              </p>
            </div>

            {/* Routing Card 3 */}
            <div
              onMouseEnter={() => setHoveredCard('c3')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c3' ? '#181822' : '#0D0D11',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ fontSize: '0.68rem', fontWeight: 800, color: '#8E8E93', letterSpacing: '0.06em', marginBottom: '3px' }}>
                ATTEMPT CHAIN
              </div>
              <p style={{ fontSize: '0.72rem', color: '#8E8E93', lineHeight: '1.5', fontFamily: 'var(--font-mono)' }}>
                freellmpool → <strong style={{ color: '#F6C878', fontWeight: 600 }}>rate limited, route cooling 60s</strong> → freellmpool → ollama (local)
              </p>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};

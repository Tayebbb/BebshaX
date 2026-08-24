import React, { useState } from 'react';
import {
  LayoutDashboard,
  Cpu,
  Target,
  Workflow,
  Sparkles,
  AlertCircle,
  CheckCircle,
  ArrowRight,
} from 'lucide-react';

export const ProductShowcase: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'personas' | 'interviews' | 'memory' | 'telemetry'>('personas');

  const tabs = [
    {
      id: 'personas' as const,
      label: 'Personas',
      icon: <LayoutDashboard size={16} />,
      headline: 'Every attribute carries the class that earned it.',
      description: 'Attributes backed by a retrieved dataset record are OBSERVED. The rest are INFERRED or SYNTHETIC. Fabricated citations are stripped in code and the attribute is downgraded.',
    },
    {
      id: 'interviews' as const,
      label: 'Interviews',
      icon: <Cpu size={16} />,
      headline: 'The same person on turn one and turn twenty.',
      description: 'The persona is never rebuilt between turns. Each turn recomposes the immutable identity card, the business context, the objective, retrieved memories, evidence themes, and the full history.',
    },
    {
      id: 'memory' as const,
      label: 'Memory',
      icon: <Workflow size={16} />,
      headline: 'A pgvector memory stream with three kinds.',
      description: 'Semantic, episodic and reflection memories, scored by similarity, recency and importance. A reflection pass condenses them into higher-level items.',
    },
    {
      id: 'telemetry' as const,
      label: 'Telemetry',
      icon: <Target size={16} />,
      headline: 'Every request records the route it actually took.',
      description: 'A provenance record per request: provider, model, latency, failure kind, fallback reason, and the routing path across the pool.',
    },
  ];

  const currentTab = tabs.find((t) => t.id === activeTab)!;

  return (
    <section
      id="product"
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
            The Console
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
            Four tabs.{' '}
            <span className="text-gradient-blue">
              One research loop.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Generate personas, interview them, inspect what they remember, and read the routing behind every call.
          </p>
        </div>

        {/* Tab Navigation Pill Bar (No outline) */}
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
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
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
                  {React.cloneElement(tab.icon, {
                    color: isActive ? '#000000' : '#8E8E93',
                  })}
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Product Module Card Display (No outline) */}
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
            {/* Left Description Column */}
            <div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 10px',
                  borderRadius: '6px',
                  background: 'rgba(246, 200, 120, 0.1)',
                  color: '#F6C878',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  marginBottom: '14px',
                  border: 'none',
                }}
              >
                <Sparkles size={13} color="#F6C878" />
                <span>CONSOLE TAB</span>
              </div>

              <h3
                style={{
                  fontSize: '1.75rem',
                  fontWeight: 800,
                  letterSpacing: '-0.02em',
                  color: '#FFFFFF',
                  marginBottom: '14px',
                  lineHeight: 1.25,
                }}
              >
                {currentTab.headline}
              </h3>

              <p
                style={{
                  fontSize: '0.95rem',
                  color: '#8E8E93',
                  lineHeight: '1.6',
                  marginBottom: '24px',
                }}
              >
                {currentTab.description}
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '28px' }}>
                {[
                  'Every LLM call declares an explicit task type',
                  'Grounded in preprocessed public research datasets',
                  'Context is never truncated to fit a smaller model',
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        background: 'rgba(255, 255, 255, 0.06)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: 'none',
                      }}
                    >
                      <CheckCircle size={12} color="#F6C878" />
                    </div>
                    <span style={{ fontSize: '0.84rem', color: '#D4D4D8', fontWeight: 500 }}>{item}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <a
                  href="#demo"
                  className="primary-hero-btn"
                  style={{
                    padding: '10px 20px',
                    borderRadius: '9999px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '0.86rem',
                    textDecoration: 'none',
                    border: 'none',
                    outline: 'none',
                  }}
                >
                  <span>Try the routing map</span>
                  <ArrowRight size={14} color="#000000" />
                </a>
              </div>
            </div>

            {/* Right Interactive Mock View (No outline) */}
            <div
              style={{
                borderRadius: '16px',
                background: '#040406',
                border: 'none',
                outline: 'none',
                padding: '20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F6C878' }} />
                  <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF' }}>
                    {currentTab.label} Preview
                  </span>
                </div>
                <span style={{ fontSize: '0.68rem', color: '#71717A', fontWeight: 500 }}>
                  Example output
                </span>
              </div>

              {/* Tab-Specific Dynamic Visuals */}
              {activeTab === 'personas' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Reorders supplies monthly</span>
                      <span style={{ fontSize: '0.72rem', color: '#34D399', fontWeight: 700 }}>OBSERVED</span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: '#52525B' }}>Backed by a retrieved dataset record</div>
                  </div>

                  <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Prefers written follow-up</span>
                      <span style={{ fontSize: '0.72rem', color: '#93C5FD', fontWeight: 700 }}>INFERRED</span>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: '#52525B' }}>Citation stripped, class downgraded</div>
                  </div>
                </div>
              )}

              {activeTab === 'interviews' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', border: 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#93C5FD', fontWeight: 700, fontSize: '0.78rem', marginBottom: '2px' }}>
                      <Sparkles size={13} /> Composed per turn
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#A1A1AA' }}>
                      Identity card + business context + objective + retrieved memories + evidence themes + full history.
                    </div>
                  </div>

                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', border: 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#F87171', fontWeight: 700, fontSize: '0.78rem', marginBottom: '2px' }}>
                      <AlertCircle size={13} /> Too large to compose
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#A1A1AA' }}>
                      The turn fails explicitly rather than truncating the persona.
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'memory' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {[
                    { name: 'Cosine similarity', impact: '0.60', time: 'Against the query embedding' },
                    { name: 'Recency', impact: '0.25', time: '48-hour half-life' },
                    { name: 'Importance', impact: '0.15', time: 'Assigned when the memory is written' },
                  ].map((p, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderRadius: '8px', background: '#0D0D11', border: 'none' }}>
                      <div>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF' }}>{p.name}</div>
                        <div style={{ fontSize: '0.68rem', color: '#71717A' }}>{p.time}</div>
                      </div>
                      <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#F6C878', background: 'rgba(246, 200, 120, 0.12)', padding: '3px 6px', borderRadius: '4px', border: 'none' }}>
                        {p.impact}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === 'telemetry' && (
                <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '6px' }}>
                    Provenance record for this request
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Task type:</span>
                    <strong style={{ color: '#F6C878' }}>PERSONA_INTERVIEW</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Pool:</span>
                    <strong style={{ color: '#FFFFFF' }}>conversation</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Recorded per attempt:</span>
                    <strong style={{ color: '#FFFFFF' }}>provider, model, latency, failure kind</strong>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

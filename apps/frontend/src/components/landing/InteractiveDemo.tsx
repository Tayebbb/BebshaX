import React, { useState } from 'react';
import {
  Sliders,
  Sparkles,
  ArrowRight,
} from 'lucide-react';

export const InteractiveDemo: React.FC = () => {
  const [mrr, setMrr] = useState<number>(120);
  const [churnRate, setChurnRate] = useState<number>(3.5);
  const [expansionRate, setExpansionRate] = useState<number>(15);

  const calculatedExpansion = Math.round(mrr * (expansionRate / 100) * 12);
  const savedFromChurn = Math.round(mrr * (churnRate / 100) * 0.45 * 12);
  const totalGain = calculatedExpansion + savedFromChurn;

  return (
    <section
      id="demo"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
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
            className="glass-panel"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(37, 99, 235, 0.08)',
              border: '1px solid rgba(37, 99, 235, 0.2)',
              color: '#2563EB',
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            ROI & Growth Simulator
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: '#0F172A',
            }}
          >
            Simulate your business outcomes{' '}
            <span className="text-gradient-blue">
              in real time.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Adjust your scale parameters below to see how BebshaX detects hidden expansion potential and protects revenue.
          </p>
        </div>

        {/* Interactive Sandbox Simulator Card in Translucent White Glass */}
        <div
          className="glass-panel"
          style={{
            borderRadius: '28px',
            background: 'rgba(255, 255, 255, 0.78)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            border: '1px solid rgba(255, 255, 255, 0.9)',
            padding: '40px',
            boxShadow: 'var(--shadow-lg)',
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
            {/* Left Controls Column */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
                <Sliders size={20} color="#2563EB" />
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A' }}>
                  Business Parameters
                </h3>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* MRR Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#475569' }}>
                      Current Monthly Revenue (MRR)
                    </span>
                    <strong style={{ fontSize: '1rem', color: '#0F172A' }}>
                      ${mrr}k /mo
                    </strong>
                  </div>
                  <input
                    type="range"
                    min="20"
                    max="500"
                    step="10"
                    value={mrr}
                    onChange={(e) => setMrr(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#2563EB', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748B', marginTop: '4px' }}>
                    <span>$20k</span>
                    <span>$500k</span>
                  </div>
                </div>

                {/* Churn Rate Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#475569' }}>
                      Estimated Monthly Churn
                    </span>
                    <strong style={{ fontSize: '1rem', color: '#DC2626' }}>
                      {churnRate}%
                    </strong>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="0.5"
                    value={churnRate}
                    onChange={(e) => setChurnRate(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#DC2626', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748B', marginTop: '4px' }}>
                    <span>1.0%</span>
                    <span>10.0%</span>
                  </div>
                </div>

                {/* Expansion Opportunity Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.88rem', fontWeight: 600, color: '#475569' }}>
                      Expansion Target Opportunity
                    </span>
                    <strong style={{ fontSize: '1rem', color: '#2563EB' }}>
                      +{expansionRate}%
                    </strong>
                  </div>
                  <input
                    type="range"
                    min="5"
                    max="40"
                    step="1"
                    value={expansionRate}
                    onChange={(e) => setExpansionRate(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#2563EB', cursor: 'pointer' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#64748B', marginTop: '4px' }}>
                    <span>5%</span>
                    <span>40%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Projected Impact Panel */}
            <div
              className="glass-card"
              style={{
                borderRadius: '24px',
                background: 'rgba(255, 255, 255, 0.88)',
                border: '1.5px solid rgba(37, 99, 235, 0.35)',
                padding: '32px',
                boxShadow: '0 20px 45px rgba(37, 99, 235, 0.12)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
                <Sparkles size={18} color="#2563EB" />
                <span style={{ fontSize: '0.8rem', fontWeight: 800, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Projected Annual Value Unlock
                </span>
              </div>

              <div
                style={{
                  fontSize: 'clamp(2.4rem, 4vw, 3.2rem)',
                  fontWeight: 800,
                  letterSpacing: '-0.03em',
                  color: '#0F172A',
                  marginBottom: '12px',
                }}
              >
                +${totalGain.toLocaleString()} <span style={{ fontSize: '1rem', color: '#64748B' }}>/yr</span>
              </div>

              <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.5', marginBottom: '24px' }}>
                Estimated revenue improvement combining automated retention triggers and proactive account expansion suggestions.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '28px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderRadius: '10px', background: 'rgba(37, 99, 235, 0.06)' }}>
                  <span style={{ fontSize: '0.82rem', color: '#475569' }}>Annual Expansion ARR:</span>
                  <strong style={{ fontSize: '0.88rem', color: '#2563EB' }}>+${calculatedExpansion.toLocaleString()}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderRadius: '10px', background: 'rgba(16, 185, 129, 0.08)' }}>
                  <span style={{ fontSize: '0.82rem', color: '#475569' }}>Retained At-Risk Revenue:</span>
                  <strong style={{ fontSize: '0.88rem', color: '#10B981' }}>+${savedFromChurn.toLocaleString()}</strong>
                </div>
              </div>

              <button
                className="primary-hero-btn"
                style={{
                  width: '100%',
                  padding: '14px',
                  borderRadius: '12px',
                  border: 'none',
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                }}
              >
                <span>Unlock Full Growth Model</span>
                <ArrowRight size={16} color="#FFFFFF" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

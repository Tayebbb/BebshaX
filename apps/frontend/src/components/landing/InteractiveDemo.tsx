import React, { useState } from 'react';
import {
  Sliders,
  Sparkles,
  ArrowRight,
} from 'lucide-react';
import { useNavigation } from '../../context/NavigationContext';

export const InteractiveDemo: React.FC = () => {
  const { navigate } = useNavigation();
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
            ROI & Growth Simulator
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
            Simulate your business outcomes{' '}
            <span className="text-gradient-blue">
              in real time.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Adjust your scale parameters below to see how BebshaX detects hidden expansion potential and protects revenue.
          </p>
        </div>

        {/* Interactive Simulator Card (No outline) */}
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
            {/* Left Controls Column */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
                <Sliders size={18} color="#FFFFFF" />
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                  Business Parameters
                </h3>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* MRR Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.84rem', fontWeight: 500, color: '#8E8E93' }}>
                      Current Monthly Revenue (MRR)
                    </span>
                    <strong style={{ fontSize: '0.95rem', color: '#FFFFFF' }}>
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
                    style={{ width: '100%', accentColor: '#FFFFFF', cursor: 'pointer', border: 'none', outline: 'none' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
                    <span>$20k</span>
                    <span>$500k</span>
                  </div>
                </div>

                {/* Churn Rate Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.84rem', fontWeight: 500, color: '#8E8E93' }}>
                      Estimated Monthly Churn
                    </span>
                    <strong style={{ fontSize: '0.95rem', color: '#EF4444' }}>
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
                    style={{ width: '100%', accentColor: '#EF4444', cursor: 'pointer', border: 'none', outline: 'none' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
                    <span>1.0%</span>
                    <span>10.0%</span>
                  </div>
                </div>

                {/* Expansion Opportunity Slider */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.84rem', fontWeight: 500, color: '#8E8E93' }}>
                      Expansion Target Opportunity
                    </span>
                    <strong style={{ fontSize: '0.95rem', color: '#F6C878' }}>
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
                    style={{ width: '100%', accentColor: '#F6C878', cursor: 'pointer', border: 'none', outline: 'none' }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
                    <span>5%</span>
                    <span>40%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Projected Impact Panel (No outline) */}
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
                  Projected Annual Value Unlock
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
                +${totalGain.toLocaleString()} <span style={{ fontSize: '0.9rem', color: '#71717A', fontWeight: 500 }}>/yr</span>
              </div>

              <p style={{ fontSize: '0.84rem', color: '#8E8E93', lineHeight: '1.5', marginBottom: '22px' }}>
                Estimated revenue improvement combining automated retention triggers and proactive account expansion suggestions.
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.03)', border: 'none' }}>
                  <span style={{ fontSize: '0.8rem', color: '#8E8E93' }}>Annual Expansion ARR:</span>
                  <strong style={{ fontSize: '0.84rem', color: '#F6C878' }}>+${calculatedExpansion.toLocaleString()}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.08)', border: 'none' }}>
                  <span style={{ fontSize: '0.8rem', color: '#8E8E93' }}>Retained At-Risk Revenue:</span>
                  <strong style={{ fontSize: '0.84rem', color: '#10B981' }}>+${savedFromChurn.toLocaleString()}</strong>
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
                <span>Unlock Full Growth Model</span>
                <ArrowRight size={15} color="#000000" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

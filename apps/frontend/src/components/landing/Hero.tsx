import React from 'react';
import { useNavigation } from '../../context/NavigationContext';

interface HeroProps {
  onOpenApp?: () => void;
  onExploreDemo?: () => void;
}

export const Hero: React.FC<HeroProps> = () => {
  const { navigate } = useNavigation();

  return (
    <section
      style={{
        position: 'relative',
        height: '100vh',
        minHeight: '760px',
        maxHeight: '1080px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        alignItems: 'center',
        textAlign: 'center',
        paddingTop: '110px',
        paddingBottom: '48px',
        paddingLeft: '24px',
        paddingRight: '24px',
        boxSizing: 'border-box',
        overflow: 'hidden',
        zIndex: 1,
      }}
    >
      {/* Top Badges Container */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '14px',
        }}
      >
        {/* Subtle Category Bracket Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '0.8rem',
            color: '#8E8E93',
            letterSpacing: '0.04em',
          }}
        >
          <span style={{ color: '#F6C878', opacity: 0.6 }}>[</span>
          <span>Next-Gen <strong style={{ color: '#FFFFFF', fontWeight: 700 }}>Autonomous Decision Intelligence</strong></span>
          <span style={{ color: '#F6C878', opacity: 0.6 }}>]</span>
        </div>

        {/* Personas Simulated Pill */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 20px',
            borderRadius: '9999px',
            background: 'rgba(255, 255, 255, 0.04)',
            border: 'none',
            fontSize: '0.78rem',
            color: '#A1A1AA',
          }}
        >
          <span>Customer Personas Simulated on BebshaX — <strong style={{ color: '#FFFFFF' }}>48,907</strong></span>
          <span style={{ fontStyle: 'italic', color: '#F6C878' }}>and counting</span>
        </div>
      </div>

      {/* Center Main Hero Typography & Glow Button */}
      <div
        style={{
          maxWidth: '880px',
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '20px 0',
        }}
      >
        {/* Main Punchy Title */}
        <h1
          style={{
            fontSize: 'clamp(2.8rem, 5.8vw, 4.8rem)',
            fontWeight: 800,
            lineHeight: 1.12,
            letterSpacing: '-0.04em',
            marginBottom: '22px',
            color: '#FFFFFF',
          }}
        >
          Simulate every decision.
          <span
            style={{
              display: 'block',
              fontStyle: 'italic',
              fontWeight: 800,
              color: '#FFFFFF',
              marginTop: '4px',
            }}
          >
            Scale with certainty.
          </span>
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontSize: 'clamp(0.95rem, 1.5vw, 1.15rem)',
            color: '#A1A1AA',
            maxWidth: '680px',
            lineHeight: 1.6,
            marginBottom: '36px',
            fontWeight: 400,
          }}
        >
          Autonomous persona intelligence and cohort simulation grounded in real customer telemetry. Stress-test pricing, messaging, and feature adoption before spending capital.
        </p>

        {/* Single Glowing Gold Pill Button */}
        <button
          onClick={() => navigate('/auth/signup')}
          style={{
            padding: '13px 32px',
            fontSize: '0.96rem',
            fontWeight: 700,
            cursor: 'pointer',
            borderRadius: '9999px',
            background: '#F6C878',
            color: '#1A1305',
            border: 'none',
            outline: 'none',
            boxShadow: '0 0 35px rgba(246, 200, 120, 0.45)',
            transition: 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#E5B45F';
            e.currentTarget.style.boxShadow = '0 0 50px rgba(246, 200, 120, 0.65)';
            e.currentTarget.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = '#F6C878';
            e.currentTarget.style.boxShadow = '0 0 35px rgba(246, 200, 120, 0.45)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          Simulate your first cohort free
        </button>
      </div>

      {/* Bottom 3 Stats Row in the Hero Fold */}
      <div
        style={{
          width: '100%',
          maxWidth: '1080px',
          margin: '0 auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '24px',
          alignItems: 'flex-end',
        }}
      >
        {/* Stat 1 */}
        <div>
          <div
            style={{
              fontSize: 'clamp(2rem, 3.5vw, 2.8rem)',
              fontWeight: 800,
              color: '#F6C878',
              letterSpacing: '-0.03em',
              marginBottom: '6px',
            }}
          >
            98.4%
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8E8E93', lineHeight: '1.4' }}>
            Behavioral fidelity — <strong style={{ color: '#FFFFFF', fontWeight: 600 }}>grounded across 48k+ events</strong>
          </div>
        </div>

        {/* Stat 2 */}
        <div>
          <div
            style={{
              fontSize: 'clamp(2rem, 3.5vw, 2.8rem)',
              fontWeight: 800,
              color: '#F6C878',
              letterSpacing: '-0.03em',
              marginBottom: '6px',
            }}
          >
            &lt; 15 <span style={{ fontSize: '0.7em', color: '#FFFFFF', fontWeight: 700 }}>sec</span>
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8E8E93', lineHeight: '1.4' }}>
            From hypothesis to <strong style={{ color: '#FFFFFF', fontWeight: 600 }}>actionable decision report</strong>
          </div>
        </div>

        {/* Stat 3 */}
        <div>
          <div
            style={{
              fontSize: 'clamp(2rem, 3.5vw, 2.8rem)',
              fontWeight: 800,
              color: '#F6C878',
              letterSpacing: '-0.03em',
              marginBottom: '6px',
            }}
          >
            3.8×
          </div>
          <div style={{ fontSize: '0.82rem', color: '#8E8E93', lineHeight: '1.4' }}>
            Faster conviction on <strong style={{ color: '#FFFFFF', fontWeight: 600 }}>product & pricing bets</strong>
          </div>
        </div>
      </div>
    </section>
  );
};

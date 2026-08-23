import React from 'react';
import { ArrowRight, ShieldCheck, CheckCircle2, Sparkles } from 'lucide-react';
import { useNavigation } from '../../context/NavigationContext';

interface FinalCTAProps {
  onOpenApp?: () => void;
}

export const FinalCTA: React.FC<FinalCTAProps> = ({ onOpenApp }) => {
  const { navigate } = useNavigation();
  return (
    <section
      style={{
        position: 'relative',
        padding: '100px 0 120px 0',
        zIndex: 1,
      }}
    >
      <div
        style={{
          maxWidth: '1120px',
          margin: '0 auto',
          padding: '0 24px',
          position: 'relative',
        }}
      >
        {/* Subtle background blue glow */}
        <div
          style={{
            position: 'absolute',
            top: '10%',
            left: '15%',
            right: '15%',
            bottom: '10%',
            background: 'radial-gradient(ellipse at center, rgba(37, 99, 235, 0.2) 0%, rgba(96, 165, 250, 0.08) 60%, transparent 80%)',
            filter: 'blur(50px)',
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />

        {/* Floating CTA Glass Box */}
        <div
          className="glass-panel"
          style={{
            position: 'relative',
            zIndex: 1,
            borderRadius: '32px',
            background: 'rgba(255, 255, 255, 0.78)',
            backdropFilter: 'blur(32px)',
            WebkitBackdropFilter: 'blur(32px)',
            border: '1.5px solid rgba(255, 255, 255, 0.95)',
            padding: '64px 40px',
            textAlign: 'center',
            boxShadow: '0 30px 80px rgba(15, 23, 42, 0.12), 0 0 1px rgba(15, 23, 42, 0.15)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          {/* Eyebrow Badge */}
          <div
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
              marginBottom: '20px',
            }}
          >
            <Sparkles size={14} color="#2563EB" />
            <span>Ready to Elevate Your Intelligence?</span>
          </div>

          {/* Heading */}
          <h2
            style={{
              fontSize: 'clamp(2rem, 4vw, 3.2rem)',
              fontWeight: 800,
              color: '#0F172A',
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              maxWidth: '700px',
              lineHeight: 1.15,
            }}
          >
            Start making{' '}
            <span
              className="text-gradient-blue"
              style={{
                fontStyle: 'italic',
                fontWeight: 900,
              }}
            >
              better business decisions
            </span>{' '}
            today.
          </h2>

          {/* Subtitle */}
          <p
            style={{
              fontSize: 'clamp(1rem, 1.6vw, 1.15rem)',
              color: '#475569',
              maxWidth: '560px',
              lineHeight: 1.6,
              marginBottom: '36px',
              fontWeight: 500,
            }}
          >
            Join forward-thinking enterprise leaders transforming disparate data into actionable operational clarity in minutes.
          </p>

          {/* CTA Buttons */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '16px',
              marginBottom: '36px',
            }}
          >
            <button
              onClick={() => navigate('/auth/signup')}
              className="primary-hero-btn"
              style={{
                padding: '16px 36px',
                fontSize: '1.05rem',
                fontWeight: 700,
                borderRadius: '14px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '10px',
                cursor: 'pointer',
                border: 'none',
              }}
            >
              <span>Get Started Free</span>
              <ArrowRight size={18} color="#FFFFFF" />
            </button>

            <button
              onClick={onOpenApp}
              className="secondary-hero-btn"
              style={{
                padding: '16px 28px',
                fontSize: '1.05rem',
                fontWeight: 600,
                borderRadius: '14px',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <ShieldCheck size={18} color="#2563EB" />
              <span>Open Platform Console</span>
            </button>
          </div>

          {/* Guarantee Badges */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '24px',
              fontSize: '0.82rem',
              color: '#0F172A',
              fontWeight: 600,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={15} color="#2563EB" />
              <span>14-day full access trial</span>
            </div>
            <span style={{ color: 'rgba(15, 23, 42, 0.2)' }}>•</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={15} color="#2563EB" />
              <span>No credit card required</span>
            </div>
            <span style={{ color: 'rgba(15, 23, 42, 0.2)' }}>•</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <CheckCircle2 size={15} color="#2563EB" />
              <span>SOC2 compliant & encrypted</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

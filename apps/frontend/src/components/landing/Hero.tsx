import React from 'react';
import { ArrowRight, Play, Check } from 'lucide-react';
import { HeroDashboardPreview } from './HeroDashboardPreview';

interface HeroProps {
  onOpenApp?: () => void;
  onExploreDemo?: () => void;
}

export const Hero: React.FC<HeroProps> = () => {
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <section
      style={{
        position: 'relative',
        paddingTop: '148px',
        paddingBottom: '80px',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '0 24px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {/* Eyebrow Badge in Translucent Glass */}
        <div
          className="glass-panel"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 16px',
            borderRadius: '9999px',
            background: 'rgba(255, 255, 255, 0.65)',
            border: '1px solid rgba(255, 255, 255, 0.85)',
            boxShadow: '0 4px 15px rgba(15, 23, 42, 0.06)',
            marginBottom: '24px',
          }}
        >
          <div
            style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              background: '#2563EB',
              boxShadow: '0 0 8px #2563EB',
            }}
          />
          <span
            style={{
              fontSize: '0.78rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: '#2563EB',
            }}
          >
            The Smarter Way to Run Your Business
          </span>
          <span style={{ color: 'rgba(15, 23, 42, 0.2)' }}>|</span>
          <span style={{ fontSize: '0.75rem', color: '#475569', fontWeight: 600 }}>
            Next-Gen Business Intelligence
          </span>
        </div>

        {/* Main Headline */}
        <h1
          style={{
            fontSize: 'clamp(2.5rem, 5.5vw, 4.4rem)',
            fontWeight: 800,
            lineHeight: 1.12,
            letterSpacing: '-0.035em',
            maxWidth: '940px',
            marginBottom: '24px',
            color: '#0F172A',
          }}
        >
          Turn business data into{' '}
          <span
            className="text-gradient-blue"
            style={{
              fontStyle: 'italic',
              fontWeight: 800,
            }}
          >
            better decisions.
          </span>
        </h1>

        {/* Supporting Paragraph */}
        <p
          style={{
            fontSize: 'clamp(1.05rem, 1.8vw, 1.25rem)',
            color: '#475569',
            maxWidth: '650px',
            lineHeight: 1.6,
            marginBottom: '36px',
            fontWeight: 500,
          }}
        >
          BebshaX brings your business data, insights, and operational workflows together so you can understand exactly what is happening, act faster, and scale with verifiable confidence.
        </p>

        {/* Call to Action Button Group */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '16px',
            marginBottom: '32px',
          }}
        >
          <button
            onClick={() => scrollToSection('demo')}
            className="primary-hero-btn"
            style={{
              padding: '14px 30px',
              fontSize: '1rem',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}
          >
            <span>Get Started</span>
            <ArrowRight size={18} color="#FFFFFF" />
          </button>

          <button
            onClick={() => scrollToSection('how-it-works')}
            className="secondary-hero-btn"
            style={{
              padding: '14px 26px',
              fontSize: '1rem',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <Play size={16} fill="#2563EB" color="#2563EB" />
            <span>See How It Works</span>
          </button>
        </div>

        {/* Trust Badges Bar */}
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
            marginBottom: '56px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Check size={16} color="#2563EB" strokeWidth={2.5} />
            <span>No credit card required</span>
          </div>
          <span style={{ color: 'rgba(15, 23, 42, 0.2)' }}>•</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Check size={16} color="#2563EB" strokeWidth={2.5} />
            <span>14-day free intelligence trial</span>
          </div>
          <span style={{ color: 'rgba(15, 23, 42, 0.2)' }}>•</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Check size={16} color="#2563EB" strokeWidth={2.5} />
            <span>Enterprise-grade data encryption</span>
          </div>
        </div>

        {/* Product Visualization Preview with gentle floating animation */}
        <div className="floating-dashboard" style={{ width: '100%' }}>
          <HeroDashboardPreview />
        </div>
      </div>
    </section>
  );
};

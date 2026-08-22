import React, { useState } from 'react';
import {
  Link2,
  BrainCircuit,
  Rocket,
  CheckCircle2,
  ArrowRight,
  Sparkles,
} from 'lucide-react';

export const HowItWorks: React.FC = () => {
  const [activeStep, setActiveStep] = useState<number>(1);

  const steps = [
    {
      num: '01',
      title: 'Connect your business',
      subtitle: 'Seamless ingestion in under 3 minutes',
      description:
        'Connect your existing tools—Stripe, HubSpot, PostgreSQL, Shopify, Google Analytics, and custom APIs—without complex data engineering pipelines.',
      icon: <Link2 size={24} color="#2563EB" />,
      features: ['Pre-built SaaS & DB connectors', 'Encrypted TLS 1.3 transfer', 'Automatic schema mapping'],
    },
    {
      num: '02',
      title: 'Understand what matters',
      subtitle: 'Autonomous intelligence & root cause analysis',
      description:
        'BebshaX continuously monitors data streams, connects related signals, spots emerging opportunities, and diagnoses why key metrics are changing.',
      icon: <BrainCircuit size={24} color="#2563EB" />,
      features: ['Real-time anomaly detection', 'Evidence-grounded explanations', 'Multi-channel attribution'],
    },
    {
      num: '03',
      title: 'Take confident action',
      subtitle: 'Prioritized playbooks with measured impact',
      description:
        'Get clear, step-by-step playbooks for your team. Deploy automated workflows, run targeted campaigns, or adjust pricing based on verified evidence.',
      icon: <Rocket size={24} color="#2563EB" />,
      features: ['Ready-to-deploy action playbooks', 'Simulated outcome forecasts', 'Live ROI & velocity tracking'],
    },
  ];

  return (
    <section
      id="how-it-works"
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 64px auto' }}>
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
            Clear 3-Step Process
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
            From scattered data to{' '}
            <span className="text-gradient-blue">
              decisive action.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            BebshaX bridges the gap between raw data collection and strategic execution in three simple steps.
          </p>
        </div>

        {/* Steps Interactive Selector */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
            marginBottom: '48px',
          }}
        >
          {steps.map((step, idx) => {
            const stepNum = idx + 1;
            const isActive = activeStep === stepNum;
            return (
              <div
                key={idx}
                onClick={() => setActiveStep(stepNum)}
                className="glass-card"
                style={{
                  padding: '32px 28px',
                  borderRadius: '22px',
                  cursor: 'pointer',
                  background: isActive
                    ? 'rgba(255, 255, 255, 0.88)'
                    : 'rgba(255, 255, 255, 0.60)',
                  border: isActive
                    ? '2px solid #2563EB'
                    : '1px solid rgba(255, 255, 255, 0.75)',
                  boxShadow: isActive ? '0 15px 35px rgba(37, 99, 235, 0.15)' : 'var(--shadow-sm)',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Number Watermark */}
                <div
                  style={{
                    position: 'absolute',
                    top: '16px',
                    right: '20px',
                    fontSize: '2.6rem',
                    fontWeight: 900,
                    color: isActive ? 'rgba(37, 99, 235, 0.15)' : 'rgba(15, 23, 42, 0.05)',
                    userSelect: 'none',
                  }}
                >
                  {step.num}
                </div>

                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '14px',
                    background: isActive ? 'rgba(37, 99, 235, 0.15)' : 'rgba(37, 99, 235, 0.08)',
                    border: '1px solid rgba(37, 99, 235, 0.25)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '20px',
                  }}
                >
                  {step.icon}
                </div>

                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A', marginBottom: '6px' }}>
                  {step.title}
                </h3>
                <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#2563EB', marginBottom: '14px' }}>
                  {step.subtitle}
                </div>
                <p style={{ fontSize: '0.88rem', color: '#475569', lineHeight: '1.6', marginBottom: '20px' }}>
                  {step.description}
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {step.features.map((f, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', color: '#0F172A', fontWeight: 500 }}>
                      <CheckCircle2 size={15} color="#2563EB" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Step Deep-Dive Showcase Box */}
        <div
          className="glass-panel"
          style={{
            padding: '36px',
            borderRadius: '24px',
            background: 'rgba(255, 255, 255, 0.8)',
            backdropFilter: 'blur(28px)',
            WebkitBackdropFilter: 'blur(28px)',
            border: '1px solid rgba(255, 255, 255, 0.9)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '20px' }}>
            <div style={{ maxWidth: '620px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                <Sparkles size={16} color="#2563EB" />
                <span style={{ fontSize: '0.8rem', fontWeight: 800, color: '#2563EB', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Step {steps[activeStep - 1].num} in Action
                </span>
              </div>
              <h4 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#0F172A', marginBottom: '8px' }}>
                {steps[activeStep - 1].title}
              </h4>
              <p style={{ fontSize: '0.92rem', color: '#475569', lineHeight: '1.6' }}>
                {steps[activeStep - 1].description}
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => setActiveStep(activeStep === 3 ? 1 : activeStep + 1)}
                className="primary-hero-btn"
                style={{
                  padding: '12px 24px',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '0.9rem',
                }}
              >
                <span>Next Step</span>
                <ArrowRight size={16} color="#FFFFFF" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

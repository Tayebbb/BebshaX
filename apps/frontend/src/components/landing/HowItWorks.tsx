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
      title: 'Describe your business',
      subtitle: 'No data connection required',
      description:
        'Give BebshaX a name, a description, an industry, and a target market. Add an optional audience segment and optional generation hints. That is the entire input.',
      icon: <Link2 size={22} color="#FFFFFF" />,
      features: ['Name, description, industry, target market', 'Optional audience segment', 'Optional generation hints'],
    },
    {
      num: '02',
      title: 'Generate a grounded persona',
      subtitle: 'Evidence, provenance, then consistency rules',
      description:
        'Evidence retrieval runs over preprocessed public dataset records, the persona is generated, provenance is enforced in code, and deterministic consistency rules run before storage. One refinement attempt is allowed — after that, generation fails with the list of violations.',
      icon: <BrainCircuit size={22} color="#F6C878" />,
      features: ['idf-weighted lexical evidence retrieval', 'OBSERVED, INFERRED or SYNTHETIC per attribute', 'One refinement attempt, then explicit failure'],
    },
    {
      num: '03',
      title: 'Interview the persona',
      subtitle: 'Multi-turn, with the same person every turn',
      description:
        'Each turn recomposes the immutable identity card, the business context, the interview objective, retrieved memories, evidence themes, and the full conversation history. Every exchange is written back as an episodic memory.',
      icon: <Rocket size={22} color="#FFFFFF" />,
      features: ['Byte-identical identity card on every turn', 'Top 4 memories retrieved per turn', 'Context is never truncated to fit'],
    },
  ];

  return (
    <section
      id="how-it-works"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
        background: '#080909',
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
            Clear 3-Step Process
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
            From a business description to{' '}
            <span className="text-gradient-blue">
              an interview.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Three steps, and no data connection at any point in them.
          </p>
        </div>

        {/* Steps Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '20px',
            marginBottom: '40px',
          }}
        >
          {steps.map((step, idx) => {
            const stepNum = idx + 1;
            const isActive = activeStep === stepNum;
            return (
              <div
                key={idx}
                onClick={() => setActiveStep(stepNum)}
                className="clean-card"
                style={{
                  padding: '32px 28px',
                  borderRadius: '18px',
                  cursor: 'pointer',
                  background: isActive ? '#121218' : '#09090C',
                  border: 'none',
                  outline: 'none',
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Number Watermark */}
                <div
                  style={{
                    position: 'absolute',
                    top: '14px',
                    right: '18px',
                    fontSize: '2.2rem',
                    fontWeight: 900,
                    color: isActive ? 'rgba(246, 200, 120, 0.15)' : 'rgba(255, 255, 255, 0.03)',
                    userSelect: 'none',
                  }}
                >
                  {step.num}
                </div>

                <div
                  style={{
                    width: '42px',
                    height: '42px',
                    borderRadius: '10px',
                    background: 'rgba(255, 255, 255, 0.04)',
                    border: 'none',
                    outline: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '20px',
                  }}
                >
                  {step.icon}
                </div>

                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '4px' }}>
                  {step.title}
                </h3>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#F6C878', marginBottom: '14px' }}>
                  {step.subtitle}
                </div>
                <p style={{ fontSize: '0.85rem', color: '#8E8E93', lineHeight: '1.6', marginBottom: '20px' }}>
                  {step.description}
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {step.features.map((f, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', color: '#D4D4D8', fontWeight: 500 }}>
                      <CheckCircle2 size={14} color="#F6C878" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Step Deep-Dive Showcase Box (No outline) */}
        <div
          className="clean-card"
          style={{
            padding: '32px 36px',
            borderRadius: '20px',
            background: '#09090C',
            border: 'none',
            outline: 'none',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '20px' }}>
            <div style={{ maxWidth: '620px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <Sparkles size={14} color="#F6C878" />
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#F6C878', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Step {steps[activeStep - 1].num} in Action
                </span>
              </div>
              <h4 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#FFFFFF', marginBottom: '8px' }}>
                {steps[activeStep - 1].title}
              </h4>
              <p style={{ fontSize: '0.88rem', color: '#8E8E93', lineHeight: '1.6' }}>
                {steps[activeStep - 1].description}
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => setActiveStep(activeStep === 3 ? 1 : activeStep + 1)}
                className="primary-hero-btn"
                style={{
                  padding: '10px 22px',
                  borderRadius: '9999px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '0.88rem',
                  border: 'none',
                  outline: 'none',
                }}
              >
                <span>Next Step</span>
                <ArrowRight size={15} color="#000000" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

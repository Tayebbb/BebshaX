import React, { useState } from 'react';
import {
  MessagesSquare,
  BrainCircuit,
  ListChecks,
  Rocket,
  FileText,
  CheckCircle2,
  ArrowRight,
} from 'lucide-react';

export const HowItWorks: React.FC = () => {
  const [activeStep, setActiveStep] = useState<number>(1);

  const steps = [
    {
      num: '01',
      title: 'Define your goal',
      subtitle: 'A conversation, not a form',
      description:
        'Tell the Study Design Copilot what you want to find out, in plain English. It asks follow-up questions, sharpens it into a research objective you can defend, and proposes which kinds of customers you should be talking to.',
      icon: <MessagesSquare size={22} color="var(--lp-text)" />,
      features: ['Free-text chat: start with one sentence', 'The copilot refines the objective with you', 'Pick the customer roles to generate'],
    },
    {
      num: '02',
      title: 'Generate your personas',
      subtitle: 'Labelled by how each attribute is known',
      description:
        'BebshaX retrieves supporting records from public research datasets, builds the personas, and labels every attribute with how it is known: cited evidence, reasoned inference, or an explicit assumption. Consistency rules run before anything is saved.',
      icon: <BrainCircuit size={22} color="var(--lp-gold)" />,
      features: ['Evidence retrieved from public datasets', 'Every attribute labelled with how it is known', 'Inconsistent personas are rejected, not patched'],
    },
    {
      num: '03',
      title: 'Build the interview script',
      subtitle: 'The questions you would actually ask',
      description:
        'BebshaX drafts the questions and the probing rules that follow up on vague answers. You read them, edit them, and cut the ones you do not need, before a single interview runs.',
      icon: <ListChecks size={22} color="var(--lp-text)" />,
      features: ['Questions drafted from your objective', 'Probing rules for shallow answers', 'Fully editable before you run it'],
    },
    {
      num: '04',
      title: 'Run the interviews',
      subtitle: 'Multi-turn, and in character',
      description:
        'Each persona answers your script across a real back-and-forth conversation, remembering what it already told you. The identity is byte-identical on every turn, so the person you started with is the person you finish with.',
      icon: <Rocket size={22} color="var(--lp-gold)" />,
      features: ['Multi-turn, not one-shot answers', 'The persona never drifts mid-interview', 'Every exchange is remembered'],
    },
    {
      num: '05',
      title: 'Get your decision report',
      subtitle: 'What you should do next',
      description:
        'One report synthesised across every interview: what you heard, where the personas disagreed, and what it means for the idea. Each finding is traceable back to the persona and the evidence behind it.',
      icon: <FileText size={22} color="var(--lp-text)" />,
      features: ['Synthesised across all interviews', 'Findings traceable to their source', 'Regenerate it as the study evolves'],
    },
  ];

  return (
    <section
      id="how-it-works"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
        background: 'var(--lp-bg)',
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
              background: 'rgba(var(--lp-fill-rgb), 0.05)',
              border: 'none',
              outline: 'none',
              color: 'var(--lp-text)',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            Five Guided Steps
          </div>

          <h2
            style={{
              fontSize: 'clamp(2rem, 3.8vw, 3rem)',
              fontWeight: 800,
              letterSpacing: '-0.03em',
              marginBottom: '16px',
              color: 'var(--lp-text)',
            }}
          >
            From a rough idea to{' '}
            <span className="text-gradient-blue">
              a decision you can defend.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
            You start by describing your idea in plain English. BebshaX walks you through the rest.
          </p>
        </div>

        {/* Steps Grid (No outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))',
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
                  background: isActive ? 'var(--lp-surface-active)' : 'var(--lp-surface)',
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
                    color: isActive ? 'rgba(var(--lp-gold-rgb), 0.15)' : 'rgba(var(--lp-fill-rgb), 0.03)',
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
                    background: 'rgba(var(--lp-fill-rgb), 0.04)',
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

                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--lp-text)', marginBottom: '4px' }}>
                  {step.title}
                </h3>
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--lp-gold)', marginBottom: '14px' }}>
                  {step.subtitle}
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--lp-text-muted)', lineHeight: '1.6', marginBottom: '20px' }}>
                  {step.description}
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {step.features.map((f, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem', color: 'var(--lp-text-hi)', fontWeight: 500 }}>
                      <CheckCircle2 size={14} color="var(--lp-gold)" />
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
            background: 'var(--lp-surface)',
            border: 'none',
            outline: 'none',
          }}
        >
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '20px' }}>
            <div style={{ maxWidth: '620px' }}>
              <h4 style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--lp-text)', marginBottom: '8px' }}>
                {steps[activeStep - 1].title}
              </h4>
              <p style={{ fontSize: '0.88rem', color: 'var(--lp-text-muted)', lineHeight: '1.6' }}>
                {steps[activeStep - 1].description}
              </p>
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => setActiveStep(activeStep === steps.length ? 1 : activeStep + 1)}
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
                <ArrowRight size={15} color="var(--lp-contrast-fg)" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

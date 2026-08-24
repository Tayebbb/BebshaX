import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export const FAQ: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const faqs = [
    {
      q: 'What is a synthetic persona in BebshaX?',
      a: 'It is a generated profile of a plausible customer for a business you describe — name, age, occupation, location and behavioural attributes — that you can then interview in a multi-turn conversation. The persona is never rebuilt between turns: the identity card is byte-identical on every turn, and a test enforces that.',
    },
    {
      q: 'What does “evidence-grounded” actually mean here?',
      a: 'Every attribute carries exactly one of three provenance classes. OBSERVED means it is backed by a retrieved record from a public research dataset. INFERRED and SYNTHETIC mean it is not. Evidence retrieval is idf-weighted lexical retrieval over preprocessed dataset records, and provenance is enforced in code: fabricated citations are stripped and the attribute is downgraded. A class can only ever be downgraded, never upgraded.',
    },
    {
      q: 'What happens when a provider fails or a context is too large?',
      a: 'Failures are classified into a closed set of 14 kinds, each with one policy: retry the same route once, advance to the next candidate, or put the route on a 60-second cooldown per provider and model. Context is never truncated to fit a smaller model — if nothing in the pool can hold the request, it fails explicitly with ContextWindowExceeded. Low answer quality is never treated as an infrastructure failure; quality belongs to the evaluation layer.',
    },
    {
      q: 'Do we need to connect any of our own data?',
      a: 'No. The input is a business name, description, industry and target market, plus an optional audience segment and optional generation hints. That is all. There is no data connection of any kind.',
    },
    {
      q: 'Are models fine-tuned on the datasets?',
      a: 'No, never. Datasets are used for grounding and evaluation only — that is an explicit project rule. The real datasets include PersonaHub, Google Synthetic-Persona-Chat, EmpatheticDialogues, an Amazon Reviews slice, MMLU and GSM8K micro slices, RouterArena and xRouteBench. Setup is one command, idempotent, checksummed and license-verified.',
    },
    {
      q: 'What does it cost to run?',
      a: 'BebshaX runs on legitimately accessed free LLM provider tiers. Zero API keys is a supported configuration, because the keyless providers work out of the box. Every pool ends at a local Ollama model, so the fallback chain terminates on your own machine.',
    },
  ];

  const toggle = (i: number) => {
    setOpenIndex(openIndex === i ? null : i);
  };

  return (
    <section
      id="faq"
      style={{
        position: 'relative',
        padding: '100px 0',
        zIndex: 1,
        background: '#080909',
      }}
    >
      <div
        style={{
          maxWidth: '860px',
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
        {/* Section Header */}
        <div style={{ textAlign: 'center', marginBottom: '56px' }}>
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
            Frequently Asked Questions
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
            Everything you need to know.{' '}
            <span className="text-gradient-blue">
              Clear & direct.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            What the system does, and what it deliberately does not do.
          </p>
        </div>

        {/* Accordion List (No outlines) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {faqs.map((faq, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                className="clean-card"
                style={{
                  borderRadius: '16px',
                  background: isOpen ? '#101017' : '#08080C',
                  border: 'none',
                  outline: 'none',
                  overflow: 'hidden',
                  transition: 'all 0.2s ease',
                }}
              >
                <button
                  onClick={() => toggle(idx)}
                  style={{
                    width: '100%',
                    padding: '20px 24px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    background: 'none',
                    border: 'none',
                    outline: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: '#FFFFFF',
                    fontSize: '1rem',
                    fontWeight: 600,
                  }}
                >
                  <span style={{ paddingRight: '16px' }}>{faq.q}</span>
                  <div
                    style={{
                      width: '26px',
                      height: '26px',
                      borderRadius: '50%',
                      background: 'rgba(255, 255, 255, 0.05)',
                      border: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.2s ease',
                    }}
                  >
                    <ChevronDown size={14} color="#A1A1AA" />
                  </div>
                </button>

                {isOpen && (
                  <div
                    style={{
                      padding: '0 24px 20px 24px',
                      fontSize: '0.88rem',
                      color: '#8E8E93',
                      lineHeight: '1.6',
                    }}
                  >
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

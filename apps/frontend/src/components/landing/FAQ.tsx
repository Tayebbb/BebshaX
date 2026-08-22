import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';

export const FAQ: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const faqs = [
    {
      q: 'How does BebshaX differ from standard dashboard tools like PowerBI or Looker?',
      a: 'Standard business intelligence tools are passive query engines that display whatever charts you configure. BebshaX is a proactive decision intelligence platform: it autonomously monitors your unified data graph, investigates root causes when anomalies happen, and generates ready-to-execute operational playbooks with measured revenue impact.',
    },
    {
      q: 'How long does it take to connect our data sources?',
      a: 'Most teams are up and running in under 3 minutes. BebshaX offers pre-built connectors for Stripe, HubSpot, PostgreSQL, Snowflake, Shopify, Segment, and standard webhook endpoints with automatic schema mapping and TLS 1.3 encryption.',
    },
    {
      q: 'What is the "Evidence-Grounded Intelligence" model?',
      a: 'Every insight and recommendation produced by BebshaX is deterministically cited with the exact underlying event rows, timestamps, and statistical confidence intervals. There are no unverifiable black-box guesses.',
    },
    {
      q: 'Can we simulate decisions before deploying them live?',
      a: 'Yes. BebshaX includes a built-in what-if simulation sandbox that models the expected revenue, churn, and operational impacts of pricing updates, quota changes, or marketing spend reallocation before you commit capital.',
    },
    {
      q: 'Is my business data secure and private?',
      a: 'Absolutely. BebshaX enforces end-to-end data encryption in transit and at rest, SOC2-compliant access controls, and role-based permissions. We never train public foundation models on your proprietary company data.',
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
            Frequently Asked Questions
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
            Everything you need to know.{' '}
            <span className="text-gradient-blue">
              Clear & direct.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Have more questions? Reach out to our technical team anytime.
          </p>
        </div>

        {/* Accordion List in Translucent Glass */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {faqs.map((faq, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                className="glass-card"
                style={{
                  borderRadius: '18px',
                  background: isOpen
                    ? 'rgba(255, 255, 255, 0.88)'
                    : 'rgba(255, 255, 255, 0.60)',
                  border: isOpen
                    ? '1.5px solid rgba(37, 99, 235, 0.4)'
                    : '1px solid rgba(255, 255, 255, 0.8)',
                  boxShadow: isOpen ? '0 10px 25px rgba(37, 99, 235, 0.08)' : 'var(--shadow-sm)',
                  overflow: 'hidden',
                  transition: 'all 0.25s ease',
                }}
              >
                <button
                  onClick={() => toggle(idx)}
                  style={{
                    width: '100%',
                    padding: '22px 24px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left',
                    color: '#0F172A',
                    fontSize: '1.05rem',
                    fontWeight: 700,
                  }}
                >
                  <span style={{ paddingRight: '16px' }}>{faq.q}</span>
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      background: isOpen ? 'rgba(37, 99, 235, 0.12)' : 'rgba(15, 23, 42, 0.05)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                      transition: 'transform 0.25s ease',
                    }}
                  >
                    <ChevronDown size={16} color={isOpen ? '#2563EB' : '#64748B'} />
                  </div>
                </button>

                {isOpen && (
                  <div
                    style={{
                      padding: '0 24px 24px 24px',
                      fontSize: '0.92rem',
                      color: '#475569',
                      lineHeight: '1.65',
                      borderTop: '1px solid rgba(15, 23, 42, 0.06)',
                      paddingTop: '16px',
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

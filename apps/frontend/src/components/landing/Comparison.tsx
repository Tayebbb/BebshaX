import React from 'react';
import { Check, X, Sparkles } from 'lucide-react';

export const Comparison: React.FC = () => {
  const criteria = [
    {
      feature: 'Root Cause Diagnosis',
      bebshax: 'Automated telemetry trace + causal attribution',
      traditional: 'Manual CSV queries & fragmented guess-work',
    },
    {
      feature: 'Action Playbooks',
      bebshax: 'Pre-configured 1-click execution workflows',
      traditional: 'Static PDF reports & unfollowed Slack memos',
    },
    {
      feature: 'Simulation & What-If',
      bebshax: 'Predictive Monte-Carlo scenario modeling',
      traditional: 'Historical reporting only (backward-looking)',
    },
    {
      feature: 'Provenance & Evidence',
      bebshax: 'Cites exact event rows & confidence intervals',
      traditional: 'Opaque metrics with unverifiable aggregation',
    },
    {
      feature: 'Setup Time',
      bebshax: '< 3 minutes (Zero data engineering required)',
      traditional: '3 to 6 months custom data pipeline builds',
    },
  ];

  return (
    <section
      id="comparison"
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
            Competitive Matrix
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
            Why high-growth teams{' '}
            <span className="text-gradient-blue">
              switch to BebshaX.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Compare legacy business intelligence approaches against BebshaX’s unified intelligence engine.
          </p>
        </div>

        {/* Table Container in Translucent Glass */}
        <div
          className="glass-panel"
          style={{
            borderRadius: '24px',
            background: 'rgba(255, 255, 255, 0.72)',
            backdropFilter: 'blur(28px)',
            WebkitBackdropFilter: 'blur(28px)',
            border: '1px solid rgba(255, 255, 255, 0.85)',
            boxShadow: 'var(--shadow-md)',
            overflow: 'hidden',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(15, 23, 42, 0.08)' }}>
                  <th style={{ padding: '24px', fontSize: '0.9rem', color: '#64748B', fontWeight: 700, width: '28%' }}>
                    Capability
                  </th>
                  <th
                    style={{
                      padding: '24px',
                      fontSize: '1.05rem',
                      color: '#0F172A',
                      fontWeight: 800,
                      background: 'rgba(37, 99, 235, 0.06)',
                      width: '38%',
                      borderLeft: '1px solid rgba(37, 99, 235, 0.15)',
                      borderRight: '1px solid rgba(37, 99, 235, 0.15)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Sparkles size={18} color="#2563EB" />
                      <span>BebshaX Intelligence</span>
                    </div>
                  </th>
                  <th style={{ padding: '24px', fontSize: '0.9rem', color: '#64748B', fontWeight: 600, width: '34%' }}>
                    Legacy Dashboards & Spreadsheets
                  </th>
                </tr>
              </thead>
              <tbody>
                {criteria.map((c, i) => (
                  <tr
                    key={i}
                    style={{
                      borderBottom: i === criteria.length - 1 ? 'none' : '1px solid rgba(15, 23, 42, 0.06)',
                    }}
                  >
                    <td style={{ padding: '20px 24px', fontWeight: 700, color: '#0F172A', fontSize: '0.92rem' }}>
                      {c.feature}
                    </td>
                    <td
                      style={{
                        padding: '20px 24px',
                        background: 'rgba(37, 99, 235, 0.04)',
                        borderLeft: '1px solid rgba(37, 99, 235, 0.15)',
                        borderRight: '1px solid rgba(37, 99, 235, 0.15)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(37, 99, 235, 0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <Check size={14} color="#2563EB" strokeWidth={2.5} />
                        </div>
                        <span style={{ fontSize: '0.88rem', color: '#0F172A', fontWeight: 600 }}>{c.bebshax}</span>
                      </div>
                    </td>
                    <td style={{ padding: '20px 24px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <div style={{ width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(15, 23, 42, 0.05)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <X size={14} color="#64748B" />
                        </div>
                        <span style={{ fontSize: '0.88rem', color: '#64748B' }}>{c.traditional}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
};

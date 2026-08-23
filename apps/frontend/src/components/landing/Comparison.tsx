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
            Competitive Matrix
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
            Why high-growth teams{' '}
            <span className="text-gradient-blue">
              switch to BebshaX.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Compare legacy business intelligence approaches against BebshaX’s unified intelligence engine.
          </p>
        </div>

        {/* Table Container (No outer border/outline) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '20px',
            background: '#09090C',
            border: 'none',
            outline: 'none',
            overflow: 'hidden',
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
              <thead>
                <tr>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: '#8E8E93', fontWeight: 600, width: '28%' }}>
                    Capability
                  </th>
                  <th
                    style={{
                      padding: '20px 24px',
                      fontSize: '0.95rem',
                      color: '#FFFFFF',
                      fontWeight: 800,
                      background: 'rgba(255, 255, 255, 0.04)',
                      width: '38%',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Sparkles size={16} color="#F6C878" />
                      <span>BebshaX Intelligence</span>
                    </div>
                  </th>
                  <th style={{ padding: '20px 24px', fontSize: '0.84rem', color: '#8E8E93', fontWeight: 500, width: '34%' }}>
                    Legacy Dashboards & Spreadsheets
                  </th>
                </tr>
              </thead>
              <tbody>
                {criteria.map((c, i) => (
                  <tr
                    key={i}
                    style={{
                      background: i % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)',
                    }}
                  >
                    <td style={{ padding: '18px 24px', fontWeight: 600, color: '#FFFFFF', fontSize: '0.88rem' }}>
                      {c.feature}
                    </td>
                    <td
                      style={{
                        padding: '18px 24px',
                        background: 'rgba(255, 255, 255, 0.03)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ width: '20px', height: '20px', borderRadius: '50%', background: '#FFFFFF', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: 'none' }}>
                          <Check size={12} color="#000000" strokeWidth={3} />
                        </div>
                        <span style={{ fontSize: '0.85rem', color: '#FFFFFF', fontWeight: 600 }}>{c.bebshax}</span>
                      </div>
                    </td>
                    <td style={{ padding: '18px 24px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ width: '20px', height: '20px', borderRadius: '50%', background: 'rgba(255, 255, 255, 0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: 'none' }}>
                          <X size={12} color="#71717A" />
                        </div>
                        <span style={{ fontSize: '0.85rem', color: '#71717A' }}>{c.traditional}</span>
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

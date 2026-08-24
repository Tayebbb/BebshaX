import React from 'react';
import {
  FileSpreadsheet,
  AlertOctagon,
  HelpCircle,
  Hourglass,
  Sparkles,
  CheckCircle,
  XCircle,
} from 'lucide-react';

export const ProblemSection: React.FC = () => {
  const problems = [
    {
      icon: <FileSpreadsheet size={18} color="#EF4444" />,
      title: 'Scattered Spreadsheets & Dashboards',
      description: 'Data locked in 12 different SaaS apps, CRM tables, and outdated CSV exports.',
    },
    {
      icon: <AlertOctagon size={18} color="#EF4444" />,
      title: 'Late Warnings on Lost Revenue',
      description: 'Discovering customer churn and margin decline weeks after it happened.',
    },
    {
      icon: <HelpCircle size={18} color="#EF4444" />,
      title: 'Too Many Charts, Zero Direction',
      description: 'Endless analytics graphs that show numbers but never explain what decision to make next.',
    },
    {
      icon: <Hourglass size={18} color="#EF4444" />,
      title: 'Slow Decision Cycles',
      description: 'Wasting dozens of hours every month manually compiling reports for executive meetings.',
    },
  ];

  return (
    <section
      id="problem"
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
        <div style={{ textAlign: 'center', maxWidth: '780px', margin: '0 auto 64px auto' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: 'none',
              outline: 'none',
              color: '#F87171',
              fontSize: '0.75rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '16px',
            }}
          >
            The Operational Bottleneck
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
            Your business already has the data.{' '}
            <span className="text-gradient-red">
              You just can’t act on it in time.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Most companies operate with blind spots because data is fragmented across separate tools, unaligned teams, and delayed reporting cycles.
          </p>
        </div>

        {/* Comparison Block (No Outlines) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
          }}
        >
          {/* Old Way Card */}
          <div
            className="clean-card"
            style={{
              padding: '36px 32px',
              borderRadius: '20px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: 'none',
                }}
              >
                <XCircle size={18} color="#EF4444" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                The Fragmented Reality
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {problems.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(239, 68, 68, 0.08)', border: 'none' }}>
                    {p.icon}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '3px' }}>
                      {p.title}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#8E8E93', lineHeight: '1.5' }}>
                      {p.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* BebshaX Unified Solution Card */}
          <div
            className="clean-card"
            style={{
              padding: '36px 32px',
              borderRadius: '20px',
              background: '#0D0D12',
              border: 'none',
              outline: 'none',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: '#F6C878',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  border: 'none',
                }}
              >
                <CheckCircle size={18} color="#000000" />
              </div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#FFFFFF' }}>
                The BebshaX Advantage
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
              {[
                {
                  title: 'Unified Operational Graph',
                  desc: 'All billing, product activity, and customer behavior reconciled into a single source of truth.',
                },
                {
                  title: 'Autonomous Anomaly & Risk Alerts',
                  desc: 'Immediate notifications when key metrics diverge, with root causes pre-diagnosed.',
                },
                {
                  title: 'Decision Intelligence, Not Just Graphs',
                  desc: 'Clear, prioritized recommendations with verified evidence and simulated outcomes.',
                },
                {
                  title: 'Instant Execution Playbooks',
                  desc: 'Turn insights into action with 1-click workflows for sales, retention, and growth.',
                },
              ].map((adv, idx) => (
                <div key={idx} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                  <div
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: '50%',
                      background: 'rgba(246, 200, 120, 0.12)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: '2px',
                      border: 'none',
                    }}
                  >
                    <Sparkles size={13} color="#F6C878" />
                  </div>
                  <div>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '3px' }}>
                      {adv.title}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#8E8E93', lineHeight: '1.5' }}>
                      {adv.desc}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

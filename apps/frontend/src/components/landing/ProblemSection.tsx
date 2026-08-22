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
      icon: <FileSpreadsheet size={20} color="#DC2626" />,
      title: 'Scattered Spreadsheets & Dashboards',
      description: 'Data locked in 12 different SaaS apps, CRM tables, and outdated CSV exports.',
    },
    {
      icon: <AlertOctagon size={20} color="#DC2626" />,
      title: 'Late Warnings on Lost Revenue',
      description: 'Discovering customer churn and margin decline weeks after it happened.',
    },
    {
      icon: <HelpCircle size={20} color="#DC2626" />,
      title: 'Too Many Charts, Zero Direction',
      description: 'Endless analytics graphs that show numbers but never explain what decision to make next.',
    },
    {
      icon: <Hourglass size={20} color="#DC2626" />,
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
            className="glass-panel"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '9999px',
              background: 'rgba(254, 242, 242, 0.75)',
              border: '1px solid rgba(254, 202, 202, 0.8)',
              color: '#DC2626',
              fontSize: '0.78rem',
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
              color: '#0F172A',
            }}
          >
            Your business already has the data.{' '}
            <span className="text-gradient-red">
              You just can’t act on it in time.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Most companies operate with blind spots because data is fragmented across separate tools, unaligned teams, and delayed reporting cycles.
          </p>
        </div>

        {/* Comparison Block: Fragmented vs BebshaX Unified */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '32px',
          }}
        >
          {/* Old Way Card */}
          <div
            className="glass-panel"
            style={{
              padding: '36px 32px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.65)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              border: '1px solid rgba(254, 202, 202, 0.6)',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <XCircle size={20} color="#DC2626" />
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A' }}>
                The Fragmented Reality
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {problems.map((p, i) => (
                <div key={i} style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div style={{ padding: '6px', borderRadius: '8px', background: 'rgba(254, 242, 242, 0.8)', border: '1px solid rgba(254, 202, 202, 0.6)' }}>
                    {p.icon}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: '4px' }}>
                      {p.title}
                    </div>
                    <div style={{ fontSize: '0.82rem', color: '#475569', lineHeight: '1.5' }}>
                      {p.description}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* BebshaX Unified Solution Card in Translucent White Glass */}
          <div
            className="glass-panel"
            style={{
              padding: '36px 32px',
              borderRadius: '24px',
              background: 'rgba(255, 255, 255, 0.78)',
              backdropFilter: 'blur(28px)',
              WebkitBackdropFilter: 'blur(28px)',
              border: '1.5px solid rgba(37, 99, 235, 0.4)',
              boxShadow: '0 20px 50px rgba(37, 99, 235, 0.12), var(--shadow-md)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '24px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)',
                }}
              >
                <CheckCircle size={20} color="#FFFFFF" />
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A' }}>
                The BebshaX Advantage
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
                <div key={idx} style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
                  <div
                    style={{
                      width: '26px',
                      height: '26px',
                      borderRadius: '50%',
                      background: 'rgba(37, 99, 235, 0.1)',
                      border: '1px solid rgba(37, 99, 235, 0.25)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: '2px',
                    }}
                  >
                    <Sparkles size={14} color="#2563EB" />
                  </div>
                  <div>
                    <div style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: '4px' }}>
                      {adv.title}
                    </div>
                    <div style={{ fontSize: '0.82rem', color: '#475569', lineHeight: '1.5' }}>
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

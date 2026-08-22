import React, { useState } from 'react';
import {
  LayoutDashboard,
  Cpu,
  Target,
  Workflow,
  Sparkles,
  AlertCircle,
  CheckCircle,
  ArrowRight,
} from 'lucide-react';

export const ProductShowcase: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'cockpit' | 'engine' | 'playbooks' | 'attribution'>('cockpit');

  const tabs = [
    {
      id: 'cockpit' as const,
      label: 'Executive Cockpit',
      icon: <LayoutDashboard size={18} />,
      headline: 'Holistic cross-departmental operations in real-time.',
      description: 'Zero data silos. Monitor revenue health, churn risk, customer lifetime value, and support bottlenecks from a unified executive view.',
    },
    {
      id: 'engine' as const,
      label: 'Diagnostic AI Engine',
      icon: <Cpu size={18} />,
      headline: 'Autonomous anomaly detection and root-cause tracing.',
      description: 'When metrics shift, BebshaX does not just send a graph—it investigates underlying data layers and isolates the precise causal drivers.',
    },
    {
      id: 'playbooks' as const,
      label: 'Action Playbooks',
      icon: <Workflow size={18} />,
      headline: 'Prioritized playbooks tailored to your business model.',
      description: 'Convert diagnostic intelligence into clear, assignable action items with measured revenue impacts and 1-click execution workflows.',
    },
    {
      id: 'attribution' as const,
      label: 'Predictive Forecaster',
      icon: <Target size={18} />,
      headline: 'Simulate business decisions before you spend budget.',
      description: 'Run what-if scenario models on pricing changes, marketing budget reallocations, and sales headcount with evidence-backed certainty.',
    },
  ];

  const currentTab = tabs.find((t) => t.id === activeTab)!;

  return (
    <section
      id="product"
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px auto' }}>
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
            Product Architecture
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
            Everything important.{' '}
            <span className="text-gradient-blue">
              In one intelligent view.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#475569', lineHeight: '1.6' }}>
            Explore the four core modules powering the BebshaX continuous intelligence engine.
          </p>
        </div>

        {/* Tab Navigation Pill Bar in Translucent Glass */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '40px',
          }}
        >
          <div
            className="glass-panel"
            style={{
              display: 'inline-flex',
              flexWrap: 'wrap',
              gap: '8px',
              padding: '8px',
              borderRadius: '16px',
              background: 'rgba(255, 255, 255, 0.65)',
              border: '1px solid rgba(255, 255, 255, 0.8)',
            }}
          >
            {tabs.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 20px',
                    borderRadius: '12px',
                    border: 'none',
                    fontSize: '0.88rem',
                    fontWeight: 700,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    background: isActive
                      ? 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)'
                      : 'transparent',
                    color: isActive ? '#FFFFFF' : '#475569',
                    boxShadow: isActive ? '0 4px 15px rgba(37, 99, 235, 0.3)' : 'none',
                  }}
                >
                  {React.cloneElement(tab.icon, {
                    color: isActive ? '#FFFFFF' : '#2563EB',
                  })}
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Product Module Card Display in Multi-Layer White Glass */}
        <div
          className="glass-panel"
          style={{
            borderRadius: '28px',
            background: 'rgba(255, 255, 255, 0.78)',
            backdropFilter: 'blur(30px)',
            WebkitBackdropFilter: 'blur(30px)',
            border: '1px solid rgba(255, 255, 255, 0.9)',
            padding: '40px',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: '40px',
              alignItems: 'center',
            }}
          >
            {/* Left Description Column */}
            <div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '4px 12px',
                  borderRadius: '8px',
                  background: 'rgba(37, 99, 235, 0.1)',
                  color: '#2563EB',
                  fontSize: '0.78rem',
                  fontWeight: 700,
                  marginBottom: '16px',
                }}
              >
                <Sparkles size={14} color="#2563EB" />
                <span>MODULE ACTIVE</span>
              </div>

              <h3
                style={{
                  fontSize: '1.85rem',
                  fontWeight: 800,
                  letterSpacing: '-0.02em',
                  color: '#0F172A',
                  marginBottom: '16px',
                  lineHeight: 1.25,
                }}
              >
                {currentTab.headline}
              </h3>

              <p
                style={{
                  fontSize: '1rem',
                  color: '#475569',
                  lineHeight: '1.65',
                  marginBottom: '28px',
                }}
              >
                {currentTab.description}
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '32px' }}>
                {[
                  'Instant synchronization across all linked cloud databases',
                  'Grounded in verifiable business event telemetry',
                  'Export-ready presentation cards for stakeholders',
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div
                      style={{
                        width: '20px',
                        height: '20px',
                        borderRadius: '50%',
                        background: 'rgba(37, 99, 235, 0.12)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <CheckCircle size={13} color="#2563EB" />
                    </div>
                    <span style={{ fontSize: '0.88rem', color: '#0F172A', fontWeight: 600 }}>{item}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: '14px' }}>
                <a
                  href="#demo"
                  className="primary-hero-btn"
                  style={{
                    padding: '12px 22px',
                    borderRadius: '12px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '0.9rem',
                    textDecoration: 'none',
                  }}
                >
                  <span>Interactive Sandbox</span>
                  <ArrowRight size={16} color="#FFFFFF" />
                </a>
              </div>
            </div>

            {/* Right Interactive Mock View in High-Translucency Glass */}
            <div
              className="glass-card"
              style={{
                borderRadius: '20px',
                background: 'rgba(255, 255, 255, 0.85)',
                border: '1.5px solid rgba(37, 99, 235, 0.3)',
                padding: '24px',
                boxShadow: '0 20px 40px rgba(15, 23, 42, 0.1)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2563EB' }} />
                  <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>
                    {currentTab.label} Preview
                  </span>
                </div>
                <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600 }}>
                  Updated 2m ago
                </span>
              </div>

              {/* Module-Specific Dynamic Visuals */}
              {activeTab === 'cockpit' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  <div style={{ padding: '16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.85)', border: '1px solid rgba(15, 23, 42, 0.08)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>Net Expansion Velocity</span>
                      <span style={{ fontSize: '0.8rem', color: '#2563EB', fontWeight: 700 }}>+23.4% YoY</span>
                    </div>
                    <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#0F172A' }}>$2.84M</div>
                  </div>

                  <div style={{ padding: '16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.85)', border: '1px solid rgba(15, 23, 42, 0.08)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>Customer Health Index</span>
                      <span style={{ fontSize: '0.8rem', color: '#10B981', fontWeight: 700 }}>98.2 / 100</span>
                    </div>
                    <div style={{ width: '100%', height: '8px', borderRadius: '4px', background: 'rgba(15, 23, 42, 0.08)', overflow: 'hidden' }}>
                      <div style={{ width: '92%', height: '100%', background: 'linear-gradient(90deg, #2563EB, #10B981)' }} />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'engine' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ padding: '14px', borderRadius: '12px', background: 'rgba(254, 242, 242, 0.8)', border: '1px solid rgba(254, 202, 202, 0.7)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#DC2626', fontWeight: 700, fontSize: '0.82rem', marginBottom: '4px' }}>
                      <AlertCircle size={14} /> Anomaly Detected
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#475569' }}>
                      Enterprise churn probability spiked +14% after API rate limit policy change.
                    </div>
                  </div>

                  <div style={{ padding: '14px', borderRadius: '12px', background: 'rgba(239, 246, 255, 0.9)', border: '1px solid rgba(191, 219, 254, 0.8)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#2563EB', fontWeight: 700, fontSize: '0.82rem', marginBottom: '4px' }}>
                      <Sparkles size={14} /> Root Cause Isolated
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#475569' }}>
                      Primary driver: 22 high-volume integration endpoints exceeding tier limits without warning.
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'playbooks' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {[
                    { name: 'Tier Cap Concierge Outreach', impact: '+$42.5k ARR', time: '5 min setup' },
                    { name: 'Onboarding Friction Email Nudge', impact: '+8.4% conversion', time: '1-click deploy' },
                    { name: 'Self-Serve Quota Adjustment', impact: '-18% support load', time: 'Automated' },
                  ].map((p, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', borderRadius: '10px', background: 'rgba(255, 255, 255, 0.85)', border: '1px solid rgba(15, 23, 42, 0.08)' }}>
                      <div>
                        <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A' }}>{p.name}</div>
                        <div style={{ fontSize: '0.72rem', color: '#64748B' }}>{p.time}</div>
                      </div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 800, color: '#2563EB', background: 'rgba(37, 99, 235, 0.1)', padding: '4px 8px', borderRadius: '6px' }}>
                        {p.impact}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === 'attribution' && (
                <div style={{ padding: '16px', borderRadius: '14px', background: 'rgba(255, 255, 255, 0.85)', border: '1px solid rgba(15, 23, 42, 0.08)' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 700, color: '#0F172A', marginBottom: '8px' }}>
                    Scenario Simulation: +15% Expansion Pricing
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '0.78rem', color: '#64748B' }}>Projected Revenue:</span>
                    <strong style={{ color: '#2563EB' }}>+$184,200</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.78rem', color: '#64748B' }}>Expected Churn Impact:</span>
                    <strong style={{ color: '#10B981' }}>&lt; 0.4%</strong>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

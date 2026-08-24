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
      icon: <LayoutDashboard size={16} />,
      headline: 'Holistic cross-departmental operations in real-time.',
      description: 'Zero data silos. Monitor revenue health, churn risk, customer lifetime value, and support bottlenecks from a unified executive view.',
    },
    {
      id: 'engine' as const,
      label: 'Diagnostic Engine',
      icon: <Cpu size={16} />,
      headline: 'Autonomous anomaly detection and root-cause tracing.',
      description: 'When metrics shift, BebshaX does not just send a graph—it investigates underlying data layers and isolates the precise causal drivers.',
    },
    {
      id: 'playbooks' as const,
      label: 'Action Playbooks',
      icon: <Workflow size={16} />,
      headline: 'Prioritized playbooks tailored to your business model.',
      description: 'Convert diagnostic intelligence into clear, assignable action items with measured revenue impacts and 1-click execution workflows.',
    },
    {
      id: 'attribution' as const,
      label: 'Predictive Forecaster',
      icon: <Target size={16} />,
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
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 56px auto' }}>
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
            Product Architecture
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
            Everything important.{' '}
            <span className="text-gradient-blue">
              In one intelligent view.
            </span>
          </h2>

          <p style={{ fontSize: '1.05rem', color: '#8E8E93', lineHeight: '1.6' }}>
            Explore the four core modules powering the BebshaX continuous intelligence engine.
          </p>
        </div>

        {/* Tab Navigation Pill Bar (No outline) */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '36px',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              flexWrap: 'wrap',
              gap: '6px',
              padding: '6px',
              borderRadius: '9999px',
              background: '#09090C',
              border: 'none',
              outline: 'none',
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
                    gap: '6px',
                    padding: '8px 18px',
                    borderRadius: '9999px',
                    border: 'none',
                    outline: 'none',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    background: isActive ? '#FFFFFF' : 'transparent',
                    color: isActive ? '#000000' : '#8E8E93',
                  }}
                >
                  {React.cloneElement(tab.icon, {
                    color: isActive ? '#000000' : '#8E8E93',
                  })}
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Product Module Card Display (No outline) */}
        <div
          className="clean-card"
          style={{
            borderRadius: '24px',
            background: '#09090C',
            border: 'none',
            outline: 'none',
            padding: '36px',
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
                  padding: '4px 10px',
                  borderRadius: '6px',
                  background: 'rgba(246, 200, 120, 0.1)',
                  color: '#F6C878',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  marginBottom: '14px',
                  border: 'none',
                }}
              >
                <Sparkles size={13} color="#F6C878" />
                <span>MODULE ACTIVE</span>
              </div>

              <h3
                style={{
                  fontSize: '1.75rem',
                  fontWeight: 800,
                  letterSpacing: '-0.02em',
                  color: '#FFFFFF',
                  marginBottom: '14px',
                  lineHeight: 1.25,
                }}
              >
                {currentTab.headline}
              </h3>

              <p
                style={{
                  fontSize: '0.95rem',
                  color: '#8E8E93',
                  lineHeight: '1.6',
                  marginBottom: '24px',
                }}
              >
                {currentTab.description}
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '28px' }}>
                {[
                  'Instant synchronization across all linked cloud databases',
                  'Grounded in verifiable business event telemetry',
                  'Export-ready presentation cards for stakeholders',
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div
                      style={{
                        width: '18px',
                        height: '18px',
                        borderRadius: '50%',
                        background: 'rgba(255, 255, 255, 0.06)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: 'none',
                      }}
                    >
                      <CheckCircle size={12} color="#F6C878" />
                    </div>
                    <span style={{ fontSize: '0.84rem', color: '#D4D4D8', fontWeight: 500 }}>{item}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <a
                  href="#demo"
                  className="primary-hero-btn"
                  style={{
                    padding: '10px 20px',
                    borderRadius: '9999px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '0.86rem',
                    textDecoration: 'none',
                    border: 'none',
                    outline: 'none',
                  }}
                >
                  <span>Interactive Sandbox</span>
                  <ArrowRight size={14} color="#000000" />
                </a>
              </div>
            </div>

            {/* Right Interactive Mock View (No outline) */}
            <div
              style={{
                borderRadius: '16px',
                background: '#040406',
                border: 'none',
                outline: 'none',
                padding: '20px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F6C878' }} />
                  <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF' }}>
                    {currentTab.label} Preview
                  </span>
                </div>
                <span style={{ fontSize: '0.68rem', color: '#71717A', fontWeight: 500 }}>
                  Live sync
                </span>
              </div>

              {/* Module-Specific Dynamic Visuals */}
              {activeTab === 'cockpit' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Net Expansion Velocity</span>
                      <span style={{ fontSize: '0.75rem', color: '#F6C878', fontWeight: 700 }}>+23.4% YoY</span>
                    </div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#FFFFFF' }}>$2.84M</div>
                  </div>

                  <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Customer Health Index</span>
                      <span style={{ fontSize: '0.75rem', color: '#10B981', fontWeight: 700 }}>98.2 / 100</span>
                    </div>
                    <div style={{ width: '100%', height: '6px', borderRadius: '3px', background: 'rgba(255, 255, 255, 0.08)', overflow: 'hidden', marginTop: '6px' }}>
                      <div style={{ width: '92%', height: '100%', background: '#F6C878' }} />
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'engine' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', border: 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#F87171', fontWeight: 700, fontSize: '0.78rem', marginBottom: '2px' }}>
                      <AlertCircle size={13} /> Anomaly Detected
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#A1A1AA' }}>
                      Enterprise churn probability spiked +14% after API rate limit policy change.
                    </div>
                  </div>

                  <div style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', border: 'none' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#93C5FD', fontWeight: 700, fontSize: '0.78rem', marginBottom: '2px' }}>
                      <Sparkles size={13} /> Root Cause Isolated
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#A1A1AA' }}>
                      Primary driver: 22 high-volume integration endpoints exceeding tier limits without warning.
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'playbooks' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {[
                    { name: 'Tier Cap Concierge Outreach', impact: '+$42.5k ARR', time: '5 min setup' },
                    { name: 'Onboarding Friction Email Nudge', impact: '+8.4% conversion', time: '1-click deploy' },
                    { name: 'Self-Serve Quota Adjustment', impact: '-18% support load', time: 'Automated' },
                  ].map((p, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 12px', borderRadius: '8px', background: '#0D0D11', border: 'none' }}>
                      <div>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF' }}>{p.name}</div>
                        <div style={{ fontSize: '0.68rem', color: '#71717A' }}>{p.time}</div>
                      </div>
                      <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#F6C878', background: 'rgba(246, 200, 120, 0.12)', padding: '3px 6px', borderRadius: '4px', border: 'none' }}>
                        {p.impact}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {activeTab === 'attribution' && (
                <div style={{ padding: '14px', borderRadius: '10px', background: '#0D0D11', border: 'none' }}>
                  <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#FFFFFF', marginBottom: '6px' }}>
                    Scenario Simulation: +15% Expansion Pricing
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Projected Revenue:</span>
                    <strong style={{ color: '#F6C878' }}>+$184,200</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.75rem', color: '#8E8E93' }}>Expected Churn Impact:</span>
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

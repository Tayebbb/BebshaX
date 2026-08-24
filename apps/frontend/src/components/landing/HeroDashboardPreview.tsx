import React, { useState } from 'react';
import {
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  ArrowUpRight,
  Sparkles,
  Zap,
  Search,
  RefreshCw,
} from 'lucide-react';

export const HeroDashboardPreview: React.FC = () => {
  const [activeMetricTab, setActiveMetricTab] = useState<'revenue' | 'velocity' | 'retention'>('revenue');
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        maxWidth: '1120px',
        margin: '0 auto',
      }}
    >
      {/* Ambient light glow without harsh box */}
      <div
        style={{
          position: 'absolute',
          top: '-15%',
          left: '10%',
          right: '10%',
          height: '130%',
          background: 'radial-gradient(ellipse at center, rgba(246, 200, 120, 0.08) 0%, rgba(59, 130, 246, 0.06) 40%, transparent 70%)',
          filter: 'blur(70px)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Main Container Minimalist Command Center (No outer box outline) */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          background: '#09090C',
          border: 'none',
          outline: 'none',
          borderRadius: '20px',
          boxShadow: '0 30px 80px rgba(0, 0, 0, 0.85)',
          overflow: 'hidden',
          padding: '20px 24px 24px 24px',
        }}
      >
        {/* Top Window Header Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: '16px',
            marginBottom: '20px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#EF4444' }} />
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#F59E0B' }} />
            <div style={{ width: '9px', height: '9px', borderRadius: '50%', background: '#10B981' }} />
            <div style={{ marginLeft: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: '#71717A', fontWeight: 500, fontFamily: 'var(--font-mono)' }}>bebshax.cloud/live/operations-hq</span>
              <span
                style={{
                  fontSize: '0.62rem',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  background: 'rgba(59, 130, 246, 0.12)',
                  color: '#93C5FD',
                  border: 'none',
                  outline: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  fontWeight: 700,
                  letterSpacing: '0.04em',
                }}
              >
                <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#60A5FA' }} />
                STREAM ACTIVE
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 12px',
                background: 'rgba(255, 255, 255, 0.04)',
                borderRadius: '6px',
                border: 'none',
                outline: 'none',
                fontSize: '0.75rem',
                color: '#71717A',
              }}
            >
              <Search size={13} color="#A1A1AA" />
              <span>Filter telemetry...</span>
            </div>
            <button
              style={{
                padding: '6px 9px',
                borderRadius: '6px',
                background: 'rgba(255, 255, 255, 0.04)',
                border: 'none',
                outline: 'none',
                color: '#FFFFFF',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <RefreshCw size={13} />
            </button>
          </div>
        </div>

        {/* Dashboard Grid Content */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '14px' }}>
          
          {/* Top KPI Cards Row (No Outlines) */}
          <div
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'revenue' ? '#14141A' : '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '14px',
              padding: '16px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onClick={() => setActiveMetricTab('revenue')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: '#8E8E93', fontWeight: 500 }}>Monthly Run Rate</span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: '#F6C878',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <TrendingUp size={13} /> +18.4%
              </span>
            </div>
            <div style={{ fontSize: '1.65rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              $148,920
            </div>
            <div style={{ fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
              vs $125,780 previous month
            </div>
          </div>

          <div
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'velocity' ? '#14141A' : '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '14px',
              padding: '16px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onClick={() => setActiveMetricTab('velocity')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: '#8E8E93', fontWeight: 500 }}>Operational Health</span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: '#10B981',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <Zap size={13} color="#10B981" /> OPTIMAL
              </span>
            </div>
            <div style={{ fontSize: '1.65rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              96.4 <span style={{ fontSize: '0.9rem', color: '#71717A', fontWeight: 500 }}>/ 100</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
              0 critical anomalies detected
            </div>
          </div>

          <div
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'retention' ? '#14141A' : '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '14px',
              padding: '16px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onClick={() => setActiveMetricTab('retention')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.78rem', color: '#8E8E93', fontWeight: 500 }}>Decision Velocity</span>
              <span
                style={{
                  fontSize: '0.72rem',
                  color: '#60A5FA',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <ArrowUpRight size={13} /> 3.2×
              </span>
            </div>
            <div style={{ fontSize: '1.65rem', fontWeight: 800, color: '#FFFFFF', letterSpacing: '-0.02em' }}>
              4.2 hrs <span style={{ fontSize: '0.8rem', color: '#71717A', fontWeight: 500 }}>median</span>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#52525B', marginTop: '4px' }}>
              Down from 14.8 hrs manual
            </div>
          </div>

          {/* Middle Main Chart Area (No Outlines) */}
          <div
            style={{
              gridColumn: 'span 8',
              background: '#0D0D11',
              border: 'none',
              outline: 'none',
              borderRadius: '16px',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <div>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#FFFFFF' }}>
                  Unified Intelligence Stream & Growth Forecast
                </div>
                <div style={{ fontSize: '0.75rem', color: '#71717A' }}>
                  Continuous multi-channel sync (CRM, Billing, Product Usage, User Feedback)
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <span style={{ padding: '3px 8px', fontSize: '0.68rem', background: 'rgba(59, 130, 246, 0.15)', color: '#93C5FD', borderRadius: '4px', fontWeight: 700, border: 'none' }}>
                  Realtime
                </span>
                <span style={{ padding: '3px 8px', fontSize: '0.68rem', background: 'rgba(255, 255, 255, 0.04)', color: '#71717A', borderRadius: '4px', fontWeight: 600, border: 'none' }}>
                  30D
                </span>
              </div>
            </div>

            {/* Custom SVG Data Visualization Chart */}
            <div style={{ height: '160px', position: 'relative', width: '100%' }}>
              <svg viewBox="0 0 500 160" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
                <defs>
                  <linearGradient id="blueAreaDarkMinimal" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.35" />
                    <stop offset="100%" stopColor="#3B82F6" stopOpacity="0.0" />
                  </linearGradient>
                  <linearGradient id="skyAreaDarkMinimal" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#F6C878" stopOpacity="0.20" />
                    <stop offset="100%" stopColor="#F6C878" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Horizontal Grid lines */}
                <line x1="0" y1="30" x2="500" y2="30" stroke="rgba(255, 255, 255, 0.05)" strokeDasharray="3 3" />
                <line x1="0" y1="75" x2="500" y2="75" stroke="rgba(255, 255, 255, 0.05)" strokeDasharray="3 3" />
                <line x1="0" y1="120" x2="500" y2="120" stroke="rgba(255, 255, 255, 0.05)" strokeDasharray="3 3" />

                {/* Secondary Baseline Wave */}
                <path
                  d="M 0 130 Q 80 110 160 115 T 320 90 T 500 70 L 500 160 L 0 160 Z"
                  fill="url(#skyAreaDarkMinimal)"
                />
                <path
                  d="M 0 130 Q 80 110 160 115 T 320 90 T 500 70"
                  fill="none"
                  stroke="#F6C878"
                  strokeWidth="1.5"
                  strokeDasharray="4 4"
                />

                {/* Primary Growth Wave */}
                <path
                  d="M 0 115 Q 70 100 140 85 T 280 60 T 420 35 T 500 20 L 500 160 L 0 160 Z"
                  fill="url(#blueAreaDarkMinimal)"
                />
                <path
                  d="M 0 115 Q 70 100 140 85 T 280 60 T 420 35 T 500 20"
                  fill="none"
                  stroke="#60A5FA"
                  strokeWidth="2.5"
                />

                {/* Highlight Nodes */}
                <circle cx="280" cy="60" r="4" fill="#60A5FA" stroke="#000000" strokeWidth="2" />
                <circle cx="420" cy="35" r="4" fill="#F6C878" stroke="#000000" strokeWidth="2" />
                <circle cx="500" cy="20" r="5" fill="#93C5FD" stroke="#000000" strokeWidth="2" />
              </svg>

              {/* Floating Insight Tooltip on Chart */}
              <div
                style={{
                  position: 'absolute',
                  top: '10px',
                  right: '65px',
                  background: '#15151D',
                  border: 'none',
                  outline: 'none',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.6)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <Sparkles size={14} color="#F6C878" />
                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#FFFFFF' }}>Peak Expansion Cohort</div>
                  <div style={{ fontSize: '0.65rem', color: '#F6C878', fontWeight: 600 }}>+$23.1k opportunity identified</div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Live Insights Stream (No Outlines) */}
          <div
            style={{
              gridColumn: 'span 4',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 2px',
              }}
            >
              <div style={{ fontSize: '0.84rem', fontWeight: 700, color: '#FFFFFF', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={14} color="#F6C878" />
                <span>Active Intelligence</span>
              </div>
              <span style={{ fontSize: '0.68rem', color: '#71717A', fontWeight: 600 }}>3 fresh</span>
            </div>

            {/* Insight Card 1 */}
            <div
              onMouseEnter={() => setHoveredCard('c1')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c1' ? '#181822' : '#0D0D11',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                <CheckCircle2 size={13} color="#10B981" />
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#FFFFFF' }}>Revenue Expansion</span>
              </div>
              <p style={{ fontSize: '0.72rem', color: '#8E8E93', lineHeight: '1.4' }}>
                High-value enterprise accounts increased usage by <strong style={{ color: '#F6C878' }}>24%</strong> this cycle.
              </p>
            </div>

            {/* Insight Card 2 */}
            <div
              onMouseEnter={() => setHoveredCard('c2')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c2' ? '#1F1418' : '#140D0F',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                <AlertTriangle size={13} color="#EF4444" />
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#FFFFFF' }}>Retention Alert</span>
              </div>
              <p style={{ fontSize: '0.72rem', color: '#8E8E93', lineHeight: '1.4' }}>
                Mid-market cohort showing 12% drop in weekly engagement.
              </p>
            </div>

            {/* Insight Card 3 */}
            <div
              onMouseEnter={() => setHoveredCard('c3')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c3' ? '#181822' : '#0D0D11',
                border: 'none',
                outline: 'none',
                borderRadius: '10px',
                padding: '12px 14px',
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '3px' }}>
                <Zap size={13} color="#F6C878" />
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#FFFFFF' }}>Playbook Suggested</span>
              </div>
              <p style={{ fontSize: '0.72rem', color: '#8E8E93', lineHeight: '1.4' }}>
                Automate concierge follow-up for 18 at-risk accounts.
              </p>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};

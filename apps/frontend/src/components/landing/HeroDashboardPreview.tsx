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
      {/* Background ambient blue light reflection */}
      <div
        style={{
          position: 'absolute',
          top: '-10%',
          left: '5%',
          right: '5%',
          height: '120%',
          background: 'radial-gradient(ellipse at center, rgba(37, 99, 235, 0.18) 0%, rgba(96, 165, 250, 0.08) 50%, transparent 75%)',
          filter: 'blur(60px)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Main Container White Glass Dashboard */}
      <div
        className="glass-panel"
        style={{
          position: 'relative',
          zIndex: 1,
          background: 'rgba(255, 255, 255, 0.72)',
          backdropFilter: 'blur(30px)',
          WebkitBackdropFilter: 'blur(30px)',
          border: '1px solid rgba(255, 255, 255, 0.85)',
          borderRadius: '24px',
          boxShadow: '0 30px 80px rgba(15, 23, 42, 0.14), 0 0 1px rgba(15, 23, 42, 0.15)',
          overflow: 'hidden',
          padding: '24px',
        }}
      >
        {/* Top Window Header Bar */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingBottom: '18px',
            borderBottom: '1px solid rgba(15, 23, 42, 0.08)',
            marginBottom: '20px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#EF4444' }} />
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#F59E0B' }} />
            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10B981' }} />
            <div style={{ marginLeft: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.82rem', color: '#475569', fontWeight: 600 }}>bebshax.cloud/live/operations-hq</span>
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '3px 8px',
                  borderRadius: '6px',
                  background: 'rgba(37, 99, 235, 0.1)',
                  color: '#2563EB',
                  border: '1px solid rgba(37, 99, 235, 0.25)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  fontWeight: 700,
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#2563EB' }} />
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
                background: 'rgba(255, 255, 255, 0.65)',
                borderRadius: '8px',
                border: '1px solid rgba(15, 23, 42, 0.08)',
                fontSize: '0.78rem',
                color: '#64748B',
              }}
            >
              <Search size={14} color="#2563EB" />
              <span>Filter streams...</span>
            </div>
            <button
              style={{
                padding: '6px 10px',
                borderRadius: '8px',
                background: 'rgba(37, 99, 235, 0.1)',
                border: '1px solid rgba(37, 99, 235, 0.25)',
                color: '#2563EB',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </div>

        {/* Dashboard Grid Content */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '16px' }}>
          
          {/* Top KPI Cards Row */}
          <div
            className="glass-card"
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'revenue' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
              border: activeMetricTab === 'revenue' ? '1.5px solid #2563EB' : '1px solid rgba(255, 255, 255, 0.8)',
              borderRadius: '16px',
              padding: '18px',
              cursor: 'pointer',
              boxShadow: activeMetricTab === 'revenue' ? '0 10px 25px rgba(37, 99, 235, 0.15)' : 'var(--shadow-sm)',
            }}
            onClick={() => setActiveMetricTab('revenue')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>Monthly Run Rate</span>
              <span
                style={{
                  fontSize: '0.75rem',
                  color: '#2563EB',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <TrendingUp size={14} /> +18.4%
              </span>
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>
              $148,920
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748B', marginTop: '4px' }}>
              vs $125,780 previous month
            </div>
          </div>

          <div
            className="glass-card"
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'velocity' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
              border: activeMetricTab === 'velocity' ? '1.5px solid #2563EB' : '1px solid rgba(255, 255, 255, 0.8)',
              borderRadius: '16px',
              padding: '18px',
              cursor: 'pointer',
              boxShadow: activeMetricTab === 'velocity' ? '0 10px 25px rgba(37, 99, 235, 0.15)' : 'var(--shadow-sm)',
            }}
            onClick={() => setActiveMetricTab('velocity')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>Operational Health</span>
              <span
                style={{
                  fontSize: '0.75rem',
                  color: '#10B981',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <Zap size={14} color="#10B981" /> OPTIMAL
              </span>
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>
              96.4 <span style={{ fontSize: '1rem', color: '#64748B' }}>/ 100</span>
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748B', marginTop: '4px' }}>
              0 critical anomalies detected
            </div>
          </div>

          <div
            className="glass-card"
            style={{
              gridColumn: 'span 4',
              background: activeMetricTab === 'retention' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
              border: activeMetricTab === 'retention' ? '1.5px solid #2563EB' : '1px solid rgba(255, 255, 255, 0.8)',
              borderRadius: '16px',
              padding: '18px',
              cursor: 'pointer',
              boxShadow: activeMetricTab === 'retention' ? '0 10px 25px rgba(37, 99, 235, 0.15)' : 'var(--shadow-sm)',
            }}
            onClick={() => setActiveMetricTab('retention')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.8rem', color: '#64748B', fontWeight: 600 }}>Decision Velocity</span>
              <span
                style={{
                  fontSize: '0.75rem',
                  color: '#2563EB',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontWeight: 700,
                }}
              >
                <ArrowUpRight size={14} /> 3.2×
              </span>
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em' }}>
              4.2 hrs <span style={{ fontSize: '0.85rem', color: '#64748B' }}>median</span>
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748B', marginTop: '4px' }}>
              Down from 14.8 hrs manual
            </div>
          </div>

          {/* Middle Main Chart Area */}
          <div
            className="glass-card"
            style={{
              gridColumn: 'span 8',
              background: 'rgba(255, 255, 255, 0.75)',
              border: '1px solid rgba(255, 255, 255, 0.85)',
              borderRadius: '18px',
              padding: '22px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#0F172A' }}>
                  Unified Intelligence Stream & Growth Forecast
                </div>
                <div style={{ fontSize: '0.78rem', color: '#64748B' }}>
                  Continuous multi-channel sync (CRM, Billing, Product Usage, User Feedback)
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px' }}>
                <span style={{ padding: '4px 10px', fontSize: '0.72rem', background: 'rgba(37, 99, 235, 0.1)', color: '#2563EB', borderRadius: '6px', fontWeight: 700 }}>
                  Realtime
                </span>
                <span style={{ padding: '4px 10px', fontSize: '0.72rem', background: 'rgba(15, 23, 42, 0.05)', color: '#64748B', borderRadius: '6px', fontWeight: 600 }}>
                  30D
                </span>
              </div>
            </div>

            {/* Custom SVG Data Visualization Chart in Vibrant Electric Blue */}
            <div style={{ height: '170px', position: 'relative', width: '100%' }}>
              <svg viewBox="0 0 500 160" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
                <defs>
                  <linearGradient id="blueArea" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#2563EB" stopOpacity="0.32" />
                    <stop offset="100%" stopColor="#2563EB" stopOpacity="0.0" />
                  </linearGradient>
                  <linearGradient id="skyArea" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stopColor="#60A5FA" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#60A5FA" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Horizontal Grid lines */}
                <line x1="0" y1="30" x2="500" y2="30" stroke="rgba(15, 23, 42, 0.06)" strokeDasharray="3 3" />
                <line x1="0" y1="75" x2="500" y2="75" stroke="rgba(15, 23, 42, 0.06)" strokeDasharray="3 3" />
                <line x1="0" y1="120" x2="500" y2="120" stroke="rgba(15, 23, 42, 0.06)" strokeDasharray="3 3" />

                {/* Secondary Baseline Wave */}
                <path
                  d="M 0 130 Q 80 110 160 115 T 320 90 T 500 70 L 500 160 L 0 160 Z"
                  fill="url(#skyArea)"
                />
                <path
                  d="M 0 130 Q 80 110 160 115 T 320 90 T 500 70"
                  fill="none"
                  stroke="#93C5FD"
                  strokeWidth="2"
                  strokeDasharray="4 4"
                />

                {/* Primary Growth Wave */}
                <path
                  d="M 0 115 Q 70 100 140 85 T 280 60 T 420 35 T 500 20 L 500 160 L 0 160 Z"
                  fill="url(#blueArea)"
                />
                <path
                  d="M 0 115 Q 70 100 140 85 T 280 60 T 420 35 T 500 20"
                  fill="none"
                  stroke="#2563EB"
                  strokeWidth="3.5"
                />

                {/* Highlight Nodes */}
                <circle cx="280" cy="60" r="5" fill="#3B82F6" stroke="#FFFFFF" strokeWidth="2" />
                <circle cx="420" cy="35" r="5" fill="#2563EB" stroke="#FFFFFF" strokeWidth="2" />
                <circle cx="500" cy="20" r="6.5" fill="#1D4ED8" stroke="#FFFFFF" strokeWidth="2.5" />
              </svg>

              {/* Floating Insight Glass Tooltip on Chart */}
              <div
                className="glass-card"
                style={{
                  position: 'absolute',
                  top: '10px',
                  right: '65px',
                  background: 'rgba(255, 255, 255, 0.95)',
                  border: '1px solid rgba(37, 99, 235, 0.3)',
                  borderRadius: '10px',
                  padding: '8px 14px',
                  boxShadow: '0 10px 25px rgba(15, 23, 42, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <Sparkles size={15} color="#2563EB" />
                <div>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#0F172A' }}>Peak Expansion Cohort</div>
                  <div style={{ fontSize: '0.68rem', color: '#2563EB', fontWeight: 600 }}>+$23.1k opportunity identified</div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Live Insights Stream */}
          <div
            style={{
              gridColumn: 'span 4',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0 4px',
              }}
            >
              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#0F172A', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Sparkles size={15} color="#2563EB" />
                <span>Active Intelligence</span>
              </div>
              <span style={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 600 }}>3 fresh</span>
            </div>

            {/* Insight Card 1 */}
            <div
              className="glass-card"
              onMouseEnter={() => setHoveredCard('c1')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c1' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
                border: '1px solid rgba(37, 99, 235, 0.25)',
                borderRadius: '12px',
                padding: '12px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <CheckCircle2 size={14} color="#10B981" />
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#0F172A' }}>Revenue Expansion</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: '#475569', lineHeight: '1.4' }}>
                High-value enterprise accounts increased usage by <strong style={{ color: '#2563EB' }}>24%</strong> this cycle.
              </p>
            </div>

            {/* Insight Card 2 */}
            <div
              className="glass-card"
              onMouseEnter={() => setHoveredCard('c2')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c2' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: '12px',
                padding: '12px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <AlertTriangle size={14} color="#EF4444" />
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#0F172A' }}>Retention Alert</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: '#475569', lineHeight: '1.4' }}>
                Mid-market cohort showing 12% drop in weekly engagement.
              </p>
            </div>

            {/* Insight Card 3 */}
            <div
              className="glass-card"
              onMouseEnter={() => setHoveredCard('c3')}
              onMouseLeave={() => setHoveredCard(null)}
              style={{
                background: hoveredCard === 'c3' ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 255, 255, 0.65)',
                border: '1px solid rgba(37, 99, 235, 0.25)',
                borderRadius: '12px',
                padding: '12px 14px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                <Zap size={14} color="#2563EB" />
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#0F172A' }}>Playbook Suggested</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: '#475569', lineHeight: '1.4' }}>
                Automate concierge follow-up for 18 at-risk accounts.
              </p>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};

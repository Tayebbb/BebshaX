import React from 'react';

interface SidebarProps {
  currentView: string;
  onSelectView: (view: string) => void;
}

interface NavItem {
  id: string;
  label: string;
  icon: string;
  phase: string;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onSelectView }) => {
  const navItems: NavItem[] = [
    { id: 'routing', label: 'Routing Dashboard', icon: '⚡', phase: 'Phase 5' },
    { id: 'businesses', label: 'Business Setup', icon: '🏢', phase: 'Phase 6' },
    { id: 'personas', label: 'Persona Engine', icon: '🧬', phase: 'Phase 8' },
    { id: 'memory', label: 'Persona Memory', icon: '🧠', phase: 'Phase 9' },
    { id: 'interviews', label: 'Interview Chat', icon: '💬', phase: 'Phase 10' },
    { id: 'evaluation', label: 'Eval & Benchmarks', icon: '📊', phase: 'Phase 11' },
  ];

  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '28px', paddingLeft: '8px' }}>
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #6366f1 0%, #38bdf8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '18px',
            boxShadow: 'var(--glow-indigo)',
          }}
        >
          ⚡
        </div>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, letterSpacing: '-0.03em', color: '#fff' }}>BebshaX</h2>
          <p style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Multi-Model Routing
          </p>
        </div>
      </div>

      {/* Navigation Section */}
      <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', paddingLeft: '8px', marginBottom: '8px' }}>
        Core Views
      </div>
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
        {navItems.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectView(item.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 12px',
                borderRadius: '8px',
                border: 'none',
                background: isActive ? 'linear-gradient(90deg, rgba(99,102,241,0.2) 0%, rgba(56,189,248,0.1) 100%)' : 'transparent',
                color: isActive ? '#fff' : 'var(--text-muted)',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s ease',
                outline: 'none',
                boxShadow: isActive ? 'inset 2px 0 0 #6366f1' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '1.1rem' }}>{item.icon}</span>
                <span style={{ fontSize: '0.85rem', fontWeight: isActive ? 600 : 500 }}>{item.label}</span>
              </div>
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: isActive ? 'rgba(99,102,241,0.3)' : 'rgba(255,255,255,0.05)',
                  color: isActive ? '#c7d2fe' : 'var(--text-dim)',
                }}
              >
                {item.phase}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div
        className="glass-panel"
        style={{
          padding: '12px',
          fontSize: '0.72rem',
          color: 'var(--text-muted)',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Budget:</span>
          <span style={{ color: '#34d399', fontWeight: 600 }}>$0.00 (Free Tiers)</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Local Fallback:</span>
          <span style={{ color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>Ollama 3B</span>
        </div>
      </div>
    </aside>
  );
};

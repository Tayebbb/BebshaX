import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { HealthResponse } from '../types';

interface NavbarProps {
  currentView: string;
}

export const Navbar: React.FC<NavbarProps> = ({ currentView }) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isLive, setIsLive] = useState<boolean>(false);

  useEffect(() => {
    const checkHealth = async () => {
      const data = await api.getHealth();
      setHealth(data);
      setIsLive(data.app === 'BebshaX');
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const titles: Record<string, { title: string; subtitle: string }> = {
    routing: { title: 'LLM Routing & Provenance', subtitle: 'Live model ranking, failure failover paths, and trace records' },
    businesses: { title: 'Business & Product Setup', subtitle: 'Target market definitions and commercial context' },
    personas: { title: 'Synthetic Persona Engine', subtitle: 'Evidence-grounded personas with OBSERVED / INFERRED / SYNTHETIC badges' },
    memory: { title: 'Persona Memory Stream', subtitle: 'Vector semantic, episodic, and reflection streams' },
    interviews: { title: 'Interview Simulation', subtitle: 'Turn-by-turn interactive research simulation' },
    evaluation: { title: 'Evaluation & Strategy Benchmarks', subtitle: 'Grounded ratio, schema validity, and routing strategy analysis' },
  };

  const current = titles[currentView] || { title: 'BebshaX Platform', subtitle: 'Synthetic Persona Research System' };

  return (
    <header className="navbar" role="banner">
      <div>
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>{current.title}</h1>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{current.subtitle}</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Backend status indicator */}
        <div
          className="glass-panel"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 12px',
            fontSize: '0.78rem',
            borderRadius: '20px',
          }}
          title={isLive ? 'Connected to FastAPI Backend' : 'Running on Mock Data Layer (VITE_MOCK=1)'}
        >
          <span className={`pulse-dot ${isLive ? '' : 'offline'}`} />
          <span style={{ fontWeight: 600, color: isLive ? '#34d399' : '#fbbf24' }}>
            {isLive ? 'Backend Online (Port 8000)' : 'Mock Mode Active'}
          </span>
          <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem' }}>
            v{health?.version || '0.1.0'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <span style={{ background: 'rgba(255,255,255,0.06)', padding: '4px 8px', borderRadius: '6px' }}>
            Port 5433 (pgvector)
          </span>
        </div>
      </div>
    </header>
  );
};

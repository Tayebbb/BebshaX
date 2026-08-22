import React, { useEffect, useState } from 'react';
import { api } from './services/api';
import { HealthResponse } from './types';

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      const res = await api.getHealth();
      setHealth(res);
    };
    fetchHealth();
  }, []);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
      <div className="glass-panel" style={{ maxWidth: '480px', width: '100%', padding: '32px', textAlign: 'center' }}>
        <div style={{ fontSize: '36px', marginBottom: '12px' }}>⚡</div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '8px', color: '#fff' }}>BebshaX</h1>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '24px' }}>
          Synthetic Persona Research Platform (Minimal Shell)
        </p>

        <div style={{ background: 'rgba(255, 255, 255, 0.03)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px', fontSize: '0.8rem', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-dim)' }}>Backend Status:</span>
            <span style={{ color: '#34d399', fontWeight: 600 }}>{health?.status || 'Connecting...'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-dim)' }}>App Name:</span>
            <span style={{ color: '#fff' }}>{health?.app || 'BebshaX'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-dim)' }}>Version:</span>
            <span style={{ color: '#38bdf8' }}>v{health?.version || '0.1.0'}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;

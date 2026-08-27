import React, { useState, useEffect } from 'react';
import { api } from '../../../services/api';
import { OpenRouterHealth } from '../../../types/dataset';
import { RefreshCw, Cpu, Activity, KeyRound, ShieldCheck, X } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export const OpenRouterDiagnosticModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const [health, setHealth] = useState<OpenRouterHealth | null>(null);
  const [modelInput, setModelInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadHealth();
    }
  }, [isOpen]);

  const loadHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getOpenRouterHealth();
      setHealth(data);
      if (data.model && !modelInput) {
        setModelInput(data.model);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to check OpenRouter status');
    } finally {
      setLoading(false);
    }
  };

  const handleRunTest = async () => {
    setTesting(true);
    setError(null);
    try {
      const result = await api.testOpenRouterConnection(modelInput.trim() || undefined);
      setHealth(result);
    } catch (err: any) {
      setError(err.message || 'OpenRouter test request failed');
    } finally {
      setTesting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(6px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 100,
      padding: '20px',
    }}>
      <div style={{
        background: '#121417',
        border: '1px solid var(--border-soft)',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '640px',
        overflow: 'hidden',
        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.6)',
      }}>
        {/* Modal Header */}
        <div style={{
          padding: '18px 24px',
          borderBottom: '1px solid var(--fill-soft-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--fill-soft)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              background: 'rgba(59, 130, 246, 0.15)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#60a5fa',
            }}>
              <Cpu size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)' }}>
                OpenRouter Diagnostic Panel
              </h3>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Server-side API key health & live completion verification
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Key Security Notice */}
          <div style={{
            padding: '12px 16px',
            borderRadius: '10px',
            background: 'rgba(34, 197, 94, 0.08)',
            border: '1px solid rgba(34, 197, 94, 0.2)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '12px',
          }}>
            <ShieldCheck size={18} color="#4ade80" style={{ marginTop: '2px', flexShrink: 0 }} />
            <div style={{ fontSize: '0.82rem', color: '#dcfce7', lineHeight: 1.4 }}>
              <strong>Zero-Leak Architecture:</strong> The <code>OPENROUTER_API_KEY</code> is loaded only in the backend server and is never sent to or stored in the browser client.
            </div>
          </div>

          {/* Configuration Status Card */}
          <div style={{
            background: 'var(--fill-soft)',
            border: '1px solid var(--fill-soft-2)',
            borderRadius: '12px',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <KeyRound size={14} /> Server Configuration
              </span>
              <span style={{
                fontSize: '0.78rem',
                fontWeight: 600,
                padding: '3px 8px',
                borderRadius: '6px',
                background: health?.configured ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                color: health?.configured ? '#4ade80' : 'var(--status-error-text)',
                border: `1px solid ${health?.configured ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              }}>
                {health?.configured ? 'KEY CONFIGURED' : 'MISSING KEY'}
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Activity size={14} /> Connection Status
              </span>
              <span style={{
                fontSize: '0.78rem',
                fontWeight: 600,
                padding: '3px 8px',
                borderRadius: '6px',
                background: health?.status === 'healthy' ? 'rgba(34, 197, 94, 0.15)' : health?.status === 'rate_limited' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                color: health?.status === 'healthy' ? '#4ade80' : health?.status === 'rate_limited' ? '#fbbf24' : 'var(--status-error-text)',
              }}>
                {health?.status === 'healthy' ? 'CONNECTED & VERIFIED' : health?.status?.toUpperCase() || 'UNKNOWN'}
              </span>
            </div>

            {health?.latency_ms !== undefined && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>Round-trip Latency</span>
                <span style={{ fontSize: '0.84rem', color: '#60a5fa', fontWeight: 600 }}>{health.latency_ms} ms</span>
              </div>
            )}
          </div>

          {/* Model Selection Input */}
          <div>
            <label style={{ display: 'block', fontSize: '0.82rem', color: 'var(--text-primary)', marginBottom: '6px', fontWeight: 500 }}>
              Test Target Model:
            </label>
            <input
              type="text"
              value={modelInput}
              onChange={(e) => setModelInput(e.target.value)}
              placeholder="e.g. meta-llama/llama-3.3-70b-instruct:free"
              style={{
                width: '100%',
                background: 'rgba(0, 0, 0, 0.3)',
                border: '1px solid var(--border-soft)',
                borderRadius: '8px',
                padding: '10px 14px',
                color: 'var(--text-main)',
                fontSize: '0.86rem',
                outline: 'none',
              }}
            />
            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              Defaults to <code>OPENROUTER_MODEL</code> or <code>meta-llama/llama-3.3-70b-instruct:free</code>.
            </div>
          </div>

          {/* Diagnostic Message */}
          {health?.message && (
            <div style={{
              padding: '12px 14px',
              borderRadius: '8px',
              background: health.status === 'healthy' ? 'rgba(34, 197, 94, 0.06)' : 'rgba(239, 68, 68, 0.06)',
              border: `1px solid ${health.status === 'healthy' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
              fontSize: '0.82rem',
              color: health.status === 'healthy' ? '#86efac' : 'var(--status-error-text)',
            }}>
              {health.message}
            </div>
          )}

          {error && (
            <div style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(239, 68, 68, 0.1)', color: 'var(--status-error-text)', fontSize: '0.82rem' }}>
              {error}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--fill-soft-2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--fill-soft)',
        }}>
          <button
            onClick={loadHealth}
            disabled={loading}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-soft)',
              borderRadius: '8px',
              padding: '8px 14px',
              color: 'var(--text-muted)',
              fontSize: '0.82rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>

          <button
            onClick={handleRunTest}
            disabled={testing}
            style={{
              background: '#3b82f6',
              border: 'none',
              borderRadius: '8px',
              padding: '9px 18px',
              color: 'var(--text-main)',
              fontSize: '0.84rem',
              fontWeight: 600,
              cursor: testing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
            }}
          >
            {testing ? <RefreshCw size={15} className="animate-spin" /> : <Activity size={15} />}
            {testing ? 'Testing OpenRouter...' : 'Test OpenRouter Connection'}
          </button>
        </div>
      </div>
    </div>
  );
};

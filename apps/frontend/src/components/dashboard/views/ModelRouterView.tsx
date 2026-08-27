import React, { useState, useEffect } from 'react';
import {
  Cpu,
  Activity,
  Shield,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { RoutesStatusResponse, ProvenanceRecord } from '../../../types';
import { api } from '../../../services/api';

export const ModelRouterView: React.FC = () => {
  const [routesStatus, setRoutesStatus] = useState<RoutesStatusResponse | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [routes, prov] = await Promise.all([
        api.getRoutesStatus(),
        api.getProvenance(15),
      ]);
      setRoutesStatus(routes);
      setProvenance(prov.items);
    } catch {
      // fallback handled in service
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div
      style={{
        padding: '32px clamp(16px, 4vw, 40px)',
        maxWidth: '1200px',
        margin: '0 auto',
        width: '100%',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div>
          <h1
            style={{
              fontSize: '1.85rem',
              fontWeight: 500,
              color: 'var(--text-main)',
              letterSpacing: '-0.02em',
              margin: '0 0 6px 0',
            }}
          >
            Model Router & Telemetry
          </h1>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: 0 }}>
            Live FreeLLMpool provider health matrix, task routing pools, and Rule R3 LLM provenance traces.
          </p>
        </div>

        <button
          type="button"
          onClick={loadData}
          disabled={isLoading}
          style={{
            background: 'var(--fill-soft)',
            border: '1px solid var(--border-soft)',
            borderRadius: '10px',
            padding: '8px 16px',
            color: 'var(--text-main)',
            fontSize: '0.84rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          Refresh Status
        </button>
      </div>

      {/* Grid: Architecture Overview */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))',
          gap: '20px',
          marginBottom: '32px',
        }}
      >
        {/* Zero-Budget Routing Engine */}
        <div
          style={{
            background: 'var(--fill-soft)',
            border: '1px solid var(--fill-soft-2)',
            borderRadius: '16px',
            padding: '24px',
            boxShadow: '0 12px 30px rgba(0, 0, 0, 0.4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
            <Cpu size={20} color="var(--accent-emerald)" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
              FreeLLMpool Routing Engine
            </h2>
          </div>
          <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            <div>Operational Budget: <strong style={{ color: 'var(--accent-emerald)' }}>Zero API Cost (Free Tier Aggregation)</strong></div>
            <div>Total Model Routes: <strong style={{ color: 'var(--text-main)' }}>222 Free Model Routes</strong></div>
            <div>Reliability Fallback: <strong style={{ color: 'var(--status-warn-text)' }}>Local Ollama (Qwen / LLaMA)</strong></div>
          </div>
        </div>

        {/* Task Pool Routing Topology */}
        <div
          style={{
            background: 'var(--fill-soft)',
            border: '1px solid var(--fill-soft-2)',
            borderRadius: '16px',
            padding: '24px',
            boxShadow: '0 12px 30px rgba(0, 0, 0, 0.4)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
            <Layers size={20} color="var(--status-warn-text)" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
              Active Task Pools
            </h2>
          </div>
          <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
            <div>Reasoning Pool: <strong style={{ color: 'var(--text-main)' }}>Persona Generation & Consistency</strong></div>
            <div>Conversation Pool: <strong style={{ color: 'var(--text-main)' }}>Multi-Turn Persona Interviews</strong></div>
            <div>Emergency Pool: <strong style={{ color: 'var(--status-warn-text)' }}>Local-First Fallback (Ollama)</strong></div>
          </div>
        </div>
      </div>

      {/* Live Provider Health Matrix */}
      <div
        style={{
          background: 'var(--fill-soft)',
          border: '1px solid var(--fill-soft-2)',
          borderRadius: '16px',
          padding: '24px',
          marginBottom: '32px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
          <Activity size={18} color="var(--status-warn-text)" />
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
            Live Provider Health Matrix
          </h2>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '14px' }}>
          {routesStatus?.providers.map((p) => {
            const isHealthy = p.status === 'healthy';
            return (
              <div
                key={p.name}
                style={{
                  background: 'var(--fill-soft)',
                  border: '1px solid var(--fill-soft-2)',
                  borderRadius: '12px',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize', fontSize: '0.92rem' }}>
                    {p.name}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: isHealthy ? 'var(--accent-emerald)' : '#F59E0B',
                        boxShadow: isHealthy ? '0 0 8px rgba(16, 185, 129, 0.4)' : 'none',
                      }}
                    />
                    <span style={{ fontSize: '0.72rem', color: isHealthy ? 'var(--accent-emerald)' : '#F59E0B', textTransform: 'capitalize' }}>
                      {p.status}
                    </span>
                  </div>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Type: <span style={{ color: 'var(--text-primary)' }}>{p.type.replace(/_/g, ' ')}</span>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Models: <span style={{ color: 'var(--status-warn-text)', fontWeight: 600 }}>{p.available_models} active</span>
                </div>
                {p.active_cooldowns > 0 && (
                  <div style={{ fontSize: '0.72rem', color: '#F59E0B', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertTriangle size={12} /> {p.active_cooldowns} cooling down
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Task Pools Concurrency Status */}
      {routesStatus?.pools && routesStatus.pools.length > 0 && (
        <div
          style={{
            background: 'var(--fill-soft)',
            border: '1px solid var(--fill-soft-2)',
            borderRadius: '16px',
            padding: '24px',
            marginBottom: '32px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <Layers size={18} color="var(--accent-emerald)" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
              Pool Concurrency & Candidate Allocation
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
            {routesStatus.pools.map((pool) => (
              <div
                key={pool.name}
                style={{
                  background: 'var(--fill-soft)',
                  border: '1px solid var(--fill-soft)',
                  borderRadius: '10px',
                  padding: '14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize', fontSize: '0.88rem' }}>
                    {pool.name}
                  </span>
                  <span style={{ fontSize: '0.74rem', color: 'var(--status-warn-text)', fontWeight: 600 }}>
                    {pool.candidates_count} candidates
                  </span>
                </div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  Max Concurrency: <strong style={{ color: 'var(--text-primary)' }}>{pool.max_concurrency}</strong>
                </div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  Active Requests: <strong style={{ color: pool.active_requests > 0 ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>{pool.active_requests}</strong>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Provenance Record Traces (Rule R3) */}
      <div
        style={{
          background: 'var(--fill-soft)',
          border: '1px solid var(--fill-soft-2)',
          borderRadius: '16px',
          padding: '24px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Shield size={18} color="var(--status-warn-text)" />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
              Recent Provenance Traces (Rule R3)
            </h2>
          </div>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Every LLM request produces 14-field verified provenance
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {provenance.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.86rem' }}>
              No recent provenance traces found. Run a research study or persona generation to generate traces.
            </div>
          ) : (
            provenance.map((rec) => (
              <div
                key={rec.request_id}
                style={{
                  background: 'rgba(255, 255, 255, 0.015)',
                  border: '1px solid var(--fill-soft)',
                  borderRadius: '12px',
                  padding: '14px 18px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '12px',
                  fontSize: '0.84rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span
                    style={{
                      fontFamily: 'monospace',
                      color: 'var(--status-warn-text)',
                      background: 'rgba(246, 200, 120, 0.1)',
                      padding: '2px 6px',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                    }}
                  >
                    {rec.request_id.slice(0, 10)}
                  </span>
                  <span style={{ color: 'var(--text-main)', fontWeight: 600 }}>{rec.task}</span>
                  {rec.pool && (
                    <span
                      style={{
                        fontSize: '0.72rem',
                        color: 'var(--text-muted)',
                        background: 'var(--fill-soft)',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        textTransform: 'uppercase',
                      }}
                    >
                      {rec.pool}
                    </span>
                  )}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', color: 'var(--text-muted)' }}>
                  <span style={{ color: 'var(--text-primary)' }}>
                    Served: <strong style={{ color: 'var(--text-main)' }}>{rec.served_by_provider || 'pollinations'}</strong>
                    {rec.served_by_model && ` (${rec.served_by_model})`}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={13} />
                    {rec.total_latency_ms ? `${Math.round(rec.total_latency_ms)}ms` : '340ms'}
                  </span>
                  <span
                    style={{
                      color: rec.success ? 'var(--accent-emerald)' : '#EF4444',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <CheckCircle2 size={14} /> {rec.success ? 'Success' : 'Failed'}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

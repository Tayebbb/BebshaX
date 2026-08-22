import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { ProvenanceRecord, RoutesStatusResponse } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { JsonViewerModal } from '../components/JsonViewerModal';

export const RoutingDashboardView: React.FC = () => {
  const [provenance, setProvenance] = useState<ProvenanceRecord[]>([]);
  const [routesStatus, setRoutesStatus] = useState<RoutesStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedRecord, setSelectedRecord] = useState<ProvenanceRecord | null>(null);
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      const [provData, statusData] = await Promise.all([
        api.getProvenance(50),
        api.getRoutesStatus(),
      ]);
      setProvenance(provData.items);
      setRoutesStatus(statusData);
      setLoading(false);
    };
    fetchData();
  }, []);

  const totalRequests = provenance.length;
  const successfulRequests = provenance.filter((r) => r.success).length;
  const successRate = totalRequests > 0 ? ((successfulRequests / totalRequests) * 100).toFixed(1) : '100';
  const avgLatency =
    totalRequests > 0
      ? (provenance.reduce((acc, r) => acc + (r.total_latency_ms || 0), 0) / totalRequests).toFixed(0)
      : '0';
  const totalTokens = provenance.reduce((acc, r) => acc + (r.input_tokens || 0) + (r.output_tokens || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px' }}>
        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
            Total Governed Calls
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#fff' }}>{totalRequests}</div>
          <div style={{ fontSize: '0.72rem', color: '#34d399', marginTop: '4px' }}>100% Provenance Traceable</div>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
            Routing Success Rate
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#34d399' }}>{successRate}%</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>Zero silent degradation (R2)</div>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
            Avg Roundtrip Latency
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#38bdf8' }}>{avgLatency} ms</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>Includes failovers & retries</div>
        </div>

        <div className="glass-panel" style={{ padding: '20px' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
            Token Usage (Free Tiers)
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#c084fc' }}>{totalTokens.toLocaleString()}</div>
          <div style={{ fontSize: '0.72rem', color: '#34d399', marginTop: '4px' }}>Est. Cost: $0.00</div>
        </div>
      </div>

      {/* Provider & Pools Overview */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* Providers */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>🌐</span> Active Providers & Free Tier Status
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
            {routesStatus?.providers.map((p) => (
              <div
                key={p.name}
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  padding: '12px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.88rem', textTransform: 'capitalize' }}>{p.name}</span>
                  <StatusBadge type="status" value={p.status} />
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Type: <span style={{ color: '#fff' }}>{p.type}</span>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Models: <span style={{ color: '#38bdf8' }}>{p.available_models}</span> | Cooldowns:{' '}
                  <span style={{ color: p.active_cooldowns > 0 ? '#fb7185' : '#34d399' }}>{p.active_cooldowns}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Candidate Pools */}
        <div className="glass-panel" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>⚙</span> Task Pools & Semaphores
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {routesStatus?.pools.map((pool) => (
              <div
                key={pool.name}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: '0.78rem',
                  padding: '8px 10px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: '6px',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <span style={{ fontWeight: 600, color: '#c7d2fe' }}>{pool.name}</span>
                <span style={{ color: 'var(--text-muted)' }}>
                  Active: <strong style={{ color: '#38bdf8' }}>{pool.active_requests}</strong> / Max: {pool.max_concurrency}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Provenance Request Log */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h3 style={{ fontSize: '1.05rem', color: '#fff' }}>LLM Request Provenance Log</h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Every LLM call captures 14 provenance fields persisted to PostgreSQL (`llm_requests` table)
            </p>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Showing last {provenance.length} records</span>
        </div>

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading provenance traces...</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {provenance.map((req) => {
              const isExpanded = expandedRequestId === req.request_id;
              const hasFallback = req.attempts.length > 1;

              return (
                <div
                  key={req.request_id}
                  style={{
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '10px',
                    overflow: 'hidden',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {/* Row Header */}
                  <div
                    style={{
                      padding: '14px 18px',
                      display: 'grid',
                      gridTemplateColumns: '1.2fr 1.5fr 1.5fr 1fr 1fr 1fr auto',
                      alignItems: 'center',
                      gap: '12px',
                      cursor: 'pointer',
                      background: isExpanded ? 'rgba(255, 255, 255, 0.03)' : 'transparent',
                    }}
                    onClick={() => setExpandedRequestId(isExpanded ? null : req.request_id)}
                  >
                    <div>
                      <div className="mono" style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff' }}>
                        {req.request_id.slice(0, 14)}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                        {new Date(req.created_at).toLocaleTimeString()}
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#93c5fd' }}>{req.task}</span>
                      {req.pool && (
                        <div style={{ marginTop: '2px' }}>
                          <StatusBadge type="pool" value={req.pool} />
                        </div>
                      )}
                    </div>

                    <div>
                      <div style={{ fontSize: '0.78rem', color: '#fff', fontWeight: 500 }}>
                        {req.served_by_provider ? `${req.served_by_provider}/${req.served_by_model}` : 'Unserved'}
                      </div>
                      {hasFallback && (
                        <span style={{ fontSize: '0.68rem', color: '#f59e0b', fontWeight: 600 }}>
                          ⚡ Failover ({req.attempts.length} attempts)
                        </span>
                      )}
                    </div>

                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      <strong style={{ color: '#fff' }}>{req.total_latency_ms?.toFixed(0) || '0'}</strong> ms
                    </div>

                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {((req.input_tokens || 0) + (req.output_tokens || 0)).toLocaleString()} tok
                    </div>

                    <div>
                      <StatusBadge type="status" value={req.success ? 'success' : 'failed'} />
                    </div>

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedRecord(req);
                        }}
                      >
                        JSON
                      </button>
                      <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem', alignSelf: 'center' }}>
                        {isExpanded ? '▲' : '▼'}
                      </span>
                    </div>
                  </div>

                  {/* Expanded Trace Breakdown */}
                  {isExpanded && (
                    <div
                      style={{
                        padding: '16px 20px',
                        borderTop: '1px solid var(--border-subtle)',
                        background: 'rgba(0, 0, 0, 0.25)',
                      }}
                    >
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '10px' }}>
                        ROUTING PATH & ATTEMPT TRACE:
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {req.attempts.map((attempt) => (
                          <div
                            key={attempt.attempt_number}
                            style={{
                              padding: '10px 14px',
                              borderRadius: '8px',
                              background: attempt.success ? 'rgba(16, 185, 129, 0.06)' : 'rgba(244, 63, 94, 0.08)',
                              border: `1px solid ${attempt.success ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.25)'}`,
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                            }}
                          >
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fff' }}>
                                  Attempt #{attempt.attempt_number}:
                                </span>
                                <span className="mono" style={{ fontSize: '0.8rem', color: '#38bdf8' }}>
                                  {attempt.provider}/{attempt.model}
                                </span>
                                <StatusBadge type="status" value={attempt.success ? 'success' : 'failed'} />
                              </div>

                              {attempt.failure_detail && (
                                <div style={{ fontSize: '0.72rem', color: '#fb7185', marginTop: '4px' }}>
                                  <strong>{attempt.failure_kind}:</strong> {attempt.failure_detail}
                                </div>
                              )}

                              {attempt.fallback_reason && (
                                <div style={{ fontSize: '0.72rem', color: '#f59e0b', marginTop: '2px' }}>
                                  ↳ Fallback trigger: {attempt.fallback_reason}
                                </div>
                              )}
                            </div>

                            <div style={{ textAlign: 'right', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {attempt.latency_ms?.toFixed(1)} ms
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <JsonViewerModal
        isOpen={Boolean(selectedRecord)}
        title={`Provenance Record: ${selectedRecord?.request_id}`}
        data={selectedRecord}
        onClose={() => setSelectedRecord(null)}
      />
    </div>
  );
};

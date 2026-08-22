import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { EvaluationMetrics } from '../types';

export const EvaluationInsightsView: React.FC = () => {
  const [metrics, setMetrics] = useState<EvaluationMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const data = await api.getEvaluationMetrics();
      setMetrics(data);
      setLoading(false);
    };
    load();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Research Question Banner */}
      <div
        className="glass-panel"
        style={{
          padding: '24px',
          background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(56, 189, 248, 0.1) 100%)',
          border: '1px solid rgba(99, 102, 241, 0.3)',
        }}
      >
        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#38bdf8', textTransform: 'uppercase', marginBottom: '6px' }}>
          Core Research Question
        </div>
        <h2 style={{ fontSize: '1.25rem', color: '#fff', marginBottom: '8px' }}>
          "Can intelligent multi-model routing aggregate free LLM capacity while preserving synthetic persona quality and user experience?"
        </h2>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
          BebshaX aggregates ~24 free providers and local Ollama fallback behind pre-flight token budgeting and deterministic task pools to achieve high reliability with $0 API budget.
        </p>
      </div>

      {loading || !metrics ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading evaluation metrics...</div>
      ) : (
        <>
          {/* Top Quality KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Schema Validity Rate
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#34d399' }}>
                {(metrics.overall_health.schema_validity_rate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Strict Pydantic contract compliance
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Consistency Pass Rate
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#38bdf8' }}>
                {(metrics.overall_health.consistency_pass_rate * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Deterministic rule checks & critic
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Avg Grounding Ratio
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#c084fc' }}>
                {(metrics.overall_health.avg_grounding_ratio * 100).toFixed(1)}%
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Evidence-backed attributes / total
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '20px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '6px' }}>
                Average Latency
              </div>
              <div style={{ fontSize: '1.8rem', fontWeight: 800, color: '#fbbf24' }}>
                {metrics.overall_health.avg_latency_ms.toFixed(0)} ms
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                Across all 16 TaskTypes
              </div>
            </div>
          </div>

          {/* Strategy Benchmark Comparison */}
          <div className="glass-panel" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '1.1rem', color: '#fff' }}>Routing Strategy Offline Benchmark (Phase 11)</h3>
                <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  Evaluates routing policies against RouterArena & xRouteBench replay datasets
                </p>
              </div>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '12px 14px' }}>Strategy</th>
                    <th style={{ padding: '12px 14px' }}>Success Rate</th>
                    <th style={{ padding: '12px 14px' }}>Avg Latency</th>
                    <th style={{ padding: '12px 14px' }}>Failover / Fallback Rate</th>
                    <th style={{ padding: '12px 14px' }}>Cost Efficiency</th>
                    <th style={{ padding: '12px 14px' }}>Recommendation</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.routing_strategies.map((s, idx) => {
                    const isHybrid = s.strategy.includes('HYBRID');
                    const isNaive = s.strategy.includes('ROUND_ROBIN');

                    return (
                      <tr
                        key={idx}
                        style={{
                          borderBottom: '1px solid var(--border-subtle)',
                          background: isHybrid ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '14px', fontWeight: 600, color: isHybrid ? '#38bdf8' : '#fff' }}>
                          {s.strategy}
                          {isHybrid && (
                            <span
                              style={{
                                marginLeft: '8px',
                                fontSize: '0.68rem',
                                background: 'rgba(56,189,248,0.2)',
                                color: '#38bdf8',
                                padding: '2px 6px',
                                borderRadius: '4px',
                              }}
                            >
                              PRODUCTION
                            </span>
                          )}
                        </td>

                        <td style={{ padding: '14px' }}>
                          <span style={{ color: s.success_rate >= 0.95 ? '#34d399' : '#fb7185', fontWeight: 700 }}>
                            {(s.success_rate * 100).toFixed(1)}%
                          </span>
                        </td>

                        <td style={{ padding: '14px', color: '#fff' }}>{s.avg_latency_ms} ms</td>

                        <td style={{ padding: '14px' }}>
                          <span style={{ color: s.fallback_rate <= 0.15 ? '#34d399' : '#f59e0b' }}>
                            {(s.fallback_rate * 100).toFixed(1)}%
                          </span>
                        </td>

                        <td style={{ padding: '14px', color: '#fff' }}>{(s.cost_efficiency * 100).toFixed(0)}%</td>

                        <td style={{ padding: '14px', fontSize: '0.75rem' }}>
                          {isHybrid ? (
                            <span style={{ color: '#34d399', fontWeight: 600 }}>✓ Optimal balance (Capability + Quota + Local)</span>
                          ) : isNaive ? (
                            <span style={{ color: '#fb7185' }}>✕ Severe rate-limit cascades</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>Specialized use only</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

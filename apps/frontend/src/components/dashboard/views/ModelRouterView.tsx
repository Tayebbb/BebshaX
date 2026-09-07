import React, { useState, useEffect, useCallback } from 'react';
import {
  Activity,
  Shield,
  Layers,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { RoutesStatusResponse, ProvenanceRecord, EvaluationMetrics } from '../../../types';
import { api } from '../../../services/api';
import { ProvenanceTraceRow } from './router/ProvenanceTraceRow';
import { EvaluationCard } from './router/EvaluationCard';
import { JudgeLabPanel } from './router/JudgeLabPanel';
import { fmtCount } from './router/routerFormat';

/** Developer-facing routing & provenance dashboard (RULES R11: internals live
 * here only, clearly labelled). Every number is measured or rendered as "—". */
export const ModelRouterView: React.FC = () => {
  const [routesStatus, setRoutesStatus] = useState<RoutesStatusResponse | null>(null);
  const [provenance, setProvenance] = useState<ProvenanceRecord[]>([]);
  // Distinct "never loaded" state so the empty-traces copy cannot flash before
  // the first response arrives.
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationMetrics | null>(null);
  const [evaluationLoading, setEvaluationLoading] = useState(true);
  const [evaluationError, setEvaluationError] = useState<string | null>(null);

  const loadEvaluation = useCallback(async () => {
    setEvaluationLoading(true);
    setEvaluationError(null);
    try {
      setEvaluation(await api.getEvaluationMetrics());
    } catch (err: any) {
      setEvaluation(null);
      setEvaluationError(err?.message || 'metrics endpoint did not respond');
    } finally {
      setEvaluationLoading(false);
    }
  }, []);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [routes, prov] = await Promise.all([
        api.getRoutesStatus(),
        api.getProvenance(15),
      ]);
      setRoutesStatus(routes);
      setProvenance(prov.items);
    } catch (err: any) {
      // The service throws — swallowing this rendered an empty matrix that
      // looked like "no providers" instead of "we couldn't check".
      setLoadError(err?.message || 'Provider status could not be loaded.');
      setRoutesStatus(null);
      setProvenance([]);
    } finally {
      setIsLoading(false);
      setHasLoaded(true);
    }
    // Evaluation is independent: its failure must not blank the health matrix.
    void loadEvaluation();
  }, [loadEvaluation]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

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
            Routing &amp; Provenance
          </h1>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', margin: 0 }}>
            Which AI providers are online, how each request was routed, and what the evaluation log measures.
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

      {/* How routing works — static architecture, deliberately labelled as such */}
      <section aria-labelledby="bx-router-arch" style={{ marginBottom: '36px' }}>
        <div
          id="bx-router-arch"
          style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: '10px' }}
        >
          How routing works — architecture, not live status
        </div>
        <dl
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))',
            gap: '10px 32px',
            margin: 0,
            fontSize: '0.86rem',
            lineHeight: 1.55,
          }}
        >
          <div>
            <dt style={{ color: 'var(--text-muted)' }}>Operational budget</dt>
            <dd style={{ margin: 0, color: 'var(--text-main)', fontWeight: 600 }}>Zero API cost: free-tier aggregation across providers</dd>
          </div>
          <div>
            <dt style={{ color: 'var(--text-muted)' }}>Reliability fallback</dt>
            <dd style={{ margin: 0, color: 'var(--text-main)', fontWeight: 600 }}>Local Ollama model at the end of every pool</dd>
          </div>
          <div>
            <dt style={{ color: 'var(--text-muted)' }}>Task Pool Design</dt>
            <dd style={{ margin: 0, color: 'var(--text-main)' }}>
              <span style={{ fontWeight: 600 }}>Reasoning</span> generates and checks personas · <span style={{ fontWeight: 600 }}>Conversation</span> runs interviews ·{' '}
              <span style={{ fontWeight: 600 }}>Emergency</span> is local-first
            </dd>
          </div>
          {routesStatus?.providers && (
            <div>
              <dt style={{ color: 'var(--text-muted)' }}>Providers reporting now</dt>
              <dd style={{ margin: 0, color: 'var(--text-main)', fontWeight: 600 }}>{routesStatus.providers.length}</dd>
            </div>
          )}
        </dl>
      </section>

      {/* Provenance Record Traces (Rule R3) — the request story comes first */}
      <section className="bx-section" style={{ marginTop: 0, marginBottom: '36px' }}>
        <div className="bx-section__head" style={{ flexWrap: 'wrap' }}>
          <h2 className="bx-section__title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Shield size={18} color="var(--accent-teal)" aria-hidden="true" />
            Recent Provenance Traces (Rule R3)
          </h2>
          <span className="bx-section__hint">Every LLM request produces 14-field provenance. Expand a row for its attempt chain.</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {!hasLoaded || isLoading ? (
            <div role="status" style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.86rem' }}>
              Loading provenance traces…
            </div>
          ) : provenance.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '0.86rem', border: '1px dashed var(--border-medium)', borderRadius: '12px' }}>
              {loadError
                ? 'Provenance traces could not be loaded.'
                : 'No recent provenance traces found. Run a research study or persona generation to generate traces.'}
            </div>
          ) : (
            provenance.map((rec) => <ProvenanceTraceRow key={rec.request_id} rec={rec} />)
          )}
        </div>
      </section>

      {/* Live Provider Health Matrix */}
      <section className="bx-section" style={{ marginTop: 0, marginBottom: '36px' }}>
        <div className="bx-section__head">
          <h2 className="bx-section__title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Activity size={18} color="var(--accent-teal)" aria-hidden="true" />
            Live Provider Health Matrix
          </h2>
        </div>

        {loadError && (
          <div
            role="alert"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              background: 'var(--status-error-bg)',
              border: '1px solid var(--status-error-border)',
              borderRadius: '10px',
              padding: '12px 16px',
              marginBottom: '16px',
              color: 'var(--status-error-text)',
              fontSize: '0.85rem',
            }}
          >
            <span>Provider status unavailable: {loadError}</span>
            <button
              type="button"
              onClick={loadData}
              disabled={isLoading}
              style={{
                background: 'transparent',
                border: '1px solid currentColor',
                borderRadius: '6px',
                padding: '4px 12px',
                color: 'inherit',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                fontWeight: 600,
                fontSize: '0.82rem',
                whiteSpace: 'nowrap',
              }}
            >
              Retry
            </button>
          </div>
        )}

        {!loadError && hasLoaded && !isLoading && (routesStatus?.providers?.length ?? 0) === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.86rem', padding: '12px 0' }}>
            No providers reported yet.
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(190px, 100%), 1fr))', gap: '14px' }}>
          {routesStatus?.providers.map((p) => {
            const isHealthy = p.status === 'healthy';
            return (
              <div
                key={p.name}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '12px',
                  padding: '16px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  boxShadow: 'inset 0 1px 0 var(--reflect)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize', fontSize: '0.92rem' }}>
                    {p.name}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span
                      aria-hidden="true"
                      style={{
                        width: '7px',
                        height: '7px',
                        borderRadius: '50%',
                        background: isHealthy ? 'var(--accent-emerald)' : 'var(--accent-amber)',
                      }}
                    />
                    <span style={{ fontSize: '0.72rem', color: isHealthy ? 'var(--status-success-text)' : 'var(--status-warn-text)', textTransform: 'capitalize' }}>
                      {p.status}
                    </span>
                  </div>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Type: <span style={{ color: 'var(--text-primary)' }}>{p.type.replace(/_/g, ' ')}</span>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Models: <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.available_models} active</span>
                </div>
                <div style={{ fontSize: '0.72rem', color: p.active_cooldowns ? 'var(--status-warn-text)' : 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {p.active_cooldowns ? <AlertTriangle size={12} aria-hidden="true" /> : null}
                  Cooling down: {fmtCount(p.active_cooldowns)}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Task Pools Concurrency Status */}
      {routesStatus?.pools && routesStatus.pools.length > 0 && (
        <section className="bx-section" style={{ marginTop: 0, marginBottom: '36px' }}>
          <div className="bx-section__head">
            <h2 className="bx-section__title" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Layers size={18} color="var(--accent-teal)" aria-hidden="true" />
              Pool Concurrency & Candidate Allocation
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '12px' }}>
            {routesStatus.pools.map((pool) => (
              <div
                key={pool.name}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '10px',
                  padding: '14px',
                  boxShadow: 'inset 0 1px 0 var(--reflect)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize', fontSize: '0.88rem' }}>
                    {pool.name}
                  </span>
                  <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                    {pool.candidates_count} candidates
                  </span>
                </div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  Max Concurrency: <strong style={{ color: 'var(--text-primary)' }}>{pool.max_concurrency}</strong>
                </div>
                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                  Active Requests:{' '}
                  <strong style={{ color: pool.active_requests ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>{fmtCount(pool.active_requests)}</strong>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Measured evaluation numbers */}
      <EvaluationCard metrics={evaluation} loading={evaluationLoading} error={evaluationError} />

      {/* Judge Lab — only when the backend exposes it */}
      <JudgeLabPanel />
    </div>
  );
};

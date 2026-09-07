import React from 'react';
import { BarChart3 } from 'lucide-react';
import type { EvaluationMetrics } from '../../../../types';
import { DASH, fmtMs, fmtPct } from './routerFormat';

const NOT_MEASURED = 'not yet measured';

/** `null` from the backend means "not measured" — say so instead of showing 0. */
const measured = (v: number | null | undefined, fmt: (n: number) => string): React.ReactNode =>
  typeof v === 'number' && Number.isFinite(v) ? (
    fmt(v)
  ) : (
    <span style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontWeight: 400 }}>{NOT_MEASURED}</span>
  );

const cell: React.CSSProperties = { padding: '8px 10px', borderBottom: '1px solid var(--fill-soft)', whiteSpace: 'nowrap' };
const head: React.CSSProperties = {
  ...cell,
  fontSize: '0.72rem',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color: 'var(--text-muted)',
  fontWeight: 600,
  textAlign: 'left',
};

interface EvaluationCardProps {
  metrics: EvaluationMetrics | null;
  loading: boolean;
  error: string | null;
}

/**
 * Measured evaluation numbers from /api/evaluation/metrics. Every figure is
 * labelled with its data source; nulls read "not yet measured".
 */
export const EvaluationCard: React.FC<EvaluationCardProps> = ({ metrics, loading, error }) => {
  const totalRequests = (metrics?.pools || []).reduce((sum, p) => sum + (p.requests || 0), 0);
  const gate = metrics?.quality_gate;

  return (
    <section
      aria-labelledby="evaluation-card-title"
      style={{
        background: 'var(--fill-soft)',
        border: '1px solid var(--fill-soft-2)',
        borderRadius: '16px',
        padding: '24px',
        marginBottom: '32px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '10px', marginBottom: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <BarChart3 size={18} color="var(--accent-cyan)" aria-hidden="true" />
          <h2 id="evaluation-card-title" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
            Evaluation
          </h2>
        </div>
        {metrics && (
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Computed from {totalRequests.toLocaleString()} logged request{totalRequests === 1 ? '' : 's'} ·{' '}
            {metrics.overall_health.total_personas_generated.toLocaleString()} personas
          </span>
        )}
      </div>
      <p style={{ margin: '0 0 16px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        Measured over the provenance log and stored persona validations — nothing here is a target or an estimate.
      </p>

      {loading && (
        <div role="status" style={{ color: 'var(--text-muted)', fontSize: '0.86rem' }}>
          Loading evaluation metrics…
        </div>
      )}

      {!loading && error && (
        <div role="alert" style={{ color: 'var(--status-error-text)', fontSize: '0.86rem' }}>
          Evaluation metrics unavailable: {error}
        </div>
      )}

      {!loading && !error && metrics && (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))',
              gap: '12px',
              marginBottom: '18px',
            }}
          >
            {[
              { label: 'Avg grounding', value: measured(metrics.overall_health.avg_grounding_ratio, (n) => fmtPct(n)), hint: 'OBSERVED attributes / all attributes' },
              { label: 'Consistency pass', value: measured(metrics.overall_health.consistency_pass_rate, (n) => fmtPct(n)), hint: 'validated personas with 0 warnings' },
              { label: 'Schema validity', value: measured(metrics.overall_health.schema_validity_rate, (n) => fmtPct(n)), hint: 'generation requests without MALFORMED_RESPONSE' },
              { label: 'Avg latency', value: measured(metrics.overall_health.avg_latency_ms, (n) => fmtMs(n)), hint: 'all logged requests' },
            ].map((m) => (
              <div key={m.label} style={{ background: 'var(--fill-soft)', border: '1px solid var(--fill-soft-2)', borderRadius: '10px', padding: '12px 14px' }}>
                <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>{m.label}</div>
                <div style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--text-main)', marginTop: '4px' }}>{m.value}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>{m.hint}</div>
              </div>
            ))}
          </div>

          <div style={{ overflowX: 'auto' }}>
            {metrics.pools.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                No pool has served a request yet — per-pool rates appear after the first logged request.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                <caption style={{ captionSide: 'top', textAlign: 'left', fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', paddingBottom: '6px' }}>
                  Per-pool measured performance
                </caption>
                <thead>
                  <tr>
                    <th scope="col" style={head}>Pool</th>
                    <th scope="col" style={head}>Requests</th>
                    <th scope="col" style={head}>Success rate</th>
                    <th scope="col" style={head}>Fallback rate</th>
                    <th scope="col" style={head}>Local-serve share</th>
                    <th scope="col" style={head}>Avg latency</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.pools.map((p) => (
                    <tr key={p.pool}>
                      <td style={{ ...cell, fontWeight: 600, color: 'var(--text-main)', textTransform: 'capitalize' }}>{p.pool}</td>
                      <td style={cell}>{p.requests.toLocaleString()}</td>
                      <td style={cell}>{fmtPct(p.success_rate)}</td>
                      <td style={cell}>{fmtPct(p.fallback_rate)}</td>
                      <td style={cell}>{fmtPct(p.local_serve_rate)}</td>
                      <td style={cell}>{measured(p.avg_latency_ms, (n) => fmtMs(n))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={{ marginTop: '16px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)', marginRight: '8px' }}>
              Quality gate
            </span>
            {gate ? (
              <span>
                Local vs cloud interview judge — bar {gate.bar ?? DASH}
                {gate.arms.length > 0 && (
                  <>
                    {' · '}
                    {gate.arms
                      .map((a) => `${a.tag || a.model || 'arm'}: ${a.weighted_score != null ? a.weighted_score.toFixed(2) : DASH}`)
                      .join(' / ')}
                  </>
                )}
                {gate.judge_route && <span style={{ color: 'var(--text-muted)' }}> · judged by {gate.judge_route}</span>}
                <span style={{ color: 'var(--text-muted)' }}> · source {gate.source_file}</span>
              </span>
            ) : (
              <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>{NOT_MEASURED} — no judged gate report on disk</span>
            )}
          </div>
        </>
      )}
    </section>
  );
};

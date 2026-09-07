import React, { useEffect, useState } from 'react';
import { AlertTriangle, FlaskConical, Loader2, Play } from 'lucide-react';
import type { DemoLabRunResult, DemoLabScenario } from '../../../../types';
import { api } from '../../../../services/api';
import { fromUnknownError, toUserMessage } from '../../../../utils/apiError';
import { RequestIdTag } from '../../../common/RequestIdTag';
import { FailureKindChip } from './ProvenanceTraceRow';
import { DASH, fmtMs } from './routerFormat';

const OUTCOME_LABEL: Record<string, string> = {
  served: 'Served',
  served_after_fallback: 'Served after fallback',
  explicit_failure: 'Explicit failure — nothing fabricated',
  claims_downgraded: 'Claims downgraded',
  low_grounding: 'Low grounding flagged',
};

const outcomeTone = (outcome: string): { fg: string; bg: string } => {
  switch (outcome) {
    case 'served':
      return { fg: 'var(--accent-emerald)', bg: 'rgba(16, 185, 129, 0.12)' };
    case 'served_after_fallback':
      return { fg: 'var(--accent-cyan)', bg: 'rgba(34, 211, 238, 0.12)' };
    case 'explicit_failure':
      return { fg: '#EF4444', bg: 'rgba(239, 68, 68, 0.12)' };
    default:
      return { fg: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' };
  }
};

const isTextBlock = (key: string, value: unknown): value is string =>
  typeof value === 'string' && (value.includes('\n') || value.length > 120 || /prompt|excerpt|wrapped/i.test(key));

const renderExtraValue = (key: string, value: unknown): React.ReactNode => {
  if (isTextBlock(key, value)) {
    return (
      <pre
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontSize: '0.74rem',
          lineHeight: 1.45,
          background: 'var(--bg-pure)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          padding: '10px 12px',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-mono, monospace)',
          maxHeight: '260px',
          overflow: 'auto',
        }}
      >
        {value}
      </pre>
    );
  }
  if (value === null || value === undefined) return <span style={{ color: 'var(--text-muted)' }}>{DASH}</span>;
  if (typeof value === 'object') {
    return (
      <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '0.74rem', fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-primary)' }}>
        {JSON.stringify(value, null, 2)}
      </pre>
    );
  }
  return <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>{String(value)}</span>;
};

const RunResult: React.FC<{ result: DemoLabRunResult }> = ({ result }) => {
  const tone = outcomeTone(result.outcome);
  const extraEntries = Object.entries(result.extra || {});
  return (
    <div
      role="region"
      aria-label={`Result for ${result.title}`}
      style={{
        marginTop: '16px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '12px',
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: '0.74rem',
            fontWeight: 700,
            letterSpacing: '0.04em',
            color: tone.fg,
            background: tone.bg,
            padding: '3px 10px',
            borderRadius: '999px',
          }}
        >
          {OUTCOME_LABEL[result.outcome] || result.outcome}
        </span>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          error_code:{' '}
          <span style={{ fontFamily: 'var(--font-mono, monospace)', color: result.error_code ? 'var(--status-error-text)' : 'var(--text-secondary)' }}>
            {result.error_code ?? 'null'}
          </span>
        </span>
        {result.provenance?.request_id && <RequestIdTag requestId={result.provenance.request_id} />}
      </div>

      <p style={{ margin: 0, fontSize: '0.86rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>{result.explanation}</p>

      <div>
        <h4 style={{ margin: '0 0 8px', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>
          Timeline
        </h4>
        <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {result.timeline.map((step, i) => (
            <li
              key={`${step.step}-${i}`}
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(120px, auto) 1fr',
                gap: '10px',
                alignItems: 'baseline',
                fontSize: '0.8rem',
              }}
            >
              <span style={{ fontWeight: 700, letterSpacing: '0.05em', fontSize: '0.72rem', color: step.result === 'failed' ? 'var(--status-error-text)' : step.result === 'skipped' ? '#F59E0B' : 'var(--accent-emerald)' }}>
                {step.step}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', color: 'var(--text-secondary)' }}>
                {step.provider && (
                  <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-main)' }}>
                    {step.provider}
                    {step.model ? `/${step.model}` : ''}
                  </span>
                )}
                {step.failure_kind && <FailureKindChip kind={step.failure_kind} />}
                {step.fallback_reason && <span>{step.fallback_reason}</span>}
                {step.latency_ms != null && <span style={{ color: 'var(--text-muted)' }}>{fmtMs(step.latency_ms)}</span>}
                {!step.provider && !step.failure_kind && !step.fallback_reason && step.latency_ms == null && (
                  <span style={{ color: 'var(--text-muted)' }}>{step.result}</span>
                )}
              </span>
            </li>
          ))}
        </ol>
      </div>

      {extraEntries.length > 0 && (
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)' }}>
            Scenario details
          </h4>
          <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'minmax(140px, auto) 1fr', columnGap: '12px', rowGap: '8px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {extraEntries.map(([k, v]) => (
              <React.Fragment key={k}>
                <dt style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)' }}>{k}</dt>
                <dd style={{ margin: 0, minWidth: 0 }}>{renderExtraValue(k, v)}</dd>
              </React.Fragment>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
};

/**
 * Judge Lab: one button per scripted failure scenario. Renders only when the
 * backend exposes /api/demo-lab/scenarios (404 → nothing at all).
 */
export const JudgeLabPanel: React.FC = () => {
  const [scenarios, setScenarios] = useState<DemoLabScenario[] | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<DemoLabRunResult | null>(null);
  const [runError, setRunError] = useState<{ message: string; requestId: string | null } | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getDemoLabScenarios()
      .then((res) => {
        if (!alive) return;
        setScenarios(res && res.enabled ? res.scenarios : null);
      })
      .catch(() => {
        // Lab unavailable for any reason — the panel simply stays hidden.
        if (alive) setScenarios(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (!scenarios || scenarios.length === 0) return null;

  const run = async (name: string) => {
    if (running) return;
    setRunning(name);
    setRunError(null);
    setResult(null);
    try {
      const res = await api.runDemoLabScenario(name);
      setResult(res);
    } catch (err) {
      setRunError({ message: toUserMessage(err, { timeoutMs: 30000 }), requestId: fromUnknownError(err).requestId ?? null });
    } finally {
      setRunning(null);
    }
  };

  return (
    <section
      aria-labelledby="judge-lab-title"
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
          <FlaskConical size={18} color="var(--accent-cyan)" aria-hidden="true" />
          <h2 id="judge-lab-title" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0 }}>
            Judge Lab
          </h2>
        </div>
        <span
          style={{
            fontSize: '0.72rem',
            fontWeight: 700,
            letterSpacing: '0.06em',
            color: '#F59E0B',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.4)',
            padding: '3px 10px',
            borderRadius: '999px',
          }}
        >
          SIMULATED — scripted adapters, real routing code
        </span>
      </div>
      <p style={{ margin: '0 0 16px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
        Each scenario replaces the providers with scripted responses and runs the production router,
        failure taxonomy and provenance path against them. No real provider is called.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(240px, 100%), 1fr))', gap: '10px' }}>
        {scenarios.map((s) => {
          const isRunning = running === s.name;
          return (
            <button
              key={s.name}
              type="button"
              onClick={() => run(s.name)}
              disabled={!!running}
              aria-busy={isRunning}
              title={s.description}
              style={{
                textAlign: 'left',
                background: 'var(--bg-card)',
                border: result?.scenario === s.name ? '1px solid var(--accent-teal)' : '1px solid var(--border-subtle)',
                borderRadius: '12px',
                padding: '12px 14px',
                color: 'var(--text-main)',
                cursor: running ? 'not-allowed' : 'pointer',
                opacity: running && !isRunning ? 0.6 : 1,
                display: 'flex',
                flexDirection: 'column',
                gap: '6px',
                font: 'inherit',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, fontSize: '0.86rem' }}>
                {isRunning ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
                {s.title}
              </span>
              <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>{s.description}</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Expected: <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>{s.expected_outcome}</span>
              </span>
            </button>
          );
        })}
      </div>

      {runError && (
        <div
          role="alert"
          style={{
            marginTop: '14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: '10px',
            padding: '12px 16px',
            color: 'var(--status-error-text)',
            fontSize: '0.84rem',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={14} aria-hidden="true" />
            Scenario could not run: {runError.message}
          </span>
          <RequestIdTag requestId={runError.requestId} />
        </div>
      )}

      {result && <RunResult result={result} />}
    </section>
  );
};

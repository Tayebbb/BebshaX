import React, { useState } from 'react';
import { ShieldCheck, RefreshCw, AlertTriangle } from 'lucide-react';
import { api } from '../../../../services/api';
import type { AiReviewVerdict } from '../../../../services/api';
import { fromUnknownError, toUserMessage } from '../../../../utils/apiError';
import { RequestIdTag } from '../../../common/RequestIdTag';
import { READ_ONLY_TITLE } from './types';

/** Independent AI review of everything the study produced. The verdict is
 * written by a separate model pass (CRITIC) against a fixed rubric and names
 * the route that served it — it is never cached, templated or pre-computed, so
 * two runs may legitimately differ. Failures are shown as such. */
interface AiReviewCardProps {
  studyId?: string;
  isReadOnly?: boolean;
}

const severityColor: Record<string, string> = {
  high: 'var(--status-error-text, #ef4444)',
  medium: 'var(--status-warning-text, #f59e0b)',
  low: 'var(--text-secondary)',
};

export const AiReviewCard: React.FC<AiReviewCardProps> = ({ studyId, isReadOnly = false }) => {
  const [verdict, setVerdict] = useState<AiReviewVerdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const run = async () => {
    if (!studyId || isRunning) return;
    setIsRunning(true);
    setError(null);
    setErrorCode(null);
    try {
      setVerdict(await api.requestStudyAiReview(studyId));
    } catch (err) {
      const parsed = fromUnknownError(err);
      setError(toUserMessage(err, { timeoutMs: 300000 }));
      setErrorCode(parsed.errorCode ?? null);
      setRequestId(parsed.requestId ?? null);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <section
      data-testid="ai-review-card"
      aria-labelledby="ai-review-title"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '12px',
        padding: '18px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <ShieldCheck size={18} style={{ color: 'var(--accent-cyan)' }} aria-hidden="true" />
          <div>
            <h3 id="ai-review-title" style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>
              Independent AI review
            </h3>
            <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              A separate model audits this study’s personas, evidence, interviews and report against a fixed
              rubric (grounding, specificity, consistency, honesty, actionability).
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={run}
          disabled={isRunning || isReadOnly || !studyId}
          title={isReadOnly ? READ_ONLY_TITLE : undefined}
          data-testid="ai-review-run"
          style={{
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
            color: 'var(--accent-cyan)',
            borderRadius: '8px',
            padding: '8px 14px',
            fontSize: '0.82rem',
            fontWeight: 600,
            cursor: isRunning || isReadOnly ? 'not-allowed' : 'pointer',
            opacity: isRunning || isReadOnly ? 0.6 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <RefreshCw size={14} className={isRunning ? 'animate-spin' : ''} aria-hidden="true" />
          {isRunning ? 'Reviewing…' : verdict ? 'Review again' : 'Run AI review'}
        </button>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: 'var(--status-error-text)',
            borderRadius: '8px',
            padding: '10px 14px',
            fontSize: '0.84rem',
          }}
        >
          <AlertTriangle size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} aria-hidden="true" />
          AI review did not complete: {error} — no verdict was invented.
          {errorCode && <code style={{ marginLeft: 8, fontSize: '0.75rem' }}>{errorCode}</code>}
          {requestId && (
            <div style={{ marginTop: 6 }}>
              <RequestIdTag requestId={requestId} />
            </div>
          )}
        </div>
      )}

      {verdict && (
        <div data-testid="ai-review-verdict" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '14px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-main)', fontVariantNumeric: 'tabular-nums' }}>
              {verdict.overall_score}
              <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', fontWeight: 500 }}>/100</span>
            </span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              Reviewed by {verdict.served_by ?? 'the routing layer'} ·{' '}
              {Object.entries(verdict.reviewed_artifacts)
                .filter(([, n]) => n > 0)
                .map(([k, n]) => `${n} ${k.replace(/_/g, ' ')}`)
                .join(', ') || 'no artefacts'}
              {verdict.attempts > 1 ? ` · ${verdict.attempts} attempts` : ''}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '8px' }}>
            {Object.entries(verdict.dimension_scores).map(([dim, score]) => (
              <div
                key={dim}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '8px',
                  padding: '8px 10px',
                }}
              >
                <span style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-secondary)' }}>
                  {dim}
                </span>
                <span style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-main)', fontVariantNumeric: 'tabular-nums' }}>
                  {score}
                </span>
              </div>
            ))}
          </div>

          <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--text-main)', lineHeight: 1.55 }}>{verdict.verdict}</p>

          {verdict.strengths.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
              {verdict.strengths.map((s, i) => (
                <li key={`s-${i}`}>{s}</li>
              ))}
            </ul>
          )}

          {verdict.issues.length > 0 && (
            <ul data-testid="ai-review-issues" style={{ margin: 0, paddingLeft: '18px', fontSize: '0.84rem' }}>
              {verdict.issues.map((issue, i) => (
                <li key={`i-${i}`} style={{ color: severityColor[issue.severity] ?? 'var(--text-secondary)' }}>
                  <strong style={{ textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '0.05em' }}>{issue.severity}</strong>{' '}
                  {issue.artifact && <code style={{ fontSize: '0.75rem' }}>{issue.artifact}</code>} {issue.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
};

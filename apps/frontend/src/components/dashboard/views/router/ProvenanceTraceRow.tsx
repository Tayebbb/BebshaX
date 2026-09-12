import React, { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle2, Clock, XCircle } from 'lucide-react';
import type { AttemptRecord, ProvenanceRecord } from '../../../../types';
import { DASH, failureKindTone, fmtCount, fmtMs, parseRoutingPath } from './routerFormat';

/** Small pill for a failure kind (or "served" when the attempt succeeded). */
export const FailureKindChip: React.FC<{ kind: string | null | undefined; success?: boolean }> = ({
  kind,
  success,
}) => {
  const label = success ? 'served' : kind || 'unknown';
  const tone = success ? failureKindTone(null) : failureKindTone(kind || 'UNKNOWN');
  return (
    <span
      style={{
        fontSize: '0.75rem',
        fontWeight: 700,
        letterSpacing: 0,
        color: tone.fg,
        background: tone.bg,
        padding: '1px 7px',
        borderRadius: '4px',
        fontFamily: 'var(--font-mono, monospace)',
        minWidth: 0,
        maxWidth: '100%',
        boxSizing: 'border-box',
        overflowWrap: 'anywhere',
      }}
    >
      {label}
    </span>
  );
};

const AttemptStep: React.FC<{ attempt: AttemptRecord; isLast: boolean }> = ({ attempt, isLast }) => {
  const cached = attempt.notes?.some((n) => /cache/i.test(n));
  return (
    <li
      style={{
        display: 'grid',
        gridTemplateColumns: '28px minmax(0, 1fr)',
        minWidth: 0,
        gap: '10px',
        position: 'relative',
        paddingBottom: isLast ? 0 : '12px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <span
          aria-hidden="true"
          style={{
            width: '22px',
            height: '22px',
            borderRadius: '4px',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '0.75rem',
            fontWeight: 700,
            color: attempt.success ? 'var(--accent-emerald)' : 'var(--status-error-text)',
            background: attempt.success ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.1)',
          }}
        >
          {attempt.attempt_number}
        </span>
        {!isLast && <span aria-hidden="true" style={{ flex: 1, width: '1px', background: 'var(--border-subtle)', marginTop: '4px' }} />}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem', minWidth: 0, overflowWrap: 'anywhere' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--text-main)', fontWeight: 600, minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
            {attempt.provider}/{attempt.model}
          </span>
          <FailureKindChip kind={attempt.failure_kind} success={attempt.success} />
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: 'var(--text-muted)', flexShrink: 0, whiteSpace: 'nowrap' }}>
            <Clock size={11} aria-hidden="true" style={{ flexShrink: 0 }} />
            {fmtMs(attempt.latency_ms)}
          </span>
          {cached && (
            <span
              title="The provider layer answered from its response cache — no new model call was made"
              style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', background: 'var(--fill-soft-2)', padding: '1px 6px', borderRadius: '4px', letterSpacing: 0 }}
            >
              CACHED
            </span>
          )}
        </div>
        {attempt.fallback_reason && (
          <div style={{ color: 'var(--text-secondary)', minWidth: 0, overflowWrap: 'anywhere' }}>
            <span style={{ color: 'var(--text-muted)' }}>Fallback: </span>
            {attempt.fallback_reason}
          </div>
        )}
        {attempt.failure_detail && (
          <div style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)', fontSize: '0.75rem', minWidth: 0, overflowWrap: 'anywhere' }}>
            {attempt.failure_detail}
          </div>
        )}
      </div>
    </li>
  );
};

/**
 * One provenance trace: a summary row that expands (aria-expanded) into the
 * attempt timeline, the routing path with skipped markers, token counts and
 * the pool. Every null is rendered as "—" — nothing is estimated.
 */
export const ProvenanceTraceRow: React.FC<{ rec: ProvenanceRecord }> = ({ rec }) => {
  const [open, setOpen] = useState(false);
  const path = parseRoutingPath(rec.routing_path);
  const candidates = path.filter((p) => p.kind !== 'annotation');
  const annotations = path.filter((p) => p.kind === 'annotation');
  const anyCached = rec.attempts?.some((a) => a.notes?.some((n) => /cache/i.test(n)));
  const panelId = `trace-${rec.request_id}`;

  return (
    <div
      style={{
        background: 'rgba(255, 255, 255, 0.015)',
        border: '1px solid var(--fill-soft)',
        borderRadius: '8px',
        fontSize: '0.84rem',
        minWidth: 0,
        maxWidth: '100%',
        boxSizing: 'border-box',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        style={{
          width: '100%',
          minWidth: 0,
          boxSizing: 'border-box',
          background: 'transparent',
          border: 'none',
          color: 'inherit',
          textAlign: 'left',
          padding: '14px 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
          cursor: 'pointer',
          font: 'inherit',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
          {open ? <ChevronDown size={14} aria-hidden="true" style={{ flexShrink: 0 }} /> : <ChevronRight size={14} aria-hidden="true" style={{ flexShrink: 0 }} />}
          <span
            style={{
              fontFamily: 'var(--font-mono, monospace)',
              color: 'var(--status-warn-text)',
              background: 'rgba(246, 200, 120, 0.1)',
              padding: '2px 6px',
              borderRadius: '6px',
              fontSize: '0.78rem',
            }}
          >
            {rec.request_id.slice(0, 10)}
          </span>
          <span style={{ color: 'var(--text-main)', fontWeight: 600, minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>{rec.task}</span>
          {rec.pool && (
            <span
              style={{
                fontSize: '0.75rem',
                color: 'var(--text-muted)',
                background: 'var(--fill-soft)',
                padding: '2px 6px',
                borderRadius: '4px',
                textTransform: 'uppercase',
                minWidth: 0,
                maxWidth: '100%',
                boxSizing: 'border-box',
                overflowWrap: 'anywhere',
              }}
            >
              {rec.pool}
            </span>
          )}
          {rec.attempts && rec.attempts.length > 1 && (
            <span style={{ fontSize: '0.75rem', color: '#F59E0B', fontWeight: 600, flexShrink: 0, whiteSpace: 'nowrap' }}>
              {rec.attempts.length} attempts
            </span>
          )}
        </span>

        <span style={{ display: 'flex', alignItems: 'center', gap: '16px', color: 'var(--text-muted)', flexWrap: 'wrap', minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
          <span style={{ color: 'var(--text-primary)', minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
            Served: <strong style={{ color: 'var(--text-main)' }}>{rec.served_by_provider || 'not served'}</strong>
            {rec.served_by_model && ` (${rec.served_by_model})`}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0, whiteSpace: 'nowrap' }}>
            <Clock size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
            {fmtMs(rec.total_latency_ms)}
          </span>
          <span
            style={{
              color: rec.success ? 'var(--accent-emerald)' : '#EF4444',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            {rec.success ? <CheckCircle2 size={14} aria-hidden="true" style={{ flexShrink: 0 }} /> : <XCircle size={14} aria-hidden="true" style={{ flexShrink: 0 }} />}
            {rec.success ? 'Success' : 'Failed'}
          </span>
        </span>
      </button>

      {open && (
        <div
          id={panelId}
          style={{
            borderTop: '1px solid var(--fill-soft)',
            padding: '16px 18px 18px 44px',
            minWidth: 0,
            maxWidth: '100%',
            boxSizing: 'border-box',
            overflowWrap: 'anywhere',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(280px, 100%), 1fr))',
            gap: '20px',
          }}
        >
          <section style={{ minWidth: 0 }}>
            <h4 style={{ margin: '0 0 10px', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: 0, color: 'var(--text-muted)' }}>
              Attempts timeline
            </h4>
            {rec.attempts && rec.attempts.length > 0 ? (
              <ol style={{ listStyle: 'none', margin: 0, padding: 0, minWidth: 0 }}>
                {rec.attempts.map((a, i) => (
                  <AttemptStep key={`${a.attempt_number}-${a.provider}-${a.model}`} attempt={a} isLast={i === rec.attempts.length - 1} />
                ))}
              </ol>
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                No provider was attempted — the request was rejected before routing (see the routing path).
              </div>
            )}
          </section>

          <section style={{ display: 'flex', flexDirection: 'column', gap: '14px', minWidth: 0 }}>
            <div>
              <h4 style={{ margin: '0 0 8px', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: 0, color: 'var(--text-muted)' }}>
                Routing path
              </h4>
              {candidates.length === 0 && annotations.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{DASH}</div>
              ) : (
                <ul style={{ margin: 0, paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.78rem' }}>
                  {candidates.map((p, i) => (
                    <li key={`${p.raw}-${i}`} style={{ color: p.kind === 'skipped' ? 'var(--text-muted)' : 'var(--text-primary)', minWidth: 0, overflowWrap: 'anywhere' }}>
                      <span style={{ fontFamily: 'var(--font-mono, monospace)' }}>{p.route}</span>
                      {p.kind === 'skipped' && (
                        <span style={{ marginLeft: '6px', fontSize: '0.75rem', fontWeight: 600, color: '#F59E0B' }}>
                          skipped — {p.reason}
                        </span>
                      )}
                    </li>
                  ))}
                  {annotations.map((p, i) => (
                    <li key={`ann-${i}`} style={{ color: 'var(--text-muted)', fontStyle: 'italic', listStyle: 'circle', minWidth: 0, overflowWrap: 'anywhere' }}>
                      {p.reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <dl
              style={{
                margin: 0,
                display: 'grid',
                gridTemplateColumns: 'auto minmax(0, 1fr)',
                minWidth: 0,
                columnGap: '12px',
                rowGap: '4px',
                fontSize: '0.78rem',
                color: 'var(--text-secondary)',
              }}
            >
              <dt style={{ color: 'var(--text-muted)' }}>Pool</dt>
              <dd style={{ margin: 0, minWidth: 0 }}>{rec.pool || DASH}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Input tokens</dt>
              <dd style={{ margin: 0, minWidth: 0, fontFamily: 'var(--font-mono, monospace)' }}>{fmtCount(rec.input_tokens)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Output tokens</dt>
              <dd style={{ margin: 0, minWidth: 0, fontFamily: 'var(--font-mono, monospace)' }}>{fmtCount(rec.output_tokens)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Cached</dt>
              <dd style={{ margin: 0, minWidth: 0 }}>{anyCached ? 'yes — served from the provider response cache' : 'no'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Request ID</dt>
              <dd style={{ margin: 0, minWidth: 0, fontFamily: 'var(--font-mono, monospace)', overflowWrap: 'anywhere' }}>{rec.request_id}</dd>
            </dl>
          </section>
        </div>
      )}
    </div>
  );
};

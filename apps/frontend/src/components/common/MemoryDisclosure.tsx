import React, { useState } from 'react';
import { Brain, ChevronDown, ChevronRight } from 'lucide-react';
import type { RetrievedMemory } from '../../types';

const normalise = (m: RetrievedMemory): { text: string; kind?: string; score?: number | null } =>
  typeof m === 'string' ? { text: m } : { text: m.text, kind: m.kind, score: m.score };

/**
 * "Recalled N memories" disclosure rendered under a persona turn. Collapsed by
 * default; lists exactly what the engine retrieved for that turn (text, kind
 * and score when present). Renders nothing when nothing was recalled — an
 * empty disclosure would imply memory that does not exist.
 */
export const MemoryDisclosure: React.FC<{
  memories?: RetrievedMemory[] | null;
  compact?: boolean;
  className?: string;
}> = ({ memories, compact = false, className }) => {
  const [open, setOpen] = useState(false);
  const items = (memories || []).map(normalise).filter((m) => m.text && m.text.trim());
  if (items.length === 0) return null;
  const n = items.length;

  return (
    <div className={className} style={{ marginTop: compact ? '6px' : '8px' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          background: 'transparent',
          border: 'none',
          padding: 0,
          color: 'var(--text-secondary)',
          fontSize: '0.74rem',
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        <Brain size={12} aria-hidden="true" />
        Recalled {n} {n === 1 ? 'memory' : 'memories'}
      </button>
      {open && (
        <ul
          style={{
            margin: '6px 0 0',
            paddingLeft: '18px',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            fontSize: '0.78rem',
            color: 'var(--text-primary)',
            lineHeight: 1.45,
          }}
        >
          {items.map((m, i) => (
            <li key={i}>
              {m.text}
              {(m.kind || typeof m.score === 'number') && (
                <span
                  style={{
                    marginLeft: '6px',
                    fontSize: '0.72rem',
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono, monospace)',
                  }}
                >
                  {[m.kind, typeof m.score === 'number' ? `score ${m.score.toFixed(2)}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

/**
 * Collapsible "Route" disclosure replacing chrome-style "Served by …" text on a
 * persona turn. Nothing renders when the route is unknown.
 */
export const RouteDisclosure: React.FC<{
  servedBy?: string | null;
  latencyMs?: number | null;
  compact?: boolean;
}> = ({ servedBy, latencyMs, compact = false }) => {
  const [open, setOpen] = useState(false);
  if (!servedBy) return null;
  return (
    <div style={{ marginTop: compact ? '4px' : '6px' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '5px',
          background: 'transparent',
          border: 'none',
          padding: 0,
          color: 'var(--text-secondary)',
          fontSize: '0.74rem',
          fontWeight: 600,
          cursor: 'pointer',
        }}
      >
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        Route
      </button>
      {open && (
        <div
          style={{
            marginTop: '4px',
            fontSize: '0.74rem',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono, monospace)',
          }}
        >
          Served by {servedBy}
          {typeof latencyMs === 'number' ? ` · ${Math.round(latencyMs)}ms` : ''}
        </div>
      )}
    </div>
  );
};

/**
 * Deterministic consistency signals the engine attaches to a persona turn
 * (identity drift, numeric self-contradiction). These are QUALITY findings —
 * the turn was served normally; nothing was retried or swapped. Renders
 * nothing when both flags are false so a clean turn stays clean.
 */
export const ConsistencyFlags: React.FC<{
  identityDrift?: boolean | null;
  driftNotes?: string[] | null;
  contradictionDetected?: boolean | null;
  contradictionDetails?: string | null;
  compact?: boolean;
}> = ({ identityDrift, driftNotes, contradictionDetected, contradictionDetails, compact = false }) => {
  if (!identityDrift && !contradictionDetected) return null;
  const chip: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '0.72rem',
    fontWeight: 700,
    letterSpacing: '0.03em',
    color: 'var(--status-warning-text, #d97706)',
    background: 'rgba(217, 119, 6, 0.12)',
    border: '1px solid rgba(217, 119, 6, 0.35)',
    borderRadius: '999px',
    padding: '1px 8px',
  };
  return (
    <div
      role="status"
      style={{ marginTop: compact ? '6px' : '8px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}
    >
      {identityDrift && (
        <span
          style={chip}
          title={
            (driftNotes && driftNotes.length ? driftNotes.join('; ') : 'Reply states an identity fact that differs from the persona card') +
            ' — quality signal from a deterministic check, not an infrastructure failure.'
          }
        >
          Identity drift detected
        </span>
      )}
      {contradictionDetected && (
        <span
          style={chip}
          title={
            (contradictionDetails || 'Reply contradicts a stated number') +
            ' — quality signal from a deterministic check, not an infrastructure failure.'
          }
        >
          Numeric contradiction
        </span>
      )}
    </div>
  );
};

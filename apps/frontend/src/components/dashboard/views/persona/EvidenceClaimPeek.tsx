import React, { useEffect, useState } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import type { ClaimDetail } from '../../../../types';
import { api } from '../../../../services/api';
import { toUserMessage } from '../../../../utils/apiError';

/**
 * Inline claim → source trace opened from an OBSERVED provenance chip. Fetches
 * each cited evidence claim and lists its supporting sources so a reader can
 * follow persona claim → evidence claim → publisher/URL.
 */
export const EvidenceClaimPeek: React.FC<{ studyId: string; evidenceIds: string[]; onClose: () => void }> = ({
  studyId,
  evidenceIds,
  onClose,
}) => {
  const [claims, setClaims] = useState<ClaimDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setClaims(null);
    setError(null);
    Promise.all(evidenceIds.map((id) => api.getEvidenceClaimDetail(studyId, id)))
      .then((res) => {
        if (alive) setClaims(res);
      })
      .catch((err) => {
        if (alive) setError(toUserMessage(err, { timeoutMs: 15000 }));
      });
    return () => {
      alive = false;
    };
  }, [studyId, evidenceIds]);

  return (
    <div
      role="region"
      aria-label="Cited evidence"
      style={{
        marginTop: '8px',
        background: 'var(--bg-secondary)',
        border: '1px solid rgba(16, 185, 129, 0.3)',
        borderRadius: '10px',
        padding: '10px 12px',
        fontSize: '0.8rem',
        color: 'var(--text-primary)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '6px' }}>
        <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.05em', color: 'var(--accent-emerald)' }}>
          CITED EVIDENCE ({evidenceIds.length})
        </span>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.74rem', fontWeight: 600 }}
        >
          Hide
        </button>
      </div>

      {!claims && !error && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-secondary)' }}>
          <Loader2 size={12} className="animate-spin" aria-hidden="true" /> Loading claim details…
        </div>
      )}
      {error && (
        <div role="alert" style={{ color: 'var(--status-error-text)' }}>
          Evidence detail unavailable: {error}. Claim ids: <code>{evidenceIds.join(', ')}</code>
        </div>
      )}
      {claims && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {claims.map((c) => (
            <li key={c.id} style={{ borderLeft: '2px solid var(--accent-emerald)', paddingLeft: '10px' }}>
              <div style={{ lineHeight: 1.45 }}>{c.claim_text}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                status {c.status} · confidence {typeof c.confidence === 'number' ? Math.round(c.confidence * 100) : '—'}% · id{' '}
                <code>{c.id}</code>
              </div>
              {(c.supporting_sources || []).length > 0 ? (
                <ul style={{ margin: '4px 0 0', paddingLeft: '14px', color: 'var(--text-secondary)' }}>
                  {c.supporting_sources.map((s) => (
                    <li key={s.id}>
                      {s.url ? (
                        <a href={s.url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-cyan)', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                          {s.title || s.publisher} <ExternalLink size={11} aria-hidden="true" />
                        </a>
                      ) : (
                        <span>{s.title || s.publisher}</span>
                      )}
                      {s.publisher && s.title && <span style={{ color: 'var(--text-muted)' }}> — {s.publisher}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '2px' }}>No source rows attached to this claim.</div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

import React, { useEffect, useState } from 'react';
import { ChevronUp, ExternalLink, Loader2 } from 'lucide-react';
import type { ClaimDetail } from '../../../../types';
import { api } from '../../../../services/api';
import { toUserMessage } from '../../../../utils/apiError';

const safeSourceUrl = (value?: string | null): string | undefined => {
  if (!value || /[\u0000-\u001f\u007f-\u009f]/.test(value)) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : undefined;
  } catch {
    return undefined;
  }
};

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
        marginTop: '0.75rem',
        borderTop: '1px solid var(--border-subtle)',
        paddingTop: '0.75rem',
        minWidth: 0,
        overflowWrap: 'anywhere',
        fontSize: '0.875rem',
        color: 'var(--text-main)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-main)' }}>
          CITED EVIDENCE ({evidenceIds.length})
        </span>
        <button
          type="button"
          onClick={onClose}
          className="bx-btn bx-btn--ghost bx-btn--sm"
          title="Hide cited evidence"
          style={{ flexShrink: 0 }}
        >
          <ChevronUp size={14} aria-hidden="true" /> Hide
        </button>
      </div>

      {!claims && !error && (
        <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)' }}>
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
          {claims.map((claim) => (
            <li key={claim.id} style={{ minWidth: 0, paddingBottom: '0.75rem' }}>
              <div style={{ lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{claim.claim_text}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                status {claim.status} · confidence {typeof claim.confidence === 'number' ? Math.round(claim.confidence * 100) : '—'}% · id{' '}
                <code>{claim.id}</code>
              </div>
              {claim.rationale && (
                <div style={{ marginTop: '0.75rem' }}>
                  <div style={{ fontWeight: 600 }}>Rationale</div>
                  <p style={{ margin: '0.25rem 0 0', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{claim.rationale}</p>
                </div>
              )}
              {[
                { label: 'Supporting sources', sources: claim.supporting_sources || [] },
                { label: 'Contradicting sources', sources: claim.contradicting_sources || [] },
              ].map(({ label, sources }) => sources.length > 0 && (
                <div key={label} style={{ marginTop: '0.75rem' }}>
                  <div style={{ fontWeight: 600 }}>{label}</div>
                  <ul aria-label={label} style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem', color: 'var(--text-main)' }}>
                    {sources.map((source) => {
                      const sourceUrl = safeSourceUrl(source.url);
                      return (
                        <li key={source.id} style={{ minWidth: 0, marginTop: '0.5rem' }}>
                          {sourceUrl ? (
                            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-main)', textDecoration: 'underline', textUnderlineOffset: '0.2em' }}>
                              {source.title || source.publisher || source.id} <ExternalLink size={12} aria-hidden="true" style={{ verticalAlign: 'middle' }} />
                            </a>
                          ) : (
                            <span>{source.title || source.publisher || source.id}</span>
                          )}
                          {source.publisher && source.title && <span style={{ color: 'var(--text-muted)' }}> — {source.publisher}</span>}
                          {!sourceUrl && source.url && <div style={{ whiteSpace: 'pre-wrap' }}>{source.url}</div>}
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            Source <code>{source.id}</code> · {source.source_type} · {source.status}
                            {source.content_hash && <div>Content hash <code>{source.content_hash}</code></div>}
                          </div>
                          {source.content && <p style={{ margin: '0.25rem 0 0', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{source.content}</p>}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
              {!claim.supporting_sources?.length && !claim.contradicting_sources?.length && !claim.supporting_chunks?.length && (
                <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>No source rows attached to this claim.</div>
              )}
              {(claim.supporting_chunks || []).length > 0 && (
                <div style={{ marginTop: '0.75rem' }}>
                  <div style={{ fontWeight: 600 }}>Supporting excerpts</div>
                  <ul aria-label="Supporting excerpts" style={{ margin: '0.25rem 0 0', paddingLeft: '1.25rem' }}>
                    {claim.supporting_chunks.map((chunk) => (
                      <li key={chunk.id} style={{ minWidth: 0, marginTop: '0.5rem' }}>
                        <blockquote style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{chunk.content}</blockquote>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Source <code>{chunk.source_id}</code> · chunk <code>{chunk.id}</code> · index <code>{chunk.chunk_index}</code></div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

import React, { useEffect, useState } from 'react';
import { Brain, Loader2 } from 'lucide-react';
import type { MemoryItem } from '../../../../types';
import { api } from '../../../../services/api';
import { toUserMessage } from '../../../../utils/apiError';

const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
};

/**
 * Persona memory list (GET /api/personas/{id}/memories). Loading, empty and
 * error states are all explicit — an empty list is "no memories yet", never a
 * silent blank, and a 503/404 is reported as such.
 */
export const PersonaMemoryPanel: React.FC<{ personaId: string }> = ({ personaId }) => {
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setItems(null);
    api
      .getMemories(personaId)
      .then((res) => {
        if (alive) setItems(res);
      })
      .catch((err) => {
        if (alive) setError(toUserMessage(err, { timeoutMs: 15000 }));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [personaId]);

  return (
    <section aria-label="Persona memory" style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '10px' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Brain size={18} aria-hidden="true" style={{ flexShrink: 0 }} /> Memory
          </h3>
          {items && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {items.length} item{items.length === 1 ? '' : 's'} stored
            </span>
          )}
        </div>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: '0 0 1rem', lineHeight: 1.5 }}>
          Verbatim persona statements and researcher context. Researcher questions are not persona recollections.
        </p>

        {loading && (
          <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading memories…
          </div>
        )}

        {!loading && error && (
          <div role="alert" style={{ color: 'var(--status-error-text)', fontSize: '0.84rem' }}>
            Memories could not be loaded: {error}
          </div>
        )}

        {!loading && !error && items && items.length === 0 && (
          <div role="status" style={{ padding: '1rem 0', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            No memories recorded yet — they form as this persona is interviewed.
          </div>
        )}

        {!loading && !error && items && items.length > 0 && (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {items.map((item) => (
                <li key={item.id} style={{ minWidth: 0, borderTop: '1px solid var(--border-subtle)', padding: '0.75rem 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-main)', background: 'var(--bg-card)', padding: '1px 6px', borderRadius: '4px' }}>
                      {item.kind}
                    </span>
                    {item.source && item.source !== 'persona' && (
                      <span
                        title="Text authored by the researcher, kept as context — not a persona recollection"
                        style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--status-warn-text)', background: 'var(--status-warn-bg)', padding: '1px 6px', borderRadius: '4px' }}
                      >
                        asked by researcher
                      </span>
                    )}
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)' }}>
                      importance {typeof item.importance === 'number' ? item.importance.toFixed(2) : '—'}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>{formatDate(item.created_at)}</span>
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-main)', lineHeight: 1.5, overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' }}>{item.text}</div>
                </li>
            ))}
          </ul>
        )}
    </section>
  );
};

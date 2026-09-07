import React, { useEffect, useState } from 'react';
import { Brain, Loader2 } from 'lucide-react';
import type { MemoryItem } from '../../../../types';
import { api } from '../../../../services/api';
import { toUserMessage } from '../../../../utils/apiError';

const KIND_TONE: Record<string, { fg: string; bg: string }> = {
  semantic: { fg: 'var(--accent-cyan)', bg: 'rgba(34, 211, 238, 0.12)' },
  episodic: { fg: 'var(--accent-emerald)', bg: 'rgba(16, 185, 129, 0.12)' },
  reflection: { fg: '#A855F7', bg: 'rgba(168, 85, 247, 0.12)' },
};

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '14px', padding: '18px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '10px' }}>
          <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Brain size={18} color="var(--accent-teal)" aria-hidden="true" /> Memory
          </h4>
          {items && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              {items.length} item{items.length === 1 ? '' : 's'} stored
            </span>
          )}
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '0 0 14px' }}>
          Statements this persona made during interviews, stored verbatim with kind and importance. Researcher
          questions are kept separately as context and are never treated as the persona&apos;s own memory;
          retrieval per turn is shown under the transcript as &quot;Recalled N memories&quot;.
        </p>

        {loading && (
          <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)', fontSize: '0.84rem' }}>
            <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading memories…
          </div>
        )}

        {!loading && error && (
          <div role="alert" style={{ color: 'var(--status-error-text)', fontSize: '0.84rem' }}>
            Memories could not be loaded: {error}
          </div>
        )}

        {!loading && !error && items && items.length === 0 && (
          <div style={{ border: '1px dashed var(--border-subtle)', borderRadius: '10px', padding: '16px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.84rem' }}>
            No memories recorded yet — they form as this persona is interviewed.
          </div>
        )}

        {!loading && !error && items && items.length > 0 && (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {items.map((m) => {
              const tone = KIND_TONE[m.kind] || { fg: 'var(--text-secondary)', bg: 'var(--fill-soft-2)' };
              return (
                <li key={m.id} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '4px' }}>
                    <span style={{ fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.05em', color: tone.fg, background: tone.bg, padding: '1px 6px', borderRadius: '4px', textTransform: 'uppercase' }}>
                      {m.kind}
                    </span>
                    {m.source && m.source !== 'persona' && (
                      <span
                        title="Text authored by the researcher, kept as context — not a persona recollection"
                        style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--status-warning-text, #d97706)', background: 'rgba(217, 119, 6, 0.12)', padding: '1px 6px', borderRadius: '4px' }}
                      >
                        asked by researcher
                      </span>
                    )}
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono, monospace)' }}>
                      importance {typeof m.importance === 'number' ? m.importance.toFixed(2) : '—'}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>{formatDate(m.created_at)}</span>
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.45 }}>{m.text}</div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};

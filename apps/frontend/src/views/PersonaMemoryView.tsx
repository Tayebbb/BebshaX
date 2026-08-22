import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { MemoryItem, MemoryKind, Persona } from '../types';

interface PersonaMemoryViewProps {
  initialPersonaId?: string;
}

export const PersonaMemoryView: React.FC<PersonaMemoryViewProps> = ({ initialPersonaId }) => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>(initialPersonaId || 'per_sarah_01');
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [kindFilter, setKindFilter] = useState<'all' | MemoryKind>('all');
  const [loading, setLoading] = useState(true);

  // New Memory state
  const [newText, setNewText] = useState('');
  const [newKind, setNewKind] = useState<MemoryKind>('episodic');
  const [newImportance, setNewImportance] = useState(0.8);
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const perList = await api.getPersonas();
      setPersonas(perList);
      const targetId = initialPersonaId || (perList.length > 0 ? perList[0].id : 'per_sarah_01');
      setSelectedPersonaId(targetId);
      const memList = await api.getMemories(targetId);
      setMemories(memList);
      setLoading(false);
    };
    load();
  }, [initialPersonaId]);

  const handlePersonaChange = async (id: string) => {
    setSelectedPersonaId(id);
    setLoading(true);
    const memList = await api.getMemories(id);
    setMemories(memList);
    setLoading(false);
  };

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newText) return;
    setAdding(true);
    const item: MemoryItem = {
      id: `mem_${Date.now().toString(36)}`,
      persona_id: selectedPersonaId,
      kind: newKind,
      text: newText,
      importance: newImportance,
      recency_weight: 1.0,
      relevance_score: 0.95,
      created_at: new Date().toISOString(),
    };
    setMemories((prev) => [item, ...prev]);
    setNewText('');
    setAdding(false);
  };

  const filteredMemories = kindFilter === 'all' ? memories : memories.filter((m) => m.kind === kindFilter);
  const selectedPersona = personas.find((p) => p.id === selectedPersonaId);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Header & Filter Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', color: '#fff' }}>
            Persistent Persona Memory: {selectedPersona?.name || 'Loading...'}
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Stores semantic facts, episodic dialog observations, and reflection summaries powered by pgvector (port 5433).
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <select
            className="form-select"
            style={{ width: '200px' }}
            value={selectedPersonaId}
            onChange={(e) => handlePersonaChange(e.target.value)}
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', padding: '3px', borderRadius: '8px' }}>
            {(['all', 'semantic', 'episodic', 'reflection'] as const).map((k) => (
              <button
                key={k}
                onClick={() => setKindFilter(k)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  background: kindFilter === k ? 'rgba(99, 102, 241, 0.4)' : 'transparent',
                  color: kindFilter === k ? '#fff' : 'var(--text-muted)',
                  textTransform: 'capitalize',
                }}
              >
                {k}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        {/* Memories List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading memory items...</div>
          ) : filteredMemories.length === 0 ? (
            <div className="glass-panel" style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
              No memories recorded for this category yet.
            </div>
          ) : (
            filteredMemories.map((mem) => {
              let badgeColor = '#38bdf8';
              let badgeBg = 'rgba(56, 189, 248, 0.15)';
              if (mem.kind === 'episodic') {
                badgeColor = '#c084fc';
                badgeBg = 'rgba(192, 132, 252, 0.15)';
              } else if (mem.kind === 'reflection') {
                badgeColor = '#fbbf24';
                badgeBg = 'rgba(251, 191, 36, 0.15)';
              }

              return (
                <div
                  key={mem.id}
                  className="glass-panel"
                  style={{
                    padding: '18px 20px',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: badgeBg,
                          color: badgeColor,
                          textTransform: 'uppercase',
                        }}
                      >
                        {mem.kind}
                      </span>
                      <span className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                        {mem.id}
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: '12px', fontSize: '0.75rem' }}>
                      <span style={{ color: 'var(--text-muted)' }}>
                        Importance: <strong style={{ color: '#34d399' }}>{mem.importance.toFixed(2)}</strong>
                      </span>
                      <span style={{ color: 'var(--text-muted)' }}>
                        Recency: <strong style={{ color: '#38bdf8' }}>{mem.recency_weight.toFixed(2)}</strong>
                      </span>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.86rem', color: '#f1f5f9', lineHeight: 1.6 }}>{mem.text}</p>

                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: '12px',
                      fontSize: '0.7rem',
                      color: 'var(--text-dim)',
                    }}
                  >
                    <span>Recorded: {new Date(mem.created_at).toLocaleString()}</span>
                    <span className="mono" style={{ color: 'var(--text-dim)' }}>
                      pgvector embedding: indexed
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Add Memory Form & Scoring Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Add Observation Card */}
          <div className="glass-panel" style={{ padding: '20px' }}>
            <h3 style={{ fontSize: '0.95rem', color: '#fff', marginBottom: '14px' }}>Record Memory Observation</h3>

            <form onSubmit={handleAddMemory} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                  Memory Kind
                </label>
                <select className="form-select" value={newKind} onChange={(e) => setNewKind(e.target.value as MemoryKind)}>
                  <option value="episodic">Episodic (Direct Dialogue Event)</option>
                  <option value="semantic">Semantic (Stable Identity Fact)</option>
                  <option value="reflection">Reflection (High-Level Insight)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>
                  Observation Text
                </label>
                <textarea
                  required
                  rows={3}
                  className="form-textarea"
                  placeholder="e.g. Expressed strong interest in weekly earnings projections..."
                  value={newText}
                  onChange={(e) => setNewText(e.target.value)}
                />
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                  <span>Importance Score</span>
                  <strong style={{ color: '#38bdf8' }}>{newImportance}</strong>
                </div>
                <input
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  style={{ width: '100%', cursor: 'pointer' }}
                  value={newImportance}
                  onChange={(e) => setNewImportance(parseFloat(e.target.value))}
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ marginTop: '6px' }} disabled={adding}>
                {adding ? 'Encoding vector...' : '+ Save Memory'}
              </button>
            </form>
          </div>

          {/* Retrieval Formula Card */}
          <div className="glass-panel" style={{ padding: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '10px' }}>
              Retrieval Formula (Generative Agents)
            </h4>
            <div
              className="mono"
              style={{
                fontSize: '0.75rem',
                color: '#38bdf8',
                background: 'rgba(0,0,0,0.4)',
                padding: '10px',
                borderRadius: '6px',
                lineHeight: 1.5,
              }}
            >
              score = w_rel·cos(v, q) + w_rec·e^(-λΔt) + w_imp·I
            </div>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '8px', lineHeight: 1.5 }}>
              Interviews query this stream per turn, retrieving only high-relevance memories to maintain persona consistency without exceeding context budgets.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

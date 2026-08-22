import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Business, Persona } from '../types';
import { StatusBadge } from '../components/StatusBadge';
import { JsonViewerModal } from '../components/JsonViewerModal';

interface PersonaProfileViewProps {
  initialBusinessId?: string;
  onNavigateToMemory?: (personaId: string) => void;
  onNavigateToInterview?: (personaId: string) => void;
}

export const PersonaProfileView: React.FC<PersonaProfileViewProps> = ({
  initialBusinessId,
  onNavigateToMemory,
  onNavigateToInterview,
}) => {
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>('per_sarah_01');
  const [loading, setLoading] = useState(true);

  // Generation Form State
  const [showGenModal, setShowGenModal] = useState(false);
  const [targetBizId, setTargetBizId] = useState<string>('');
  const [audienceSegment, setAudienceSegment] = useState('');
  const [hints, setHints] = useState('');
  const [generating, setGenerating] = useState(false);

  // JSON modal
  const [showJsonModal, setShowJsonModal] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const [perList, bizList] = await Promise.all([api.getPersonas(), api.getBusinesses()]);
      setPersonas(perList);
      setBusinesses(bizList);
      if (initialBusinessId) {
        setTargetBizId(initialBusinessId);
      } else if (bizList.length > 0) {
        setTargetBizId(bizList[0].id);
      }
      if (perList.length > 0 && !selectedPersonaId) {
        setSelectedPersonaId(perList[0].id);
      }
      setLoading(false);
    };
    load();
  }, [initialBusinessId]);

  const activePersona = personas.find((p) => p.id === selectedPersonaId) || personas[0];

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!audienceSegment || !targetBizId) return;
    setGenerating(true);
    const parsedHints = hints ? hints.split(',').map((h) => h.trim()) : [];
    const result = await api.generatePersona(targetBizId, audienceSegment, parsedHints);
    setPersonas((prev) => [result.persona, ...prev]);
    setSelectedPersonaId(result.persona.id);
    setGenerating(false);
    setShowGenModal(false);
    setAudienceSegment('');
    setHints('');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* View Header & Action */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h2 style={{ fontSize: '1.25rem', color: '#fff' }}>Evidence-Grounded Persona Profile</h2>
          <select
            className="form-select"
            style={{ width: '220px', padding: '6px 12px' }}
            value={selectedPersonaId}
            onChange={(e) => setSelectedPersonaId(e.target.value)}
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.archetype.slice(0, 20)}...)
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            className="btn btn-secondary"
            onClick={() => setShowJsonModal(true)}
            style={{ fontSize: '0.82rem' }}
          >
            <span>📄</span> Raw JSON
          </button>

          <button className="btn btn-primary" onClick={() => setShowGenModal(true)}>
            <span>🧬</span> Generate New Persona
          </button>
        </div>
      </div>

      {loading || !activePersona ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading persona profile...</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px' }}>
          {/* Left Column: Demographic & Identity Summary */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Identity Card */}
            <div className="glass-panel" style={{ padding: '24px', textAlign: 'center' }}>
              <div
                style={{
                  width: '72px',
                  height: '72px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
                  margin: '0 auto 14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '32px',
                  boxShadow: 'var(--glow-indigo)',
                }}
              >
                👤
              </div>

              <h3 style={{ fontSize: '1.3rem', color: '#fff', marginBottom: '4px' }}>{activePersona.name}</h3>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38bdf8', marginBottom: '8px' }}>
                {activePersona.archetype}
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '16px' }}>
                "{activePersona.tagline}"
              </p>

              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
                <span className="badge badge-success">Status: {activePersona.status}</span>
                <span className="badge badge-pool">v{activePersona.version}</span>
              </div>
            </div>

            {/* Demographics Card */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '14px' }}>
                Demographic Coordinates
              </h4>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.8rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Age / Gender:</span>
                  <strong style={{ color: '#fff' }}>
                    {activePersona.demographics.age} • {activePersona.demographics.gender}
                  </strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Occupation:</span>
                  <strong style={{ color: '#fff', textAlign: 'right' }}>{activePersona.demographics.occupation}</strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Income:</span>
                  <strong style={{ color: '#34d399', textAlign: 'right' }}>{activePersona.demographics.income_bracket}</strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Location:</span>
                  <strong style={{ color: '#fff' }}>{activePersona.demographics.location}</strong>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Education:</span>
                  <strong style={{ color: '#fff', textAlign: 'right' }}>{activePersona.demographics.education}</strong>
                </div>
              </div>
            </div>

            {/* Critic & Validation Heuristics */}
            <div className="glass-panel" style={{ padding: '20px' }}>
              <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '12px' }}>
                Quality & Grounding Metrics
              </h4>

              <div style={{ display: 'flex', justifyContent: 'space-around', marginBottom: '14px' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#34d399' }}>
                    {(activePersona.consistency_score * 100).toFixed(0)}%
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Consistency Score</div>
                </div>

                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '1.4rem', fontWeight: 800, color: '#38bdf8' }}>
                    {(activePersona.grounding_ratio * 100).toFixed(0)}%
                  </div>
                  <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Grounding Ratio</div>
                </div>
              </div>

              <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '6px' }}>
                <strong>Critic Note:</strong> {activePersona.critic_notes}
              </div>

              <div style={{ marginTop: '14px', fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                Generated via: <span className="mono" style={{ color: '#c084fc' }}>{activePersona.generation_model}</span>
              </div>
            </div>

            {/* Navigation Actions */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                className="btn btn-primary"
                style={{ width: '100%' }}
                onClick={() => onNavigateToInterview && onNavigateToInterview(activePersona.id)}
              >
                <span>💬</span> Launch Interview Chat
              </button>

              <button
                className="btn btn-secondary"
                style={{ width: '100%' }}
                onClick={() => onNavigateToMemory && onNavigateToMemory(activePersona.id)}
              >
                <span>🧠</span> View Memory Stream
              </button>
            </div>
          </div>

          {/* Right Column: Grouped Attributes with Provenance Badges & Evidence Quotes */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div className="glass-panel" style={{ padding: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
                <h3 style={{ fontSize: '1.1rem', color: '#fff' }}>Evidence-Grounded Persona Attributes</h3>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <span className="badge badge-observed">OBSERVED</span>
                  <span className="badge badge-inferred">INFERRED</span>
                  <span className="badge badge-synthetic">SYNTHETIC</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {activePersona.attributes.map((attr, idx) => (
                  <div
                    key={idx}
                    style={{
                      background: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '10px',
                      padding: '16px 20px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            padding: '2px 8px',
                            borderRadius: '4px',
                            background: 'rgba(99, 102, 241, 0.15)',
                            color: '#93c5fd',
                            textTransform: 'uppercase',
                          }}
                        >
                          {attr.category}
                        </span>
                        <h4 style={{ fontSize: '0.95rem', color: '#fff' }}>{attr.title}</h4>
                      </div>

                      <StatusBadge type="provenance" value={attr.provenance_class} />
                    </div>

                    <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: attr.evidence ? '12px' : '0' }}>
                      {attr.description}
                    </p>

                    {/* Evidence Quote Link */}
                    {attr.evidence && (
                      <div
                        style={{
                          background: 'rgba(6, 182, 212, 0.06)',
                          borderLeft: '3px solid #06b6d4',
                          borderRadius: '0 8px 8px 0',
                          padding: '10px 14px',
                          fontSize: '0.76rem',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', color: '#22d3ee', fontWeight: 600, marginBottom: '4px' }}>
                          <span>🔍 Grounding Source: {attr.evidence.source}</span>
                          <span>Confidence: {(attr.evidence.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          "{attr.evidence.quote}"
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Generate Persona Modal */}
      {showGenModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
          onClick={() => setShowGenModal(false)}
        >
          <div
            className="glass-panel"
            style={{
              width: '100%',
              maxWidth: '560px',
              padding: '28px',
              backgroundColor: '#0c1222',
              borderRadius: '14px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: '1.2rem', color: '#fff', marginBottom: '8px' }}>Generate Synthetic Persona</h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '18px' }}>
              Triggers <span className="mono" style={{ color: '#38bdf8' }}>TaskType.PERSONA_GENERATION</span> via the multi-model reasoning pool.
            </p>

            <form onSubmit={handleGenerate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Target Business *
                </label>
                <select
                  required
                  className="form-select"
                  value={targetBizId}
                  onChange={(e) => setTargetBizId(e.target.value)}
                >
                  {businesses.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} ({b.industry})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Audience Segment / Archetype Target *
                </label>
                <textarea
                  required
                  rows={3}
                  placeholder="e.g. Variable-income delivery driver who struggles with quarterly taxes and hates overdraft fees"
                  className="form-textarea"
                  value={audienceSegment}
                  onChange={(e) => setAudienceSegment(e.target.value)}
                />
              </div>

              <div>
                <label style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                  Generation Hints (comma-separated, optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Mobile-first user, High car repair sensitivity"
                  className="form-input"
                  value={hints}
                  onChange={(e) => setHints(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowGenModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={generating}>
                  {generating ? 'Synthesizing with LLM...' : 'Generate Persona'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* JSON Viewer */}
      <JsonViewerModal
        isOpen={showJsonModal}
        title={`Persona Schema: ${activePersona?.name}`}
        data={activePersona}
        onClose={() => setShowJsonModal(false)}
      />
    </div>
  );
};

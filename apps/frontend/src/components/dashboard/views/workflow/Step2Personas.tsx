import React from 'react';
import { ArrowRight, RefreshCw, Sparkles, Trash2 } from 'lucide-react';
import { Persona, PersonaRoleSuggestion } from '../../../../types';

/** The backend may mark a persona as generated without retrieved evidence.
 * The field is optional — the grounding value alone decides when it is absent. */
type PersonaGroundingHints = Persona & { grounding_basis?: string };

/** Evidence-backed only when a real grounding ratio survived generation and the
 * backend did not flag the persona as "no evidence retrieved". */
const isEvidenceBacked = (p: Persona): boolean => {
  const ratio = p.grounding_ratio ?? 0;
  const basis = (p as PersonaGroundingHints).grounding_basis;
  return ratio > 0 && basis !== 'no_evidence_retrieved';
};

/** Skeleton/template fallbacks are stamped by the backend generator. */
const isTemplatePersona = (p: Persona): boolean =>
  typeof p.generation_model === 'string' && p.generation_model.includes('skeleton-fallback');

/** Step 2 — grounded persona library. Pure JSX extraction from
 * StudyWorkflowView: generation state/handlers stay in the parent; the modal
 * trigger ref is written here so the parent can return focus on close. */
interface Step2PersonasProps {
  personas: Persona[];
  personaGenError: string | null;
  isGeneratingPersonas: boolean;
  suggestedRoles: PersonaRoleSuggestion[];
  handleGeneratePersonas: () => Promise<void>;
  handleStepChange: (newStep: number, opts?: { reportReady?: boolean }) => void;
  handleRemovePersona: (personaId: string, e: React.MouseEvent) => void;
  personaModalTriggerRef: React.MutableRefObject<HTMLElement | null>;
  setViewingPersona: React.Dispatch<React.SetStateAction<Persona | null>>;
  isStepUnlocked: (step: number) => boolean;
}

export const Step2Personas: React.FC<Step2PersonasProps> = ({
  personas,
  personaGenError,
  isGeneratingPersonas,
  suggestedRoles,
  handleGeneratePersonas,
  handleStepChange,
  handleRemovePersona,
  personaModalTriggerRef,
  setViewingPersona,
  isStepUnlocked,
}) => {
  const evidenceBackedCount = personas.filter(isEvidenceBacked).length;
  return (
    <>
            {personaGenError && (
              <div
                role="alert"
                style={{
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.4)',
                  color: 'var(--status-error-text)',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  fontSize: '0.88rem',
                }}
              >
                Persona generation failed: {personaGenError} — no personas were fabricated. Retry when ready.
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <h1 style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--text-main)', margin: '0 0 4px 0' }}>
                  Grounded Persona Library
                </h1>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                  <span>Total Personas</span>
                  <span>({personas.length})</span>
                  <span>
                    {personas.length > 0
                      ? `• ${evidenceBackedCount} of ${personas.length} backed by retrieved evidence — each card says which`
                      : '• Built from your description; any evidence we retrieve is labelled per persona'}
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  type="button"
                  onClick={handleGeneratePersonas}
                  disabled={isGeneratingPersonas}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--accent-cyan)',
                    borderRadius: '8px',
                    padding: '8px 16px',
                    fontSize: '0.84rem',
                    fontWeight: 600,
                    cursor: isGeneratingPersonas ? 'not-allowed' : 'pointer',
                    opacity: isGeneratingPersonas ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <RefreshCw size={14} className={isGeneratingPersonas ? 'animate-spin' : ''} />
                  Regenerate Personas
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (isStepUnlocked(3)) handleStepChange(3);
                  }}
                  disabled={!isStepUnlocked(3)}
                  title={isStepUnlocked(3) ? undefined : 'Generate personas first'}
                  style={
                    isStepUnlocked(3)
                      ? {
                          background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                          border: 'none',
                          color: 'var(--text-on-accent)',
                          borderRadius: '8px',
                          padding: '8px 20px',
                          fontSize: '0.84rem',
                          fontWeight: 700,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }
                      : {
                          background: 'var(--bg-card-hover)',
                          border: '1px solid var(--border-subtle)',
                          color: 'var(--text-faint)',
                          borderRadius: '8px',
                          padding: '8px 20px',
                          fontSize: '0.84rem',
                          fontWeight: 700,
                          cursor: 'not-allowed',
                          opacity: 0.5,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }
                  }
                >
                  Generate Script
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>

            {/* Generation progress banner */}
            {isGeneratingPersonas && (
              <div
                role="status"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  background: 'var(--accent-subtle)',
                  border: '1px solid var(--accent-glow)',
                  borderRadius: '12px',
                  padding: '14px 18px',
                  color: 'var(--accent-teal-bright)',
                  fontSize: '0.88rem',
                  fontWeight: 600,
                }}
              >
                <Sparkles size={16} className="animate-spin" />
                Generating grounded personas from evidence datasets — this can take a minute on free-tier routes...
              </div>
            )}

            {/* Persona Cards Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: '20px' }}>
              {isGeneratingPersonas &&
                personas.length === 0 &&
                Array.from({
                  length:
                    suggestedRoles.filter((r) => r.selected && r.count > 0).reduce((sum, r) => sum + r.count, 0) || 6,
                }).map((_, i) => (
                  <div
                    key={`persona_skeleton_${i}`}
                    className="bx-stagger"
                    style={{
                      ['--bx-i' as string]: Math.min(i, 12),
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '16px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '14px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="bx-skeleton" style={{ width: '42px', height: '42px', borderRadius: '10px', flexShrink: 0 }} />
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                        <div className="bx-skeleton" style={{ height: '14px', width: '55%' }} />
                        <div className="bx-skeleton" style={{ height: '11px', width: '40%' }} />
                      </div>
                    </div>
                    <div className="bx-skeleton" style={{ height: '30px', borderRadius: '6px' }} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <div className="bx-skeleton" style={{ height: '11px', width: '100%' }} />
                      <div className="bx-skeleton" style={{ height: '11px', width: '90%' }} />
                      <div className="bx-skeleton" style={{ height: '11px', width: '70%' }} />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', paddingTop: '8px' }}>
                      <div className="bx-skeleton" style={{ height: '13px', width: '38%' }} />
                      <div className="bx-skeleton" style={{ height: '18px', width: '25%', borderRadius: '6px' }} />
                    </div>
                  </div>
                ))}
              {personas.map((p, cardIdx) => (
                <div
                  key={p.id}
                  className="bx-stagger bx-lift"
                  style={{
                    ['--bx-i' as string]: Math.min(cardIdx, 12),
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: '16px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '14px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div
                        style={{
                          width: '42px',
                          height: '42px',
                          borderRadius: '10px',
                          background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                          color: 'var(--text-on-accent)',
                          fontWeight: 700,
                          fontSize: '1rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        {p.initials || p.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>{p.name}</div>
                          <span style={{ fontSize: '0.72rem', color: 'var(--accent-teal)', background: 'var(--accent-subtle)', border: '1px solid var(--accent-glow)', padding: '1px 5px', borderRadius: '4px', fontWeight: 600 }}>
                            {p.country_code || 'BD'}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--accent-cyan)' }}>{p.archetype || p.role_title}</div>
                        {p.tagline && <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{p.tagline}</div>}
                        {isTemplatePersona(p) && (
                          <div
                            title={p.critic_notes || 'Generated from a template because the model output could not be used.'}
                            style={{
                              display: 'inline-block',
                              marginTop: '4px',
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              color: 'var(--status-warn-text)',
                              background: 'var(--fill-soft)',
                              border: '1px solid var(--border-subtle)',
                              padding: '1px 6px',
                              borderRadius: '4px',
                            }}
                          >
                            Template — regenerate for full detail
                          </div>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(e) => handleRemovePersona(p.id, e)}
                      style={{ background: 'transparent', border: 'none', color: 'var(--text-faint)', cursor: 'pointer' }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>

                  {p.personality && (
                    <div title="Big Five (OCEAN) personality traits" style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '4px', background: 'var(--bg-secondary)', padding: '6px 8px', borderRadius: '6px', border: '1px solid var(--border-subtle)', textAlign: 'center' }}>
                      {[
                        { l: 'O', v: p.personality.openness, c: '#38BDF8' },
                        { l: 'C', v: p.personality.conscientiousness, c: 'var(--accent-emerald)' },
                        { l: 'E', v: p.personality.extroversion, c: '#F59E0B' },
                        { l: 'A', v: p.personality.agreeableness, c: '#A855F7' },
                        { l: 'N', v: p.personality.neuroticism, c: '#EC4899' },
                      ].map((t) => (
                        <div key={t.l} style={{ fontSize: '0.75rem' }}>
                          <span style={{ color: t.c, fontWeight: 700 }}>{t.v}</span>
                          <span style={{ color: 'var(--text-secondary)', marginLeft: '2px' }}>{t.l}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <p style={{ fontSize: '0.84rem', color: 'var(--text-primary)', lineHeight: 1.45, margin: 0 }}>
                    {p.description ||
                      p.tagline ||
                      (p.quote ? `"${p.quote}"` : '') ||
                      'No summary yet — open the full profile to see this persona’s attributes.'}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 'auto', paddingTop: '8px' }}>
                    <button
                      type="button"
                      onClick={(e) => {
                        personaModalTriggerRef.current = e.currentTarget;
                        setViewingPersona(p);
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--accent-teal)',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        padding: 0,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      View full profile <ArrowRight size={13} />
                    </button>
                    {isEvidenceBacked(p) ? (
                      <span
                        title="Share of this persona's claims traced to retrieved evidence"
                        style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--accent-emerald)', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 8px', borderRadius: '6px' }}
                      >
                        {Math.round((p.grounding_ratio ?? 0) * 100)}% evidence-backed
                      </span>
                    ) : (
                      <span
                        title="No supporting evidence was retrieved for this persona — its details come from your description."
                        style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)', background: 'var(--fill-soft)', border: '1px solid var(--border-subtle)', padding: '2px 8px', borderRadius: '6px' }}
                      >
                        Not evidence-backed — inferred from your description
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Empty state: nothing generated yet and not currently generating */}
            {!isGeneratingPersonas && personas.length === 0 && (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px',
                  textAlign: 'center',
                  padding: '64px 24px',
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '16px',
                  color: 'var(--text-secondary)',
                }}
              >
                <Sparkles size={28} className="text-teal-400" />
                <div style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)' }}>No personas yet</div>
                <div style={{ fontSize: '0.85rem', maxWidth: '420px' }}>
                  Generate grounded personas from your approved research goal and selected roles.
                </div>
                <button
                  type="button"
                  onClick={handleGeneratePersonas}
                  style={{
                    marginTop: '6px',
                    background: 'linear-gradient(135deg, #14B8A6 0%, #0D9488 100%)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '10px 20px',
                    color: 'var(--text-on-accent)',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <Sparkles size={15} />
                  Generate Personas
                </button>
              </div>
            )}
    </>
  );
};

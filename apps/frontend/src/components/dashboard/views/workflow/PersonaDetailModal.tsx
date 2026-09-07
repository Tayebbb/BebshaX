import React from 'react';
import { X } from 'lucide-react';
import { Persona } from '../../../../types';
import { ProvenanceChip } from '../PersonaLibraryView';

/** Full-profile persona modal. Pure JSX extraction from StudyWorkflowView —
 * the focus trap / Escape wiring lives in the parent and targets
 * `personaModalRef`, which must be attached to the dialog element here. */
interface PersonaDetailModalProps {
  viewingPersona: Persona;
  personaModalRef: React.MutableRefObject<HTMLDivElement | null>;
  closePersonaModal: () => void;
}

export const PersonaDetailModal: React.FC<PersonaDetailModalProps> = ({
  viewingPersona,
  personaModalRef,
  closePersonaModal,
}) => {
  return (
        <div
          className="bx-backdrop"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'var(--scrim)',
            zIndex: 50,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
          }}
          onClick={closePersonaModal}
        >
          <div
            ref={personaModalRef}
            className="bx-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`${viewingPersona.name} — full persona profile`}
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '20px',
              maxWidth: '640px',
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              padding: '28px 32px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <div
                  style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '12px',
                    background: 'var(--accent-gradient)',
                    color: 'var(--text-on-accent)',
                    fontWeight: 700,
                    fontSize: '1.2rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {viewingPersona.initials || viewingPersona.name.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {viewingPersona.name}
                    {viewingPersona.data_source === 'cached' && (
                      <span
                        title="Served from seeded/cached data — not generated live for this study"
                        style={{ fontSize: '0.72rem', fontWeight: 400, color: 'var(--text-secondary)', background: 'var(--bg-card-hover)', border: '1px solid var(--border-medium)', padding: '2px 6px', borderRadius: '4px', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
                      >
                        CACHED
                      </span>
                    )}
                  </h3>
                  <div style={{ fontSize: '0.84rem', color: 'var(--accent-cyan)' }}>{viewingPersona.archetype}</div>
                </div>
              </div>
              <button
                type="button"
                onClick={closePersonaModal}
                aria-label="Close persona profile"
                style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: 0 }}>
              {viewingPersona.description || viewingPersona.tagline}
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))', gap: '10px', background: 'var(--bg-secondary)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
              {/* Honest demographics: a missing value renders "Not available" — never invented. */}
              {(
                [
                  { label: 'Age', value: viewingPersona.demographics?.age },
                  { label: 'Occupation', value: viewingPersona.demographics?.occupation },
                  { label: 'Location', value: viewingPersona.demographics?.location },
                  { label: 'Country', value: viewingPersona.origin_country || viewingPersona.country_code },
                ] as { label: string; value?: string | number }[]
              ).map((d) => (
                <div key={d.label}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{d.label}: </span>
                  {d.value ? (
                    <span style={{ fontSize: '0.82rem', color: d.label === 'Country' ? 'var(--accent-teal)' : 'var(--text-main)', fontWeight: d.label === 'Country' ? 600 : undefined }}>
                      {d.value}
                    </span>
                  ) : (
                    <span style={{ fontSize: '0.82rem', color: 'var(--text-faint)' }}>Not available</span>
                  )}
                </div>
              ))}
            </div>

            {/* Big Five Personality */}
            {viewingPersona.personality && (
              <div style={{ background: 'var(--bg-secondary)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div
                  title="Big Five (OCEAN) trait model — openness, conscientiousness, extroversion, agreeableness, neuroticism"
                  style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-teal)', letterSpacing: '0.04em', marginBottom: '8px' }}
                >
                  Personality profile (Big Five)
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '8px', textAlign: 'center' }}>
                  {[
                    { label: 'Openness', val: viewingPersona.personality.openness, color: '#38BDF8' },
                    { label: 'Conscientious', val: viewingPersona.personality.conscientiousness, color: 'var(--accent-emerald)' },
                    { label: 'Extroversion', val: viewingPersona.personality.extroversion, color: '#F59E0B' },
                    { label: 'Agreeable', val: viewingPersona.personality.agreeableness, color: '#A855F7' },
                    { label: 'Neuroticism', val: viewingPersona.personality.neuroticism, color: '#EC4899' },
                  ].map((t) => (
                    <div key={t.label}>
                      <div style={{ fontSize: '0.78rem', fontWeight: 700, color: t.color }}>{t.val}</div>
                      <div style={{ height: '3px', background: 'var(--border-subtle)', borderRadius: '2px', overflow: 'hidden', margin: '3px 0' }}>
                        <div style={{ width: `${t.val}%`, height: '100%', background: t.color }} />
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{t.label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key Lifestyle Attributes */}
            {viewingPersona.detailed_attributes && Object.keys(viewingPersona.detailed_attributes).length > 0 && (
              <div style={{ background: 'var(--bg-secondary)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                <div
                  title="Lifestyle & routine snapshot"
                  style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-cyan)', letterSpacing: '0.04em', marginBottom: '8px' }}
                >
                  How they live day to day
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(160px, 100%), 1fr))', gap: '8px', fontSize: '0.78rem' }}>
                  {viewingPersona.detailed_attributes.commute_mode && (
                    <div><span style={{ color: 'var(--text-secondary)' }}>Commute: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.commute_mode}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.work_schedule && (
                    <div><span style={{ color: 'var(--text-secondary)' }}>Schedule: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.work_schedule}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.food_source && (
                    <div><span style={{ color: 'var(--text-secondary)' }}>Food: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.food_source}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.payment_method && (
                    <div><span style={{ color: 'var(--text-secondary)' }}>Payment: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.payment_method}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.communication_style && (
                    <div><span style={{ color: 'var(--text-secondary)' }}>Communication: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.communication_style}</span></div>
                  )}
                  {viewingPersona.detailed_attributes.hobbies && (
                    <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-secondary)' }}>Hobbies: </span><span style={{ color: 'var(--text-main)' }}>{viewingPersona.detailed_attributes.hobbies}</span></div>
                  )}
                </div>
              </div>
            )}

            {/* Behavioral Claims & Provenance */}
            <div>
              <div
                title="Behavioral claims & provenance — each claim is labeled by how it was derived"
                style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--accent-cyan)', letterSpacing: '0.04em', marginBottom: '8px' }}
              >
                What this persona claims — and how we know
              </div>
              {viewingPersona.attributes && viewingPersona.attributes.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {viewingPersona.attributes.map((attr: any, idx: number) => (
                    <div key={idx} style={{ background: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>
                          {attr.title}
                          <ProvenanceChip label={attr.provenance_class} />
                        </div>
                        {attr.category && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', flexShrink: 0 }}>{attr.category}</span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>{attr.description}</div>
                      {attr.evidence?.quote && (
                        <div style={{ marginTop: '6px', paddingLeft: '10px', borderLeft: '2px solid var(--accent-subtle)', fontSize: '0.74rem', color: 'var(--text-secondary)', fontStyle: 'italic', lineHeight: 1.45 }}>
                          “{attr.evidence.quote}”
                          {attr.evidence.source && (
                            <span style={{ display: 'block', marginTop: '2px', fontStyle: 'normal', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                              — {attr.evidence.source}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                /* Honest empty state — never fabricate claims. */
                <div style={{ background: 'var(--bg-secondary)', border: '1px dashed var(--border-subtle)', borderRadius: '8px', padding: '14px', fontSize: '0.8rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
                  No labelled claims recorded for this persona yet.
                </div>
              )}
            </div>
          </div>
        </div>
  );
};

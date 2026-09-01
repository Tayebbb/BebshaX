import React from 'react';

/** The two persona models in the app expose the same fact under different names:
 * the workflow `Persona` uses `grounding_ratio`, the library `SyntheticPersona`
 * uses `grounding_score`. `grounding_basis` is optional — the backend only sets
 * it when it wants to state that nothing was retrieved. */
export interface PersonaEvidenceFields {
  grounding_ratio?: number;
  grounding_score?: number;
  grounding_basis?: string;
  generation_model?: string;
  critic_notes?: string;
}

export const evidenceRatio = (p: PersonaEvidenceFields): number =>
  p.grounding_ratio ?? p.grounding_score ?? 0;

/** Evidence-backed only when a real grounding ratio survived generation and the
 * backend did not flag the persona as "no evidence retrieved". */
export const isEvidenceBacked = (p: PersonaEvidenceFields): boolean =>
  evidenceRatio(p) > 0 && p.grounding_basis !== 'no_evidence_retrieved';

/** Skeleton/template fallbacks are stamped by the backend generator. */
export const isTemplatePersona = (p: PersonaEvidenceFields): boolean =>
  typeof p.generation_model === 'string' && p.generation_model.includes('skeleton-fallback');

export const countEvidenceBacked = (personas: PersonaEvidenceFields[]): number =>
  personas.filter(isEvidenceBacked).length;

/** The single evidence badge used by step 2 and the persona library. A zero
 * ratio never renders as a success metric — it renders as plain prose. */
export const EvidenceBadge: React.FC<{ persona: PersonaEvidenceFields }> = ({ persona }) =>
  isEvidenceBacked(persona) ? (
    <span
      title="Share of this persona's claims traced to retrieved evidence"
      style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--accent-emerald)', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 8px', borderRadius: '6px' }}
    >
      {Math.round(evidenceRatio(persona) * 100)}% evidence-backed
    </span>
  ) : (
    <span
      title="No supporting evidence was retrieved for this persona — its details come from your description."
      style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--text-secondary)', background: 'var(--fill-soft)', border: '1px solid var(--border-subtle)', padding: '2px 8px', borderRadius: '6px' }}
    >
      Not evidence-backed — inferred from your description
    </span>
  );

/** The single template badge used by step 2 and the persona library. */
export const TemplateBadge: React.FC<{ persona: PersonaEvidenceFields }> = ({ persona }) => {
  if (!isTemplatePersona(persona)) return null;
  return (
    <div
      title={persona.critic_notes || 'Generated from a template because the model output could not be used.'}
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
  );
};

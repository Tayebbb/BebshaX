import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { Persona } from '../src/types';
import {
  EvidenceBadge,
  countEvidenceBacked,
  isEvidenceBacked,
  isSyntheticSourcePersona,
  type PersonaEvidenceFields,
} from '../src/utils/personaEvidence';
import { Step2Personas } from '../src/components/dashboard/views/workflow/Step2Personas';

afterEach(cleanup);

const mlMarkers: PersonaEvidenceFields[] = [
  { grounding_basis: 'synthetic_training_proxy' },
  { generation_model: 'bebshax-persona-ml/8e53bd7a' },
  { grounding_basis: 'synthetic_training_proxy', generation_model: 'bebshax-persona-ml/8e53bd7a' },
];

const sourcePersona = (overrides: Partial<Persona & PersonaEvidenceFields> = {}): Persona & PersonaEvidenceFields => ({
  id: 'synthetic-source-1',
  business_id: 'study-1',
  name: 'Synthetic source example',
  status: 'active',
  version: 1,
  archetype: 'Small business owner',
  tagline: 'Tracks costs before buying supplies',
  description: 'Runs a small shop and compares supplier prices weekly.',
  demographics: {
    age: 36,
    gender: 'Female',
    occupation: 'Shop owner',
    income_bracket: 'Middle',
    location: 'Dhaka',
    education: 'Secondary',
  },
  attributes: [],
  consistency_score: 0.9,
  grounding_ratio: 0,
  grounding_basis: 'synthetic_training_proxy',
  critic_notes: '',
  generation_model: 'bebshax-persona-ml/8e53bd7a',
  created_at: '2026-09-09T00:00:00Z',
  ...overrides,
});

const legacyPersona = (groundingRatio = 0): Persona & PersonaEvidenceFields => sourcePersona({
  id: 'legacy-persona-1',
  name: 'Legacy example',
  generation_model: 'llm7/codestral-latest',
  grounding_basis: undefined,
  grounding_ratio: groundingRatio,
});

const renderStep2 = (personas: Persona[], personaServedBy: string[] = []) => {
  const onNavigateToEvidence = vi.fn();
  render(
    <Step2Personas
      personas={personas}
      personaServedBy={personaServedBy}
      personaGenError={null}
      isGeneratingPersonas={false}
      suggestedRoles={[]}
      handleGeneratePersonas={vi.fn(async () => {})}
      handleStepChange={vi.fn()}
      handleRemovePersona={vi.fn()}
      personaModalTriggerRef={{ current: null }}
      setViewingPersona={vi.fn()}
      isStepUnlocked={() => true}
      onNavigateToEvidence={onNavigateToEvidence}
    />,
  );
  return onNavigateToEvidence;
};

describe('Synthetic source evidence classification', () => {
  it.each(mlMarkers)('recognizes either ML contract marker: %j', (marker) => {
    expect(isSyntheticSourcePersona(marker)).toBe(true);
  });

  it.each<PersonaEvidenceFields>([
    {},
    { grounding_basis: 'no_evidence_retrieved' },
    { generation_model: 'llm7/codestral-latest' },
    { generation_model: 'prefix/bebshax-persona-ml/8e53bd7a' },
  ])('does not classify a non-ML persona as a synthetic source: %j', (persona) => {
    expect(isSyntheticSourcePersona(persona)).toBe(false);
  });

  it.each(mlMarkers)('rejects accidental positive evidence metrics for ML: %j', (marker) => {
    expect(isEvidenceBacked({ ...marker, grounding_ratio: 0.85 })).toBe(false);
    expect(isEvidenceBacked({ ...marker, grounding_score: 0.85 })).toBe(false);
    expect(countEvidenceBacked([{ ...marker, grounding_ratio: 0.85 }, legacyPersona(0.62)])).toBe(1);
  });

  it('preserves legacy evidence and no-evidence classification', () => {
    expect(isEvidenceBacked({ grounding_ratio: 0.62 })).toBe(true);
    expect(isEvidenceBacked({ grounding_score: 0.62 })).toBe(true);
    expect(isEvidenceBacked({ grounding_ratio: 0.62, grounding_basis: 'no_evidence_retrieved' })).toBe(false);
    expect(isEvidenceBacked({})).toBe(false);
  });
});

describe('Synthetic source badge', () => {
  it.each(mlMarkers)('explains source selection without claiming observed evidence: %j', (marker) => {
    render(<EvidenceBadge persona={{ ...marker, grounding_ratio: 0.85 }} />);
    expect(screen.getByText('Synthetic source profile')).toHaveAttribute(
      'title',
      'A complete public synthetic source profile selected by the local persona model to match your brief. Its claims remain hypotheses, not observed customer evidence.',
    );
    expect(screen.queryByText(/evidence-backed|inferred from your description/i)).not.toBeInTheDocument();
  });

  it('keeps the non-ML inferred badge and tooltip', () => {
    render(<EvidenceBadge persona={legacyPersona()} />);
    expect(screen.getByText(/Not evidence-backed/)).toHaveAttribute(
      'title',
      'No supporting evidence was retrieved for this persona \u2014 its details come from your description.',
    );
  });

  it('keeps the non-ML evidence percentage', () => {
    render(<EvidenceBadge persona={legacyPersona(0.62)} />);
    expect(screen.getByText('62% evidence-backed')).toBeInTheDocument();
  });
});

describe('Step 2 synthetic source copy', () => {
  it.each([
    { name: 'model-only reload', marker: mlMarkers[1], routes: [] },
    { name: 'basis-only reload', marker: mlMarkers[0], routes: [] },
    { name: 'live batch', marker: mlMarkers[2], routes: ['bebshax-persona-ml/8e53bd7a'] },
  ])('explains ML selection for $name', ({ marker, routes }) => {
    const onNavigateToEvidence = renderStep2([
      sourcePersona({ grounding_basis: undefined, generation_model: '', ...marker, grounding_ratio: 0.85 }),
    ], routes);
    expect(screen.getByTestId('persona-served-by')).toHaveTextContent(
      'Complete public synthetic source profiles, selected by the local persona model to match your brief.',
    );
    expect(screen.getByText(/1 synthetic source profiles, not observed customers/)).toBeInTheDocument();
    expect(screen.getByText(/Synthetic profile claims remain hypotheses/)).toHaveTextContent(
      'source profiles never cite study evidence — regenerating does not change that. Evidence collected in the Evidence Laboratory is used by the interviews and the report, where it is cited per claim.',
    );
    expect(screen.queryByText(/Written by|regenerate and they will differ|inferred from your description|No research evidence has been gathered|then regenerate/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open Evidence Laboratory' }));
    expect(onNavigateToEvidence).toHaveBeenCalledOnce();
  });

  it.each([0, 0.62])('labels mixed batches without treating synthetic sources as evidence at legacy ratio %s', (ratio) => {
    renderStep2([sourcePersona({ grounding_ratio: 0.85 }), legacyPersona(ratio)]);
    expect(screen.getByTestId('persona-served-by')).toHaveTextContent('1 of 2 personas are complete public synthetic source profiles');
    expect(screen.getByTestId('persona-served-by')).toHaveTextContent('Other personas retain their own evidence labels.');
    expect(screen.getByText(`1 synthetic source profiles; ${ratio > 0 ? 1 : 0} of 2 personas cite retrieved evidence`)).toBeInTheDocument();
    expect(screen.getByText('Synthetic source profile')).toBeInTheDocument();
    expect(screen.getByText(ratio > 0 ? '62% evidence-backed' : /Not evidence-backed/)).toBeInTheDocument();
    expect(screen.queryByText(/Every persona above is inferred|The rest are inferred|then regenerate/)).not.toBeInTheDocument();
  });

  it('preserves non-ML provenance and research guidance', () => {
    renderStep2([legacyPersona()], ['llm7/codestral-latest']);
    expect(screen.getByTestId('persona-served-by')).toHaveTextContent(/Written by llm7\/codestral-latest.*regenerate and they will differ/);
    expect(screen.getByText(/Every persona above is inferred from your description alone/)).toHaveTextContent('then regenerate personas to have them cite that evidence.');
  });
});
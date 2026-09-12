import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { PersonaMemoryPanel } from '../src/components/dashboard/views/persona/PersonaMemoryPanel';
import { EvidenceClaimPeek } from '../src/components/dashboard/views/persona/EvidenceClaimPeek';
import { api } from '../src/services/api';
import type { ClaimDetail, MemoryItem, Study, SyntheticPersona } from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    getStudies: vi.fn(),
    getStudyPersonas: vi.fn(),
    getMarketSegments: vi.fn(),
    generateSyntheticPersonas: vi.fn(),
    regenerateStudyPersona: vi.fn(),
    getMemories: vi.fn(),
    getEvidenceClaimDetail: vi.fn(),
  },
}));

const study: Study = {
  id: 'studio-personas-study',
  title: 'Synthetic service research',
  type: 'interviews',
  goal: 'demand_validation',
  status: 'in_progress',
  step: 3,
  persona_count: 1,
  persona_ids: ['studio-persona'],
  suggested_roles: [],
  script_questions: [],
  created_at: '2026-09-10T10:00:00Z',
  updated_at: '2026-09-10T10:00:00Z',
};

const persona = {
  id: 'studio-persona',
  study_id: study.id,
  segment_id: 'studio-segment',
  segment_name: 'Independent professionals',
  generation_run_id: 'studio-generation',
  name: 'Alex Morgan',
  status: 'ready',
  version: 1,
  generation_model: 'synthetic-source-selector',
  archetype: 'Independent professional',
  demographics: {
    age: 34,
    occupation: 'Independent researcher',
    location: 'Portland, United States',
    income_or_budget: 'Unknown',
  },
  bio: 'A synthetic source profile for studying independent research workflows.',
  quote: 'I need the full source context before making a decision.',
  goals: ['Keep the complete research context'],
  needs: ['Traceable evidence'],
  pain_points: ['Missing source context'],
  behaviors: ['Checks source details'],
  preferences: [],
  motivations: [],
  objections: [],
  commercial_profile: {},
  technology_profile: {},
  evidence_citations: [],
  dataset_refs: [],
  grounding_score: 0,
  confidence: 0,
  validation_warnings: [],
  is_synthetic: true,
  created_at: '2026-09-10T10:00:00Z',
} satisfies SyntheticPersona;

const recordedPersonality: NonNullable<SyntheticPersona['personality']> = {
  openness: 0, conscientiousness: 40, extroversion: 50, agreeableness: 60, neuroticism: 70,
};

const memory: MemoryItem = {
  id: 'studio-memory', persona_id: persona.id, kind: 'reflection', source: 'interviewer',
  text: 'A researcher question retained as context, not a persona recollection. '.repeat(10).trim(),
  importance: 0, recency_weight: null, relevance_score: null, created_at: '2026-09-10T10:00:00Z',
};

const claim: ClaimDetail = {
  id: 'studio-claim', study_id: study.id, claim_text: 'Complete synthetic claim context. '.repeat(12).trim(),
  status: 'supported', category: 'pricing', confidence: 0,
  supporting_source_ids: ['studio-source'], supporting_chunk_ids: ['studio-chunk'], contradicting_source_ids: [],
  rationale: 'A recorded rationale that remains a research hypothesis.',
  supporting_sources: [{
    id: 'studio-source', study_id: study.id, source_type: 'report', title: 'Synthetic source record',
    url: 'https://example.test/synthetic-source', publisher: 'Synthetic fixture catalog',
    content: 'Complete source material. '.repeat(12).trim(), relevance_score: 0, status: 'processed',
  }],
  supporting_chunks: [{ id: 'studio-chunk', source_id: 'studio-source', chunk_index: 0, content: 'Complete supporting excerpt. '.repeat(12).trim() }],
  contradicting_sources: [],
};

function expectTokenSurfaces(root: HTMLElement): void {
  const elements = [root, ...root.querySelectorAll<HTMLElement>('[style]')];
  const hardcodedSurfaces = elements.map((element) => element.getAttribute('style') || '')
    .filter((style) => /(?:color|background|border|box-shadow)[^;]*(?:#[\da-f]{3,8}\b|rgba?\(|gradient|glow)/i.test(style));
  expect(hardcodedSurfaces).toEqual([]);
  const trackedText = elements.map((element) => element.style.letterSpacing)
    .filter((spacing) => spacing && !['0', '0px', 'normal'].includes(spacing));
  expect(trackedText).toEqual([]);
}

describe('Studio persona controls', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getStudies).mockResolvedValue([study]);
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [persona],
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0,
    });
    vi.mocked(api.getMarketSegments).mockResolvedValue([]);
    vi.mocked(api.getMemories).mockResolvedValue([]);
  });

  it('passes the auto-selected study when opening evidence from a fresh persona library', async () => {
    const onNavigateToEvidence = vi.fn();
    render(<PersonaLibraryView onNavigateToEvidence={onNavigateToEvidence} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/ }));
    fireEvent.click(screen.getByRole('button', { name: /View in Evidence Laboratory/ }));

    expect(onNavigateToEvidence).toHaveBeenCalledExactlyOnceWith(study.id);
  });

  it('passes the library-selected study to evidence when the shell still supplies another study', async () => {
    const nextStudy = { ...study, id: 'studio-personas-study-b', title: 'Second synthetic study' };
    const onNavigateToEvidence = vi.fn();
    vi.mocked(api.getStudies).mockResolvedValue([study, nextStudy]);
    vi.mocked(api.getStudyPersonas).mockImplementation(async (selectedStudyId) => ({
      personas: [{ ...persona, study_id: selectedStudyId }],
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0,
    }));
    render(<PersonaLibraryView studyId={study.id} onNavigateToEvidence={onNavigateToEvidence} />);
    await screen.findByRole('button', { name: 'Open profile' });

    fireEvent.change(screen.getByRole('combobox', { name: 'Active study' }), { target: { value: nextStudy.id } });
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: /Evidence/ }));
    fireEvent.click(screen.getByRole('button', { name: /View in Evidence Laboratory/ }));

    expect(screen.getByRole('combobox', { name: 'Active study' })).toHaveValue(nextStudy.id);
    expect(api.getStudyPersonas).toHaveBeenLastCalledWith(nextStudy.id);
    expect(onNavigateToEvidence).toHaveBeenCalledExactlyOnceWith(nextStudy.id);
  });

  it('does not offer evidence navigation when no study is selected', async () => {
    const onNavigateToEvidence = vi.fn();
    vi.mocked(api.getStudies).mockResolvedValue([]);
    await act(async () => {
      render(<PersonaLibraryView onNavigateToEvidence={onNavigateToEvidence} />);
    });

    expect(screen.getByRole('button', { name: 'Generate Personas' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: /View in Evidence Laboratory/ })).not.toBeInTheDocument();
    expect(api.getStudyPersonas).not.toHaveBeenCalled();
    expect(onNavigateToEvidence).not.toHaveBeenCalled();
  });

  it('disables generation while the primary persona read is pending', async () => {
    vi.mocked(api.getStudyPersonas).mockReturnValue(new Promise(() => {}));
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('combobox', { name: 'Active study' });

    expect(screen.getByRole('button', { name: 'Generate Personas' })).toBeDisabled();
    expect(api.generateSyntheticPersonas).not.toHaveBeenCalled();
  });

  it('exposes all eight inspector tabs with keyboard selection and a labelled panel', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));

    const tabList = screen.getByRole('tablist', { name: 'Persona details' });
    const tabs = within(tabList).getAllByRole('tab');
    expect(tabs).toHaveLength(8);
    const profileTab = within(tabList).getByRole('tab', { name: 'Persona Profile' });
    const personalityTab = within(tabList).getByRole('tab', { name: 'Personality (Big Five)' });
    expect(profileTab).toHaveAttribute('aria-selected', 'true');
    expect(tabs.filter((tab) => tab.tabIndex === 0)).toEqual([profileTab]);

    profileTab.focus();
    fireEvent.keyDown(profileTab, { key: 'ArrowRight' });

    expect(personalityTab).toHaveFocus();
    expect(personalityTab).toHaveAttribute('aria-selected', 'true');
    expect(profileTab).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByRole('tabpanel', { name: 'Personality (Big Five)' }))
      .toHaveAttribute('id', personalityTab.getAttribute('aria-controls'));

    fireEvent.keyDown(personalityTab, { key: 'Home' });
    expect(profileTab).toHaveFocus();
    expect(profileTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Persona Profile' }))
      .toHaveTextContent(persona.bio);
  });

  it('wraps inspector identity and actions instead of clipping a long name', async () => {
    const longName = 'Alexandra Morgan Independent Research and Accessibility Consultant';
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, name: longName }],
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));

    const dialog = screen.getByRole('dialog', { name: longName });
    const heading = within(dialog).getByRole('heading', { name: longName, level: 2 });
    expect(heading.closest('header')).toHaveStyle({ flexWrap: 'wrap', minWidth: '0' });
    expect(heading).toHaveStyle({ overflowWrap: 'anywhere' });
    expect(within(dialog).getByRole('button', { name: 'Regenerate' }).parentElement)
      .toHaveStyle({ flexWrap: 'wrap', minWidth: '0' });
  });

  it('lays out all inspector tabs in a wrapping grid with readable labels', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));

    const tabList = screen.getByRole('tablist', { name: 'Persona details' });
    expect(tabList).toHaveStyle({ display: 'grid' });
    expect(tabList.style.gridTemplateColumns).toContain('minmax(min(');
    for (const tab of within(tabList).getAllByRole('tab')) {
      expect(tab).toHaveStyle({ whiteSpace: 'normal', minWidth: '0' });
    }
  });

  it('provides one inspector close control that returns focus to the opener', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    const opener = await screen.findByRole('button', { name: 'Open profile' });
    opener.focus();
    fireEvent.click(opener);

    const dialog = screen.getByRole('dialog', { name: persona.name });
    const closeButtons = within(dialog).getAllByRole('button', { name: /^Close/ });
    expect(closeButtons).toHaveLength(1);
    fireEvent.click(closeButtons[0]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('keeps synthetic and cached provenance visible on every tab without a tagline', async () => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, data_source: 'cached' }],
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));

    const dialog = screen.getByRole('dialog', { name: persona.name });
    for (const tab of within(dialog).getAllByRole('tab')) {
      fireEvent.click(tab);
      expect(tab).toHaveAttribute('aria-selected', 'true');
      expect(within(dialog).getByText('Synthetic Persona')).toBeVisible();
      expect(within(dialog).getByText('CACHED')).toBeVisible();
    }
    await within(dialog).findByText(/No memories recorded yet/);
    expect(api.getMemories).toHaveBeenCalledWith(persona.id);
  });

  it('reaches every tab with arrows and wraps at both ends', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const tabs = screen.getAllByRole('tab');
    tabs[0].focus();
    for (let index = 1; index < tabs.length; index += 1) {
      fireEvent.keyDown(tabs[index - 1], { key: 'ArrowRight' });
      expect(tabs[index]).toHaveFocus();
      expect(tabs[index]).toHaveAttribute('aria-selected', 'true');
    }
    await screen.findByText(/No memories recorded yet/);

    fireEvent.keyDown(tabs[7], { key: 'ArrowRight' });
    expect(tabs[0]).toHaveFocus();
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' });
    expect(tabs[7]).toHaveFocus();
    await screen.findByText(/No memories recorded yet/);
    fireEvent.keyDown(tabs[7], { key: 'Home' });
    expect(tabs[0]).toHaveFocus();
    fireEvent.keyDown(tabs[0], { key: 'End' });
    expect(tabs[7]).toHaveFocus();
    await screen.findByText(/No memories recorded yet/);
  });

  it('retains Escape dismissal and focus restoration for the inspector', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    const opener = await screen.findByRole('button', { name: 'Open profile' });
    opener.focus();
    fireEvent.click(opener);
    await waitFor(() => expect(screen.getByRole('dialog')).toContainElement(document.activeElement as HTMLElement));

    fireEvent.keyDown(document.activeElement ?? document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('names the search and filters and restores results after an empty search', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });

    const search = screen.getByRole('searchbox', { name: 'Search personas' });
    expect(screen.getByRole('combobox', { name: 'Filter by segment' })).toHaveValue('all');
    expect(screen.getByRole('combobox', { name: 'Filter by status' })).toHaveValue('all');
    expect(screen.getByRole('combobox', { name: 'Filter by evidence grounding' })).toHaveValue('all');
    expect(search.style.outline).not.toBe('none');
    fireEvent.change(search, { target: { value: 'no matching synthetic profile' } });

    expect(screen.getByRole('status')).toHaveTextContent('No Personas Match Your Filter');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'JSON' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'CSV' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Clear All Filters' }));
    expect(search).toHaveValue('');
    expect(screen.getByRole('article', { name: `${persona.name} persona` })).toBeVisible();
  });

  it('uses a labelled range and native quota radios and retains settings after a generation failure', async () => {
    vi.mocked(api.generateSyntheticPersonas).mockRejectedValue(new Error('Source selection unavailable.'));
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });
    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    const dialog = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    const slider = within(dialog).getByRole('slider', { name: /Personas per Market Segment/ });
    expect(slider).toHaveAttribute('min', '1');
    expect(slider).toHaveAttribute('max', '6');
    fireEvent.change(slider, { target: { value: '6' } });
    const strategy = within(dialog).getByRole('group', { name: 'Quota Allocation Strategy' });
    const equal = within(strategy).getByRole('radio', { name: 'Equal Distribution' });
    expect(within(strategy).getByRole('radio', { name: 'Population-Weighted' })).toBeChecked();
    equal.focus();
    fireEvent.click(equal);
    expect(equal).toBeChecked();

    const form = within(dialog).getByRole('button', { name: 'Synthesize Personas' }).closest('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Source selection unavailable.');
    expect(api.generateSyntheticPersonas).toHaveBeenCalledTimes(1);
    expect(api.generateSyntheticPersonas).toHaveBeenCalledWith(study.id, {
      personas_per_segment: 6,
      distribution_strategy: 'equal',
    });
    expect(within(dialog).getByRole('slider', { name: /Personas per Market Segment/ })).toHaveValue('6');
    expect(within(dialog).getByRole('radio', { name: 'Equal Distribution' })).toBeChecked();
  });

  it('focuses the generation quota on open and restores the opener when dismissed', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });
    const opener = screen.getByRole('button', { name: 'Generate Personas' });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    const quota = within(dialog).getByRole('slider', { name: /Personas per Market Segment/ });

    await waitFor(() => expect(quota).toHaveFocus());
    expect(dialog).toHaveAttribute('tabindex', '-1');
    fireEvent.keyDown(quota, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('focuses the live pending generation status and loops Tab in both directions', async () => {
    vi.mocked(api.generateSyntheticPersonas).mockReturnValue(new Promise(() => {}));
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });
    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    const submit = screen.getByRole('button', { name: 'Synthesize Personas' });
    submit.focus();
    fireEvent.click(submit);
    const dialog = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    const pending = within(dialog).getByRole('status');

    await waitFor(() => expect(pending).toHaveFocus());
    expect(pending).toHaveAttribute('tabindex', '0');
    expect(pending).toHaveAttribute('aria-live', 'polite');
    for (const shiftKey of [false, true]) {
      expect(fireEvent.keyDown(pending, { key: 'Tab', shiftKey })).toBe(false);
      expect(pending).toHaveFocus();
    }
    fireEvent.keyDown(pending, { key: 'Escape' });
    fireEvent.click(dialog.parentElement!);
    expect(dialog).toBeVisible();
    expect(within(dialog).queryByRole('button', { name: /Cancel|Close/ })).not.toBeInTheDocument();
    expect(api.generateSyntheticPersonas).toHaveBeenCalledTimes(1);
  });

  it('focuses the generation error when a pending request fails', async () => {
    let rejectGeneration!: (error: Error) => void;
    vi.mocked(api.generateSyntheticPersonas).mockReturnValue(new Promise((_resolve, reject) => {
      rejectGeneration = reject;
    }));
    render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });
    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
    const dialog = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    await act(async () => rejectGeneration(new Error('Source selection is temporarily unavailable.')));
    const error = await within(dialog).findByRole('alert');

    await waitFor(() => expect(error).toHaveFocus());
    expect(error).toHaveTextContent('Source selection is temporarily unavailable.');
    expect(error).toHaveAttribute('tabindex', '-1');
    expect(dialog).toHaveAttribute('aria-busy', 'false');
    expect(within(dialog).getByRole('button', { name: 'Synthesize Personas' })).toBeEnabled();
  });

  it('provides a programmatically focusable inspector fallback for the shared dialog hook', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const dialog = screen.getByRole('dialog', { name: persona.name });

    expect(dialog).toHaveAttribute('tabindex', '-1');
    dialog.focus();
    expect(dialog).toHaveFocus();
  });

  it('announces regeneration failure inside the open inspector without losing its persona', async () => {
    vi.mocked(api.regenerateStudyPersona).mockRejectedValue(new Error('Source selection unavailable.'));
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const dialog = screen.getByRole('dialog', { name: persona.name });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Regenerate' }));

    expect(await within(dialog).findByRole('alert'))
      .toHaveTextContent('Regeneration failed: Source selection unavailable.');
    expect(screen.getAllByRole('alert')).toHaveLength(1);
    expect(within(dialog).getByRole('tabpanel')).toHaveTextContent(persona.bio);
    expect(within(dialog).getByRole('button', { name: 'Regenerate' })).toBeEnabled();
    expect(api.regenerateStudyPersona).toHaveBeenCalledWith(study.id, persona.id);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Dismiss error' }));
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('keeps pending generation open and ignores its failure after the study changes', async () => {
    let rejectGeneration!: (error: Error) => void;
    vi.mocked(api.generateSyntheticPersonas).mockImplementation(() => new Promise((_resolve, reject) => {
      rejectGeneration = reject;
    }));
    const { rerender } = render(<PersonaLibraryView studyId={study.id} />);
    await screen.findByRole('button', { name: 'Open profile' });
    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
    const dialog = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    expect(dialog).toHaveAttribute('aria-busy', 'true');
    expect(within(dialog).getByRole('status')).toHaveTextContent(/Generating personas/);
    expect(within(dialog).queryByRole('button', { name: /Close|Cancel/ })).not.toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    fireEvent.click(dialog.parentElement!);
    expect(dialog).toBeInTheDocument();
    expect(api.generateSyntheticPersonas).toHaveBeenCalledTimes(1);

    const nextPersona = { ...persona, id: 'next-persona', study_id: 'next-study', name: 'Sam Ellis' };
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [nextPersona], total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    rerender(<PersonaLibraryView studyId="next-study" />);
    await screen.findByRole('article', { name: 'Sam Ellis persona' });
    await act(async () => rejectGeneration(new Error('Stale generation failure.')));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText(/Stale generation failure/)).not.toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Sam Ellis persona' })).toBeVisible();
  });

  it('keeps the complete identity, long narrative, goals, and pain points readable', async () => {
    const fullQuote = 'The complete synthetic source context remains part of this profile. '.repeat(12).trim();
    const fullPersona: SyntheticPersona = {
      ...persona,
      quote: fullQuote,
      demographics: { ...persona.demographics, gender: 'Non-binary', education: 'Postgraduate research', income_or_budget: 'Income not reported by the source' },
      goals: [...persona.goals, 'Retain the second goal', 'Retain the final goal'],
      pain_points: [...persona.pain_points, 'Retain the final pain point'],
      behaviors: ['Reviews the full source record'],
      preferences: ['Complete context before conclusions'],
      motivations: ['Research traceability'],
    };
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [fullPersona], total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    const card = await screen.findByRole('article', { name: `${persona.name} persona` });
    const quote = within(card).getByText(`"${fullQuote}"`);
    expect(quote.style.overflow).not.toBe('hidden');
    expect(quote.style.getPropertyValue('-webkit-line-clamp')).toBe('');
    expect(within(card).getByText('Retain the final goal')).toBeVisible();
    expect(within(card).getByText('Retain the final pain point')).toBeVisible();
    fireEvent.click(within(card).getByRole('button', { name: 'Open profile' }));
    const panel = screen.getByRole('tabpanel', { name: 'Persona Profile' });
    expect(panel).toHaveTextContent(persona.bio!);
    expect(panel.textContent).toContain(fullQuote);
    for (const value of [...Object.values(fullPersona.demographics), ...fullPersona.behaviors, ...fullPersona.preferences, ...fullPersona.motivations]) {
      expect(panel).toHaveTextContent(String(value));
    }
  });

  it('displays recorded zero budget and confidence as zero rather than missing data', async () => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, commercial_profile: { monthly_budget_bdt: 0 }, evidence_citations: [{ claim_id: 'zero-confidence-claim', claim_text: 'A synthetic claim with no confidence assigned above zero.', confidence: 0 }] }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    const card = await screen.findByRole('article', { name: `${persona.name} persona` });
    expect(within(card).getByText('\u09F30/mo')).toBeVisible();
    fireEvent.click(within(card).getByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Commercial & WTP' }));
    expect(within(screen.getByRole('tabpanel')).getByText('\u09F30 / mo')).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: 'Evidence Citations (1)' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Confidence: 0%');
  });

  it('shows complete structured dataset values with their source and identifiers', async () => {
    const datasetValue = { range: [18, 95], description: 'A synthetic source constraint. '.repeat(16).trim() };
    const source = 'Reviewed public synthetic source catalog';
    const contentHash = 'abcdef0123456789'.repeat(4);
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, dataset_refs: [{ variable: 'source_constraints', value: datasetValue, source, dataset_id: 'synthetic-source-dataset', content_hash: contentHash }] }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Dataset Provenance' }));
    const panel = screen.getByRole('tabpanel');
    expect(panel.textContent).toContain(JSON.stringify(datasetValue, null, 2));
    expect(panel).toHaveTextContent(source);
    expect(panel).toHaveTextContent('synthetic-source-dataset');
    expect(panel).toHaveTextContent(contentHash);
    expect(panel).not.toHaveTextContent('[object Object]');
  });

  it.each([
    ['Dataset Provenance', 'No dataset provenance recorded for this persona.'],
    ['Technology Profile', 'No devices recorded.'],
  ])('announces missing data in the %s panel', async (tabName, message) => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: tabName }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getAllByRole('status').some((status) => status.textContent?.includes(message))).toBe(true);
    expect(within(panel).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the recorded warnings behind a needs-review status without declaring validation success', async () => {
    const warnings = ['Occupation was not provided by the synthetic source.', 'Income is unknown.'];
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, status: 'needs_review', validation_warnings: warnings }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const dialog = screen.getByRole('dialog', { name: persona.name });
    expect(within(dialog).getByText('Needs Review')).toBeVisible();
    expect(within(dialog).getByRole('heading', { name: 'Validation warnings', level: 3 })).toBeVisible();
    for (const warning of warnings) expect(within(dialog).getByText(warning)).toBeVisible();
    expect(within(dialog).queryByText('Complete')).not.toBeInTheDocument();
  });

  it('uses compact token-based surfaces throughout the library, inspector, and generation dialog', async () => {
    const styledPersona: SyntheticPersona = {
      ...persona, tagline: 'A complete synthetic research profile', data_source: 'cached',
      country_code: 'US', origin_country: 'United States',
      personality: recordedPersonality,
      technology_profile: { primary_devices: ['Laptop'], platforms: ['Research archive'] },
      detailed_attributes: { work_schedule: 'Flexible working hours', hobbies: 'Reading', communication_style: 'Direct', language_preferences: 'English', payment_method: 'Not stated' },
      evidence_citations: [{ claim_text: claim.claim_text, confidence: 0 }],
    };
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [styledPersona], total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    vi.mocked(api.getMemories).mockResolvedValue([memory]);
    const { container } = render(<PersonaLibraryView studyId={study.id} />);
    const card = await screen.findByRole('article', { name: `${persona.name} persona` });
    expect(screen.getByRole('heading', { name: 'Persona Library', level: 1 })).toHaveStyle({ fontSize: '1.5rem', letterSpacing: '0' });
    expect(within(card).getByRole('heading', { name: persona.name, level: 2 })).toBeVisible();
    expect(card).toHaveStyle({ borderRadius: '8px', minWidth: '0' });
    const openness = within(card).getByRole('img', { name: 'Openness 0 out of 100' });
    expect(within(openness).getByText('0')).toHaveStyle({ color: 'var(--text-main)' });
    expectTokenSurfaces(container);
    fireEvent.click(within(card).getByRole('button', { name: 'Open profile' }));
    const dialog = screen.getByRole('dialog', { name: persona.name });
    for (const tab of within(dialog).getAllByRole('tab')) {
      fireEvent.click(tab);
      if (tab.textContent === 'Memory') await within(dialog).findByText(memory.text);
      expectTokenSurfaces(dialog);
      expect(within(dialog).queryByRole('heading', { level: 4 })).not.toBeInTheDocument();
    }
    fireEvent.click(within(dialog).getByRole('button', { name: 'Close persona details' }));
    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    const generation = screen.getByRole('dialog', { name: 'Generate Synthetic Personas' });
    expect(generation).toHaveStyle({ borderRadius: '12px', overflowY: 'auto' });
    expectTokenSurfaces(generation);
  });

  it.each(['list read', 'generation', 'inspector regeneration', 'closed inspector regeneration'])(
    'keeps a neutral black surface for %s failures', async (failure) => {
      if (failure === 'list read') {
        vi.mocked(api.getStudyPersonas).mockRejectedValue(new Error('List unavailable.'));
      } else if (failure === 'generation') {
        vi.mocked(api.generateSyntheticPersonas).mockRejectedValue(new Error('Generation unavailable.'));
      } else {
        vi.mocked(api.regenerateStudyPersona).mockRejectedValue(new Error('Regeneration unavailable.'));
      }
      render(<PersonaLibraryView studyId={study.id} />);
      if (failure !== 'list read') {
        await screen.findByRole('button', { name: 'Open profile' });
        if (failure === 'generation') {
          fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
          fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
        } else {
          fireEvent.click(screen.getByRole('button', { name: 'Open profile' }));
          fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }));
        }
      }
      await screen.findByRole('alert');
      if (failure === 'closed inspector regeneration') {
        fireEvent.click(screen.getByRole('button', { name: 'Close persona details' }));
      }

      expect(screen.getByRole('alert')).toHaveStyle({ background: 'var(--bg-pure)' });
      if (failure !== 'list read') {
        const card = screen.getByRole('article', { name: `${persona.name} persona` });
        expect(within(card).getByText('Complete')).toBeVisible();
      }
    },
  );

  it('uses unboxed named sections for the inspector profile', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const panel = screen.getByRole('tabpanel', { name: 'Persona Profile' });

    for (const name of ['Identity', 'Consumer Bio & Direct Perspective', 'Core Goals', 'Needs', 'Pain Points & Anxieties', 'Buying Objections']) {
      const section = within(panel).getByRole('region', { name });
      expect(within(section).getByRole('heading', { name, level: 3 })).toBeVisible();
      expect(section.style.background).toBe('');
      expect(section.style.border).toBe('');
      expect(section).toHaveStyle({ minWidth: '0' });
    }
  });

  it('keeps card action dimensions stable and passes the selected study to each action', async () => {
    const onStartInterviewWithPersona = vi.fn();
    const onTestBehaviorWithPersona = vi.fn();
    const { container } = render(<PersonaLibraryView studyId={study.id} onStartInterviewWithPersona={onStartInterviewWithPersona} onTestBehaviorWithPersona={onTestBehaviorWithPersona} />);
    const card = await screen.findByRole('article', { name: `${persona.name} persona` });
    const interview = within(card).getByRole('button', { name: `Start an interview with ${persona.name}` });
    const behavioralTest = within(card).getByRole('button', { name: `Run a behavioral test with ${persona.name}` });

    for (const button of [interview, behavioralTest]) {
      expect(button).toHaveStyle({ width: '2.25rem', height: '2.25rem', flexShrink: '0' });
      button.focus();
      expect(button).toHaveFocus();
      fireEvent.mouseEnter(button);
      expectTokenSurfaces(container);
      fireEvent.mouseLeave(button);
      expectTokenSurfaces(container);
      fireEvent.click(button);
    }
    expect(onStartInterviewWithPersona).toHaveBeenCalledExactlyOnceWith(persona.id, study.id);
    expect(onTestBehaviorWithPersona).toHaveBeenCalledExactlyOnceWith(persona.id, study.id);
  });

  it('exposes recorded trait values as meters without inventing missing personality scores', async () => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, personality: recordedPersonality }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Personality (Big Five)' }));
    expect(screen.getAllByRole('meter')).toHaveLength(5);
    expect(screen.getByRole('meter', { name: 'Openness to Experience' })).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByRole('meter', { name: 'Openness to Experience' })).toHaveAttribute('aria-valuemax', '100');
    for (const [index, meter] of screen.getAllByRole('meter').entries()) {
      expect(meter).toHaveAttribute('aria-valuemin', '0');
      expect(meter).toHaveAttribute('aria-valuemax', '100');
      expect(meter).toHaveAttribute('aria-valuenow', String(Object.values(recordedPersonality)[index]));
    }
  });

  it.each([100, 37.5])('preserves the recorded personality score %s without rounding or rescaling', async (score) => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, personality: { ...recordedPersonality, openness: score } }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Personality (Big Five)' }));

    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByRole('meter', { name: 'Openness to Experience' }))
      .toHaveAttribute('aria-valuenow', String(score));
    expect(within(panel).getByText(`${score} / 100`)).toBeVisible();
  });

  it.each([NaN, Infinity, -Infinity, -1, 101])('does not turn invalid personality score %s into a measured trait', async (score) => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: [{ ...persona, personality: { ...recordedPersonality, openness: score } }],
      total: 1, represented_segments: 1, average_grounding_score: 0,
    });
    render(<PersonaLibraryView studyId={study.id} />);
    const card = await screen.findByRole('article', { name: `${persona.name} persona` });
    expect(within(card).queryByRole('img', { name: /^Openness / })).not.toBeInTheDocument();
    fireEvent.click(within(card).getByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Personality (Big Five)' }));

    const panel = screen.getByRole('tabpanel');
    expect(within(panel).queryByRole('meter', { name: 'Openness to Experience' })).not.toBeInTheDocument();
    expect(within(panel).getAllByRole('meter')).toHaveLength(4);
    expect(within(panel).getByText('Not measured')).toBeVisible();
  });

  it('keeps missing personality data unmeasured rather than inventing default scores', async () => {
    render(<PersonaLibraryView studyId={study.id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Personality (Big Five)' }));

    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.getByRole('tabpanel')).toHaveTextContent('No psychometric score data recorded for this persona.');
  });

  it('retains full researcher memory, zero importance, and stale-response protection in a token-based panel', async () => {
    let resolvePrevious!: (items: MemoryItem[]) => void;
    vi.mocked(api.getMemories).mockImplementationOnce(() => new Promise((resolve) => { resolvePrevious = resolve; }));
    const { container, rerender } = render(<PersonaMemoryPanel personaId="previous-persona" />);
    expect(screen.getByRole('status')).toHaveTextContent(/Loading memories/);
    vi.mocked(api.getMemories).mockResolvedValueOnce([memory]);
    rerender(<PersonaMemoryPanel personaId={persona.id} />);
    const text = await screen.findByText(memory.text);
    expect(text).toHaveStyle({ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap' });
    expect(screen.getByText('importance 0.00')).toBeVisible();
    expect(screen.getByText('asked by researcher')).toBeVisible();
    await act(async () => resolvePrevious([{ ...memory, id: 'stale-memory', text: 'Stale persona memory' }]));
    expect(screen.queryByText('Stale persona memory')).not.toBeInTheDocument();
    expectTokenSurfaces(container);
    expect(api.getMemories).toHaveBeenLastCalledWith(persona.id);
  });

  it('keeps claim text, rationale, sources, and supporting excerpts complete and theme-aware', async () => {
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValue(claim);
    const onClose = vi.fn();
    render(<EvidenceClaimPeek studyId={study.id} evidenceIds={[claim.id]} onClose={onClose} />);
    const region = screen.getByRole('region', { name: 'Cited evidence' });
    await within(region).findByText(claim.claim_text);
    expect(region).toHaveTextContent(claim.rationale!);
    expect(region.textContent).toContain(claim.supporting_sources[0].content);
    expect(region.textContent).toContain(claim.supporting_chunks[0].content);
    expect(within(region).getByRole('link', { name: 'Synthetic source record' }))
      .toHaveAttribute('href', 'https://example.test/synthetic-source');
    expect(region).toHaveTextContent('confidence 0%');
    expectTokenSurfaces(region);
    expect(api.getEvidenceClaimDetail).toHaveBeenCalledWith(study.id, claim.id);
    fireEvent.click(within(region).getByRole('button', { name: /Hide/ }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('separates supporting sources, contradicting sources, and excerpts with their complete provenance', async () => {
    const supportingSource = { ...claim.supporting_sources[0], content_hash: 'supporting-content-hash' };
    const contradictingSource = {
      ...supportingSource,
      id: 'contradicting-source',
      title: 'Conflicting source record',
      publisher: 'Conflicting fixture catalog',
      url: 'https://example.test/contradicting-source',
      content_hash: 'contradicting-content-hash',
      content: 'Complete contradicting source material. '.repeat(18).trim(),
    };
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValue({
      ...claim,
      supporting_sources: [supportingSource],
      contradicting_source_ids: [contradictingSource.id],
      contradicting_sources: [contradictingSource],
    });
    render(<EvidenceClaimPeek studyId={study.id} evidenceIds={[claim.id]} onClose={vi.fn()} />);
    const supporting = await screen.findByRole('list', { name: 'Supporting sources' });
    const contradicting = screen.getByRole('list', { name: 'Contradicting sources' });
    const excerpts = screen.getByRole('list', { name: 'Supporting excerpts' });

    for (const [group, source] of [[supporting, supportingSource], [contradicting, contradictingSource]] as const) {
      expect(within(group).getByRole('link', { name: source.title })).toHaveAttribute('href', source.url);
      expect(within(group).getByText(source.content)).toBeVisible();
      expect(group).toHaveTextContent(source.publisher);
      expect(group).toHaveTextContent(source.id);
      expect(group).toHaveTextContent(source.source_type);
      expect(group).toHaveTextContent(source.content_hash);
    }
    expect(supporting).not.toHaveTextContent(contradictingSource.content);
    expect(contradicting).not.toHaveTextContent(supportingSource.content);
    expect(within(excerpts).getByText(claim.supporting_chunks[0].content)).toBeVisible();
    expect(excerpts).toHaveTextContent(claim.supporting_chunks[0].source_id);
    expect(excerpts).toHaveTextContent(claim.supporting_chunks[0].id);
    expect(excerpts).toHaveTextContent('index 0');
    expect(screen.getByRole('region', { name: 'Cited evidence' })).toHaveTextContent('status supported');
  });

  it.each(['Contradicting sources', 'Supporting excerpts'])('does not report an empty trace when only %s are returned', async (groupName) => {
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValue({
      ...claim,
      supporting_sources: [],
      supporting_source_ids: [],
      supporting_chunks: groupName === 'Supporting excerpts' ? claim.supporting_chunks : [],
      supporting_chunk_ids: groupName === 'Supporting excerpts' ? claim.supporting_chunk_ids : [],
      contradicting_sources: groupName === 'Contradicting sources' ? claim.supporting_sources : [],
      contradicting_source_ids: groupName === 'Contradicting sources' ? claim.supporting_source_ids : [],
    });
    render(<EvidenceClaimPeek studyId={study.id} evidenceIds={[claim.id]} onClose={vi.fn()} />);
    await screen.findByText(claim.claim_text);

    expect(screen.queryByText('No source rows attached to this claim.')).not.toBeInTheDocument();
    expect(screen.getByRole('list', { name: groupName })).toBeVisible();
  });

  it('reports an empty trace when every returned source and excerpt collection is empty', async () => {
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValue({
      ...claim,
      supporting_sources: [], supporting_source_ids: [],
      supporting_chunks: [], supporting_chunk_ids: [],
      contradicting_sources: [], contradicting_source_ids: [],
    });
    render(<EvidenceClaimPeek studyId={study.id} evidenceIds={[claim.id]} onClose={vi.fn()} />);

    expect(await screen.findByText('No source rows attached to this claim.')).toBeVisible();
    expect(screen.queryByRole('list', { name: /Supporting|Contradicting/ })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Cited evidence' })).toHaveTextContent(claim.rationale!);
  });

  it('names a source link with its identifier when title and publisher are missing', async () => {
    vi.mocked(api.getEvidenceClaimDetail).mockResolvedValue({
      ...claim,
      supporting_sources: [{ ...claim.supporting_sources[0], title: '', publisher: '' }],
    });
    render(<EvidenceClaimPeek studyId={study.id} evidenceIds={[claim.id]} onClose={vi.fn()} />);

    const sources = await screen.findByRole('list', { name: 'Supporting sources' });
    expect(within(sources).getByRole('link', { name: claim.supporting_sources[0].id }))
      .toHaveAttribute('href', claim.supporting_sources[0].url);
  });
});
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import type { MarketSegment, SyntheticPersona } from '../src/types';

const requests = vi.hoisted(() => ({
  getStudies: vi.fn(),
  getStudyPersonas: vi.fn(),
  getMarketSegments: vi.fn(),
  listStudyPersonaRuns: vi.fn(),
  generateSyntheticPersonas: vi.fn(),
  regenerateStudyPersona: vi.fn(),
}));

vi.mock('../src/services/api', () => ({ api: requests }));

const persona: SyntheticPersona = {
  id: 'persona-a', study_id: 'study-a', name: 'Study A persona',
  status: 'ready', version: 1, generation_model: 'cpu-selector',
  archetype: 'Planner', demographics: {}, bio: 'Synthetic source profile', quote: '',
  goals: [], needs: [], pain_points: [], behaviors: [], preferences: [],
  motivations: [], objections: [], commercial_profile: {}, technology_profile: {},
  evidence_citations: [], dataset_refs: [], grounding_score: 0, confidence: 0,
  validation_warnings: [], is_synthetic: true, created_at: '2026-09-09T00:00:00Z',
};

describe('FE02 persona-library study ownership', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    requests.getStudies.mockResolvedValue([]);
    requests.getMarketSegments.mockResolvedValue([]);
    requests.listStudyPersonaRuns.mockResolvedValue({ runs: [] });
  });

  it('removes study A rows and exposes a partial error when study B personas fail', async () => {
    requests.getStudyPersonas
      .mockResolvedValueOnce({ personas: [persona] })
      .mockRejectedValueOnce(new Error('Study B unavailable'));
    const { rerender } = render(<PersonaLibraryView studyId="study-a" />);
    await screen.findByText('Study A persona');

    rerender(<PersonaLibraryView studyId="study-b" />);

    await waitFor(() => {
      expect(requests.getStudyPersonas).toHaveBeenCalledWith('study-b');
      expect(screen.queryByText('Study A persona')).not.toBeInTheDocument();
      expect(screen.getByRole('alert')).toHaveTextContent('Personas could not be loaded.');
    });
  });

  it('renders generated personas after the primary list read has failed', async () => {
    const generatedPersona = { ...persona, id: 'recovered-persona', name: 'Recovered persona' };
    requests.getStudyPersonas.mockRejectedValue(new Error('List unavailable'));
    requests.generateSyntheticPersonas.mockResolvedValue({ personas: [generatedPersona] });
    render(<PersonaLibraryView studyId="study-a" />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Personas could not be loaded.');

    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Recovered persona persona' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Generate Personas' })).toBeEnabled();
    expect(requests.generateSyntheticPersonas).toHaveBeenCalledExactlyOnceWith('study-a', {
      personas_per_segment: 2,
      distribution_strategy: 'population_weighted',
    });
  });

  it('keeps generated personas when the previous optional segment read finishes late', async () => {
    let resolveSegments!: (segments: MarketSegment[]) => void;
    requests.getMarketSegments.mockReturnValue(new Promise<MarketSegment[]>((resolve) => {
      resolveSegments = resolve;
    }));
    requests.getStudyPersonas.mockResolvedValue({ personas: [persona] });
    requests.generateSyntheticPersonas.mockResolvedValue({
      personas: [{ ...persona, id: 'generated-persona', name: 'Newly generated persona' }],
    });
    render(<PersonaLibraryView studyId="study-a" />);
    await screen.findByRole('article', { name: 'Study A persona persona' });

    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
    await screen.findByRole('article', { name: 'Newly generated persona persona' });
    await act(async () => resolveSegments([]));

    expect(screen.getByRole('article', { name: 'Newly generated persona persona' })).toBeVisible();
    expect(screen.queryByRole('article', { name: 'Study A persona persona' })).not.toBeInTheDocument();
  });

  it.each(['closed', 'another persona'])('does not reopen or replace the inspector when it is %s at regeneration completion', async (inspectorState) => {
    const anotherPersona = { ...persona, id: 'persona-b', name: 'Another persona' };
    const regeneratedPersona = { ...persona, name: 'Regenerated persona', version: 2 };
    let resolveRegeneration!: (result: SyntheticPersona) => void;
    requests.getStudyPersonas.mockResolvedValue({ personas: [persona, anotherPersona] });
    requests.regenerateStudyPersona.mockReturnValue(new Promise<SyntheticPersona>((resolve) => {
      resolveRegeneration = resolve;
    }));
    render(<PersonaLibraryView studyId="study-a" />);
    const originalCard = await screen.findByRole('article', { name: 'Study A persona persona' });
    fireEvent.click(within(originalCard).getByRole('button', { name: 'Open profile' }));
    const originalDialog = screen.getByRole('dialog', { name: persona.name });
    fireEvent.click(within(originalDialog).getByRole('button', { name: 'Regenerate' }));
    fireEvent.click(within(originalDialog).getByRole('button', { name: 'Close persona details' }));
    if (inspectorState === 'another persona') {
      fireEvent.click(within(screen.getByRole('article', { name: 'Another persona persona' }))
        .getByRole('button', { name: 'Open profile' }));
    }

    await act(async () => resolveRegeneration(regeneratedPersona));

    expect(screen.getByRole('article', { name: 'Regenerated persona persona' })).toBeVisible();
    expect(screen.queryByRole('dialog', { name: regeneratedPersona.name })).not.toBeInTheDocument();
    if (inspectorState === 'another persona') {
      expect(screen.getByRole('dialog', { name: anotherPersona.name })).toBeVisible();
    } else {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    }
  });

  it('updates the list and still-current inspector when regeneration succeeds', async () => {
    const updatedPersona = { ...persona, name: 'Updated current persona', version: 2 };
    requests.getStudyPersonas.mockResolvedValue({ personas: [persona] });
    requests.regenerateStudyPersona.mockResolvedValue(updatedPersona);
    render(<PersonaLibraryView studyId="study-a" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    fireEvent.click(within(screen.getByRole('dialog', { name: persona.name }))
      .getByRole('button', { name: 'Regenerate' }));

    expect(await screen.findByRole('dialog', { name: updatedPersona.name })).toBeVisible();
    expect(screen.getByRole('article', { name: 'Updated current persona persona' })).toBeVisible();
  });

  it.each([
    { operation: 'generation', navigation: 'study round trip' },
    { operation: 'regeneration', navigation: 'study round trip' },
    { operation: 'generation', navigation: 'owner remount' },
    { operation: 'regeneration', navigation: 'owner remount' },
  ])('ignores late $operation results after a $navigation creates a new request lifetime', async ({ operation, navigation }) => {
    let resolveMutation!: (result: SyntheticPersona | { personas: SyntheticPersona[] }) => void;
    const pendingMutation = new Promise<SyntheticPersona | { personas: SyntheticPersona[] }>((resolve) => {
      resolveMutation = resolve;
    });
    requests.getStudyPersonas.mockResolvedValue({ personas: [persona] });
    requests.generateSyntheticPersonas.mockReturnValue(pendingMutation);
    requests.regenerateStudyPersona.mockReturnValue(pendingMutation);
    const { rerender } = render(<PersonaLibraryView key="owner-a" studyId="study-a" />);
    await screen.findByRole('article', { name: 'Study A persona persona' });
    if (operation === 'generation') {
      fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
      fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));
    } else {
      fireEvent.click(screen.getByRole('button', { name: 'Open profile' }));
      fireEvent.click(screen.getByRole('button', { name: 'Regenerate' }));
    }

    if (navigation === 'study round trip') {
      requests.getStudyPersonas.mockResolvedValue({ personas: [{ ...persona, study_id: 'study-b', name: 'Study B persona' }] });
      rerender(<PersonaLibraryView key="owner-a" studyId="study-b" />);
      await screen.findByRole('article', { name: 'Study B persona persona' });
    }
    const currentPersona = { ...persona, name: 'Current request lifetime persona' };
    requests.getStudyPersonas.mockResolvedValue({ personas: [currentPersona] });
    rerender(<PersonaLibraryView key={navigation === 'owner remount' ? 'owner-b' : 'owner-a'} studyId="study-a" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Open profile' }));
    const latePersona = { ...persona, name: 'Previous request lifetime persona', version: 2 };
    await act(async () => resolveMutation(operation === 'generation' ? { personas: [latePersona] } : latePersona));

    expect(screen.getByRole('article', { name: 'Current request lifetime persona persona' })).toBeVisible();
    expect(screen.getByRole('dialog', { name: currentPersona.name })).toBeVisible();
    expect(screen.queryByText(latePersona.name)).not.toBeInTheDocument();
    if (operation === 'generation') {
      expect(requests.generateSyntheticPersonas).toHaveBeenCalledExactlyOnceWith('study-a', {
        personas_per_segment: 2,
        distribution_strategy: 'population_weighted',
      });
    } else {
      expect(requests.regenerateStudyPersona).toHaveBeenCalledExactlyOnceWith('study-a', persona.id);
    }
  });

  it('retains filters while accepting the complete generated persona list', async () => {
    const matchingPersona = { ...persona, id: 'matching-persona', name: 'Matching profile' };
    const otherPersona = { ...persona, id: 'other-persona', name: 'Other profile' };
    requests.getStudyPersonas.mockResolvedValue({ personas: [persona] });
    requests.generateSyntheticPersonas.mockResolvedValue({ personas: [matchingPersona, otherPersona] });
    render(<PersonaLibraryView studyId="study-a" />);
    await screen.findByRole('button', { name: 'Open profile' });
    const search = screen.getByRole('searchbox', { name: 'Search personas' });
    fireEvent.change(search, { target: { value: 'Matching' } });

    fireEvent.click(screen.getByRole('button', { name: 'Generate Personas' }));
    fireEvent.click(screen.getByRole('button', { name: 'Synthesize Personas' }));

    expect(await screen.findByRole('article', { name: 'Matching profile persona' })).toBeVisible();
    expect(search).toHaveValue('Matching');
    expect(screen.queryByRole('article', { name: 'Other profile persona' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
    expect(screen.getByRole('article', { name: 'Other profile persona' })).toBeVisible();
  });
});
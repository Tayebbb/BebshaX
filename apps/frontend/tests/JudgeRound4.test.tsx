import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudiesDashboardView } from '../src/components/dashboard/views/StudiesDashboardView';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { Step1Context } from '../src/components/dashboard/views/workflow/Step1Context';
import {
  EvidenceProbe,
  isResearchInFlight,
  nextEvidenceProbe,
} from '../src/components/dashboard/views/workflow/evidenceProbe';
import { EvidenceSummary, Study } from '../src/types';
import { api } from '../src/services/api';

vi.mock('../src/services/api', () => {
  const stub = {
    getStudies: vi.fn(),
    deleteStudy: vi.fn(),
    getStudyPersonas: vi.fn(),
    getMarketSegments: vi.fn(),
    listStudyPersonaRuns: vi.fn(),
    generateSyntheticPersonas: vi.fn(),
    regenerateStudyPersona: vi.fn(),
  };
  return { api: stub, default: stub };
});

beforeEach(() => {
  vi.clearAllMocks();
});

const study = (overrides: Partial<Study>): Study =>
  ({
    id: 'study_x',
    title: 'A Study',
    type: 'interviews',
    goal: 'demand_validation',
    prompt: 'Something',
    status: 'in_progress',
    persona_count: 0,
    persona_ids: [],
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    is_demo: false,
    step: 1,
    ...overrides,
  } as unknown as Study);

const summary = (overrides: Partial<EvidenceSummary>): EvidenceSummary =>
  ({
    study_id: 'study_x',
    research_status: 'idle',
    evidence_coverage: 0,
    supported_pct: 0,
    inferred_pct: 0,
    unsupported_pct: 0,
    supported_count: 0,
    inferred_count: 0,
    unsupported_count: 0,
    total_claims: 0,
    total_sources: 0,
    latest_run: null,
    ...overrides,
  } as EvidenceSummary);

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 1 — the in-flight indicator must use statuses the backend emits
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 1 — evidence probe speaks the backend status vocabulary', () => {
  // Written by ResearchEngineService.run_full_research (bebshax/research/service.py)
  // and documented on ResearchRuns.status (bebshax/db/models.py).
  const IN_FLIGHT = [
    'pending',
    'understanding_idea',
    'building_research_plan',
    'searching_evidence',
    'discovering_datasets',
    'evaluating_datasets',
    'importing_datasets',
    'extracting_evidence',
  ];

  it.each(IN_FLIGHT)('treats %s as a run still working', (status) => {
    expect(isResearchInFlight(status)).toBe(true);
    expect(nextEvidenceProbe(summary({ latest_run: { status } as any }), 8)).toEqual({
      state: 'searching',
    });
  });

  it.each(['completed', 'failed', 'idle'])('treats %s as not in flight', (status) => {
    expect(isResearchInFlight(status)).toBe(false);
  });

  it('reports a failed run as failed, never as "nothing found"', () => {
    const probe = nextEvidenceProbe(
      summary({
        research_status: 'failed',
        latest_run: { status: 'failed', error_message: 'provider quota exhausted' } as any,
      }),
      8,
    );

    expect(probe).toEqual({ state: 'failed', message: 'provider quota exhausted' });
    expect(probe.state).not.toBe('empty');
  });

  it('reports a completed run that found nothing as empty', () => {
    expect(nextEvidenceProbe(summary({ latest_run: { status: 'completed' } as any }), 8)).toEqual({
      state: 'empty',
    });
  });

  it('reports no run at all as not_run', () => {
    expect(nextEvidenceProbe(summary({ research_status: 'idle' }), 8)).toEqual({ state: 'not_run' });
  });

  it('reports found claims regardless of run status', () => {
    expect(
      nextEvidenceProbe(
        summary({ total_claims: 12, total_sources: 4, latest_run: { status: 'completed' } as any }),
        8,
      ),
    ).toEqual({ state: 'found', claims: 12, sources: 4 });
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 2 — the probe resolves when polling runs out
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 2 — the probe never stays pending forever', () => {
  it('resolves to a terminal timeout once the poll budget is spent', () => {
    const stillWorking = summary({ latest_run: { status: 'searching_evidence' } as any });

    expect(nextEvidenceProbe(stillWorking, 1)).toEqual({ state: 'searching' });
    expect(nextEvidenceProbe(stillWorking, 0)).toEqual({ state: 'timeout' });
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKERS 1 + 2 — what step 1 actually says
   ──────────────────────────────────────────────────────────────────────── */

describe('Step 1 status line', () => {
  const renderStep1 = (evidenceProbe: EvidenceProbe, onNavigateToEvidence = vi.fn()) =>
    render(
      <Step1Context
        copilotChatRef={{ current: null }}
        copilotMessages={[]}
        isCopilotTyping={false}
        showRoleSelection={false}
        handleApproveGoal={vi.fn()}
        handleSendCopilotMessage={vi.fn()}
        handleRetryCopilotMessage={vi.fn()}
        step1InputRef={{ current: null }}
        step1Prompt=""
        setStep1Prompt={vi.fn()}
        roleSelectionRef={{ current: null }}
        suggestedRoles={[]}
        isLoadingRoles={false}
        roleError={null}
        handleRetrySuggestedRoles={vi.fn()}
        isGeneratingPersonas={false}
        handleGeneratePersonas={vi.fn()}
        handleToggleRole={vi.fn()}
        handleIncrementRole={vi.fn()}
        handleDecrementRole={vi.fn()}
        evidenceProbe={evidenceProbe}
        onNavigateToEvidence={onNavigateToEvidence}
      />,
    );

  it('says the run failed — not that nothing was found', () => {
    renderStep1({ state: 'failed', message: 'provider quota exhausted' });

    expect(screen.getByText(/evidence research run failed/i)).toBeInTheDocument();
    expect(screen.getByText(/provider quota exhausted/i)).toBeInTheDocument();
    expect(screen.queryByText(/No evidence found/i)).toBeNull();
    // and it points somewhere the user can retry
    expect(screen.getByRole('button', { name: /Open Evidence Laboratory/i })).toBeInTheDocument();
  });

  it('says it is still searching when the poll budget ran out', () => {
    renderStep1({ state: 'timeout' });

    expect(screen.getByText(/Still searching — this can take a few minutes/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open Evidence Laboratory/i })).toBeInTheDocument();
    expect(screen.queryByText(/No evidence found/i)).toBeNull();
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 3 — the demo card only advertises what the study carries
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 3 — demo study blurb is data-driven', () => {
  it('promises only the report when the study has no personas or interviews', async () => {
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_done', title: 'Finished Demo', is_demo: true, status: 'completed', step: 5 }),
    ]);

    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('DEMO STUDY')).toBeInTheDocument());
    expect(screen.getByText('Sample study — explore a finished decision report')).toBeInTheDocument();
    expect(screen.queryByText(/pre-generated interviews/i)).toBeNull();
  });

  it('names personas when the study has them — and never advertises interviews (the list never serializes them)', async () => {
    (api.getStudies as any).mockResolvedValue([
      study({
        id: 'demo_done',
        title: 'Finished Demo',
        is_demo: true,
        status: 'completed',
        step: 5,
        persona_count: 3,
        // Even a hypothetical interviews payload must not be advertised: the
        // backend never puts interviews on the study list, so the clause was
        // dead in production and has been removed.
        interviews: [{ id: 'iv_1' }, { id: 'iv_2' }] as any,
      }),
    ]);

    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('DEMO STUDY')).toBeInTheDocument());
    expect(
      screen.getByText('Sample study — explore a finished decision report, 3 personas'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/2 interviews/)).toBeNull();
  });
});

/* ────────────────────────────────────────────────────────────────────────
   MAJOR 4 — the persona library never silently adopts the demo study
   ──────────────────────────────────────────────────────────────────────── */

describe('Major 4 — persona library study selection', () => {
  const stubPersonaCalls = () => {
    (api.getMarketSegments as any).mockResolvedValue([]);
    (api.listStudyPersonaRuns as any).mockResolvedValue({ runs: [] });
    (api.getStudyPersonas as any).mockResolvedValue({
      personas: [],
      total: 0,
      represented_segments: 0,
      average_grounding_score: 0,
    });
  };

  it('picks the user\'s most recent own study, not the demo', async () => {
    stubPersonaCalls();
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_1', title: 'Demo', is_demo: true, status: 'completed', step: 5 }),
      study({ id: 'own_old', title: 'Older Own', updated_at: '2026-01-01T00:00:00.000Z' }),
      study({ id: 'own_new', title: 'Newer Own', updated_at: '2026-06-01T00:00:00.000Z' }),
    ]);

    render(<PersonaLibraryView />);

    await waitFor(() => expect(api.getStudyPersonas as any).toHaveBeenCalledWith('own_new'));
    expect(api.getStudyPersonas).not.toHaveBeenCalledWith('demo_1');
    expect(api.getStudyPersonas).not.toHaveBeenCalledWith('default');
  });

  it('asks the user to pick when they only have the demo study', async () => {
    stubPersonaCalls();
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_1', title: 'Demo', is_demo: true, status: 'completed', step: 5 }),
    ]);

    render(<PersonaLibraryView />);

    await waitFor(() => expect(screen.getByText('Pick a study')).toBeInTheDocument());
    expect(api.getStudyPersonas).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Active study')).toBeInTheDocument();
  });

  it('explains the empty library when the user has no studies at all', async () => {
    stubPersonaCalls();
    (api.getStudies as any).mockResolvedValue([]);

    render(<PersonaLibraryView />);

    await waitFor(() => expect(screen.getByText('Pick a study')).toBeInTheDocument());
    expect(screen.getByText(/You have no studies yet/i)).toBeInTheDocument();
    expect(api.getStudyPersonas).not.toHaveBeenCalled();
  });

  it('honours an explicit study id from the route', async () => {
    stubPersonaCalls();
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_1', title: 'Demo', is_demo: true, status: 'completed', step: 5 }),
      study({ id: 'own_new', title: 'Newer Own' }),
    ]);

    render(<PersonaLibraryView studyId="own_new" />);

    await waitFor(() => expect(api.getStudyPersonas as any).toHaveBeenCalledWith('own_new'));
  });
});

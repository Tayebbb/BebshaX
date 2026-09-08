import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudiesDashboardView } from '../src/components/dashboard/views/StudiesDashboardView';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { StartInterviewModal } from '../src/components/dashboard/modals/StartInterviewModal';
import { Step1Context } from '../src/components/dashboard/views/workflow/Step1Context';
import { Step2Personas } from '../src/components/dashboard/views/workflow/Step2Personas';
import { Step4Interviews } from '../src/components/dashboard/views/workflow/Step4Interviews';
import { findExampleStudy, EXAMPLE_STUDY_STEP } from '../src/utils/exampleStudy';
import { EvidenceProbe } from '../src/components/dashboard/views/workflow/evidenceProbe';
import { Persona, Study, SyntheticPersona } from '../src/types';
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
    startPersonaInterview: vi.fn(),
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
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    is_demo: false,
    step: 1,
    ...overrides,
  } as unknown as Study);

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 1 — the "finished example study" affordance
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 1 — the example study affordance only points at a finished study', () => {
  it('prefers a completed demo over a newer unfinished one', () => {
    const picked = findExampleStudy([
      study({ id: 'demo_new', is_demo: true, status: 'in_progress', step: 1 }),
      study({ id: 'demo_done', is_demo: true, status: 'completed', step: 5 }),
    ]);

    expect(picked?.id).toBe('demo_done');
  });

  it('falls back to a demo parked on the report step', () => {
    const picked = findExampleStudy([
      study({ id: 'demo_mid', is_demo: true, status: 'in_progress', step: 2 }),
      study({ id: 'demo_report', is_demo: true, status: 'in_progress', step: 5 }),
    ]);

    expect(picked?.id).toBe('demo_report');
  });

  it('returns nothing when no demo is finished, so the affordance is not rendered', () => {
    const picked = findExampleStudy([
      study({ id: 'demo_a', is_demo: true, status: 'in_progress', step: 1 }),
      study({ id: 'demo_b', is_demo: true, status: 'draft', step: 2 }),
      study({ id: 'own', is_demo: false, status: 'completed', step: 5 }),
    ]);

    expect(picked).toBeNull();
  });

  it('renders no demo card when every seeded demo is unfinished', async () => {
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_a', title: 'Half Finished Demo', is_demo: true, status: 'in_progress', step: 2 }),
    ]);

    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={vi.fn()} />);

    await waitFor(() => expect(screen.getByText('Your Studies')).toBeInTheDocument());
    expect(screen.queryByText('DEMO STUDY')).toBeNull();
  });

  it('opens the finished demo on the report step', async () => {
    const onOpenStudy = vi.fn();
    (api.getStudies as any).mockResolvedValue([
      study({ id: 'demo_open', title: 'Unfinished Demo', is_demo: true, status: 'in_progress', step: 1 }),
      study({ id: 'demo_done', title: 'Finished Demo', is_demo: true, status: 'completed', step: 5 }),
    ]);

    render(<StudiesDashboardView onCreateStudy={vi.fn()} onOpenStudy={onOpenStudy} />);

    await waitFor(() => expect(screen.getByText('DEMO STUDY')).toBeInTheDocument());
    expect(screen.getByText('Finished Demo')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Explore Report'));
    expect(onOpenStudy).toHaveBeenCalledWith('demo_done', EXAMPLE_STUDY_STEP);
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 2 — the "Verified" badge
   ──────────────────────────────────────────────────────────────────────── */

const libraryPersona = (overrides: Partial<SyntheticPersona> = {}): SyntheticPersona =>
  ({
    id: 'per_lib_1',
    study_id: 'study_123',
    segment_id: 'seg_01',
    segment_name: 'Budget-Conscious Students',
    name: 'Nadia Rahman',
    status: 'ready',
    version: 1,
    generation_model: 'llm7/codestral-latest',
    archetype: 'Budget-Conscious Student Planner',
    demographics: { age: 21, occupation: 'Undergrad Student', location: 'Dhaka' },
    bio: 'Undergraduate managing a tight budget.',
    goals: [],
    needs: [],
    pain_points: [],
    behaviors: [],
    preferences: [],
    motivations: [],
    objections: [],
    commercial_profile: {},
    technology_profile: {},
    evidence_citations: [],
    dataset_refs: [],
    grounding_score: 0,
    confidence: 0.5,
    validation_warnings: [],
    is_synthetic: true,
    created_at: new Date().toISOString(),
    ...overrides,
  } as unknown as SyntheticPersona);

const renderLibrary = (personas: SyntheticPersona[]) => {
  (api.getStudies as any).mockResolvedValue([]);
  (api.getMarketSegments as any).mockResolvedValue([]);
  (api.listStudyPersonaRuns as any).mockResolvedValue({ runs: [] });
  (api.getStudyPersonas as any).mockResolvedValue({
    personas,
    total: personas.length,
    represented_segments: 1,
    average_grounding_score: 0,
  });
  return render(<PersonaLibraryView studyId="study_123" />);
};

describe('Blocker 2 — structural completeness is never called verification', () => {
  it('labels a passing persona "Complete", not "Verified"', async () => {
    renderLibrary([libraryPersona({ status: 'ready' })]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getAllByText('Complete').length).toBeGreaterThan(0);
    expect(screen.queryByText('Verified')).toBeNull();
    expect(screen.queryByText(/Verified & Ready/i)).toBeNull();
    expect(screen.queryByText(/Ready \/ Verified/i)).toBeNull();
  });

  it('counts them as complete profiles, not verified ones', async () => {
    renderLibrary([libraryPersona({ status: 'ready' })]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getByText('Complete profiles')).toBeInTheDocument();
  });

  it('still flags an incomplete persona for review', async () => {
    renderLibrary([libraryPersona({ status: 'needs_review' })]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getAllByText('Needs Review').length).toBeGreaterThan(0);
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 3 — fabricated persona details in the interview modal
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 3 — the interview modal invents nothing', () => {
  const renderModal = (persona: SyntheticPersona) =>
    render(
      <StartInterviewModal
        isOpen
        onClose={vi.fn()}
        persona={persona}
        studyId="study_123"
        onInterviewStarted={vi.fn()}
      />
    );

  it('omits budget and location entirely when the persona has neither', () => {
    renderModal(
      libraryPersona({
        demographics: { occupation: 'Undergrad Student' } as SyntheticPersona['demographics'],
        commercial_profile: {},
      })
    );

    expect(screen.getByText(/Undergrad Student/)).toBeInTheDocument();
    expect(screen.queryByText(/Budget:/)).toBeNull();
    expect(screen.queryByText(/300–600/)).toBeNull();
    expect(screen.queryByText(/Bangladesh/)).toBeNull();
  });

  it('never falls back to "Customer Archetype" when the occupation is missing', () => {
    renderModal(
      libraryPersona({
        archetype: 'Budget-Conscious Student Planner',
        demographics: {} as SyntheticPersona['demographics'],
        commercial_profile: {},
      })
    );

    expect(screen.queryByText(/Customer Archetype/)).toBeNull();
    expect(screen.getByText(/Budget-Conscious Student Planner/)).toBeInTheDocument();
  });

  it('shows budget and location when the persona really carries them', () => {
    renderModal(
      libraryPersona({
        demographics: { occupation: 'Undergrad Student', location: 'Dhaka' } as SyntheticPersona['demographics'],
        commercial_profile: { monthly_budget_bdt: 450 } as SyntheticPersona['commercial_profile'],
      })
    );

    expect(screen.getByText(/Dhaka/)).toBeInTheDocument();
    expect(screen.getByText(/Budget: ৳450\/mo/)).toBeInTheDocument();
  });

  it('uses the shared evidence predicate for its grounding claim', () => {
    renderModal(libraryPersona({ grounding_score: 0 }));

    expect(
      screen.getByText(/No supporting evidence was retrieved for this persona/i)
    ).toBeInTheDocument();
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 4 — the evidence attempt is visible in step 1
   ──────────────────────────────────────────────────────────────────────── */

describe('Blocker 4 — step 1 reports the evidence attempt', () => {
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
      />
    );

  it('says it is looking while the research run is in flight', () => {
    renderStep1({ state: 'searching' });

    expect(screen.getByText(/Looking for supporting evidence/i)).toBeInTheDocument();
  });

  it('reports the claim count once evidence is found', () => {
    renderStep1({ state: 'found', claims: 12, sources: 4 });

    expect(screen.getByText(/Found 12 supporting claims from 4 sources/i)).toBeInTheDocument();
  });

  it('says personas will be inferred when a run found nothing', () => {
    renderStep1({ state: 'empty' });

    expect(
      screen.getByText(/No evidence claims were extracted — personas will be inferred from your description/i)
    ).toBeInTheDocument();
  });

  it('names the live provider and says nothing was substituted when the search returned no sources', () => {
    renderStep1({ state: 'empty', noLiveEvidence: true, provider: 'WikipediaResearchProvider' });

    expect(screen.getByText(/live search \(WikipediaResearchProvider\) returned no sources/i)).toBeInTheDocument();
    expect(screen.getByText(/no claims were written in their place/i)).toBeInTheDocument();
  });

  it('shows the run error code when the evidence run failed', () => {
    renderStep1({ state: 'failed', message: 'Research planning needs the AI routing layer', errorCode: 'llm_unavailable' });

    expect(screen.getByText(/\[llm_unavailable\]/)).toBeInTheDocument();
    expect(screen.getByText(/nothing was substituted/i)).toBeInTheDocument();
  });

  it('says no run has happened yet and links to the evidence laboratory', () => {
    const onNavigateToEvidence = vi.fn();
    renderStep1({ state: 'not_run' }, onNavigateToEvidence);

    expect(screen.getByText(/No evidence run yet for this study/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Open Evidence Laboratory/i }));
    expect(onNavigateToEvidence).toHaveBeenCalled();
  });

  it('never claims evidence exists when the check failed', () => {
    renderStep1({ state: 'unavailable' });

    expect(screen.getByText(/Could not check for supporting evidence/i)).toBeInTheDocument();
    expect(screen.queryByText(/Found \d+ supporting claim/i)).toBeNull();
  });

  it('does not promise grounded personas in the step header', () => {
    renderStep1({ state: 'not_run' });

    expect(screen.queryByText(/build grounded personas/i)).toBeNull();
  });
});

/* ────────────────────────────────────────────────────────────────────────
   BLOCKER 5 — no copy asserts grounding the data does not support
   ──────────────────────────────────────────────────────────────────────── */

const workflowPersona = (overrides: Partial<Persona> = {}): Persona =>
  ({
    id: 'per_1',
    name: 'Nusrat Jahan',
    archetype: 'The Frugal Striver',
    tagline: 'Every taka counts',
    description: 'Third-year student.',
    grounding_ratio: 0,
    critic_notes: '',
    generation_model: 'llm7/codestral-latest',
    ...overrides,
  } as unknown as Persona);

describe('Blocker 5 — grounding is stated conditionally or not at all', () => {
  const renderStep2 = (personas: Persona[], isGeneratingPersonas = false) =>
    render(
      <Step2Personas
        personas={personas}
        personaGenError={null}
        isGeneratingPersonas={isGeneratingPersonas}
        suggestedRoles={[]}
        handleGeneratePersonas={vi.fn()}
        handleStepChange={vi.fn()}
        handleRemovePersona={vi.fn()}
        personaModalTriggerRef={{ current: null }}
        setViewingPersona={vi.fn()}
        isStepUnlocked={() => true}
        onNavigateToEvidence={vi.fn()}
      />
    );

  it('titles step 2 without asserting grounding', () => {
    renderStep2([workflowPersona()]);

    expect(screen.getByText('Study Personas')).toBeInTheDocument();
    expect(screen.queryByText(/Grounded Persona Library/i)).toBeNull();
  });

  it('does not claim grounded generation in the progress banner', () => {
    renderStep2([], true);

    expect(screen.getByText(/Generating personas/i)).toBeInTheDocument();
    expect(screen.queryByText(/Generating grounded personas/i)).toBeNull();
  });

  it('does not claim grounded personas in the empty state', () => {
    renderStep2([]);

    expect(screen.queryByText(/Generate grounded personas/i)).toBeNull();
  });

  it('always offers the evidence laboratory, including when personas are backed', () => {
    renderStep2([workflowPersona({ grounding_ratio: 0.7 })]);

    expect(screen.getByText(/1 of 1 personas cite retrieved evidence/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open Evidence Laboratory/i })).toBeInTheDocument();
  });

  it('does not claim grounded personas in the step 4 empty state', () => {
    render(
      <Step4Interviews
        personas={[]}
        isBatchRunning={false}
        handleRunBatchInterviews={vi.fn()}
        onCancelBatch={vi.fn()}
        isGeneratingReport={false}
        handleGenerateFinalReport={vi.fn()}
        handleStepChange={vi.fn()}
        interviewStatusMap={{}}
        activeInterviewPersonaId=""
        setActiveInterviewPersonaId={vi.fn()}
        setChatMessages={vi.fn()}
        setConversationId={vi.fn()}
        interviewChatRef={{ current: null }}
        chatMessages={[]}
        isSimulating={false}
        handleSendInterviewMessage={vi.fn()}
        userInputMessage=""
        setUserInputMessage={vi.fn()}
      />
    );

    expect(screen.getByText(/Generate personas in the Personas step first/i)).toBeInTheDocument();
    expect(screen.queryByText(/Generate grounded personas in the Personas step/i)).toBeNull();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { InterviewsView } from '../src/components/dashboard/views/InterviewsView';
import { Step3Script } from '../src/components/dashboard/views/workflow/Step3Script';
import { Step5Report } from '../src/components/dashboard/views/workflow/Step5Report';
import { Step2Personas } from '../src/components/dashboard/views/workflow/Step2Personas';
import { isEvidenceBacked, isTemplatePersona } from '../src/utils/personaEvidence';
import { api } from '../src/services/api';
import { Interview, Persona, StudyReport, SyntheticPersona } from '../src/types';

vi.mock('../src/services/api', () => {
  const stub = {
    getStudies: vi.fn(),
    getStudyPersonas: vi.fn(),
    getMarketSegments: vi.fn(),
    listStudyPersonaRuns: vi.fn(),
    generateSyntheticPersonas: vi.fn(),
    regenerateStudyPersona: vi.fn(),
    listStudyInterviews: vi.fn(),
    getStudyInterviewMetrics: vi.fn(),
    updateStudy: vi.fn(),
  };
  return { api: stub, default: stub };
});

const libraryPersona = (overrides: Partial<SyntheticPersona> = {}): SyntheticPersona =>
  ({
    id: 'per_lib_1',
    study_id: 'study_123',
    segment_id: 'seg_01',
    segment_name: 'Budget-Conscious Students',
    name: 'Nadia Rahman',
    status: 'ready',
    version: 1,
    generation_model: 'qwen3.5-grounded',
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

beforeEach(() => {
  vi.clearAllMocks();
});

describe('shared evidence predicate — exactly one definition', () => {
  it('reads both persona shapes through the same rule', () => {
    expect(isEvidenceBacked({ grounding_ratio: 0 })).toBe(false);
    expect(isEvidenceBacked({ grounding_score: 0 })).toBe(false);
    expect(isEvidenceBacked({ grounding_ratio: 0.5 })).toBe(true);
    expect(isEvidenceBacked({ grounding_score: 0.5 })).toBe(true);
    expect(isEvidenceBacked({ grounding_score: 0.5, grounding_basis: 'no_evidence_retrieved' })).toBe(false);
    expect(isTemplatePersona({ generation_model: 'bebshax/skeleton-fallback' })).toBe(true);
    expect(isTemplatePersona({ generation_model: 'qwen3.5-grounded' })).toBe(false);
  });

  it('is the same function the workflow step uses', async () => {
    render(
      <Step2Personas
        personas={[workflowPersona({ grounding_ratio: 0 })]}
        personaGenError={null}
        isGeneratingPersonas={false}
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
    expect(screen.getByText(/Not evidence-backed — inferred from your description/i)).toBeInTheDocument();
  });
});

describe('Blocker 1 — the persona library never renders 0% as a success metric', () => {
  it('shows the neutral chip instead of a grounding meter', async () => {
    renderLibrary([libraryPersona()]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getByText(/Not evidence-backed — inferred from your description/i)).toBeInTheDocument();
    expect(screen.queryByText('0%')).toBeNull();
    expect(screen.queryByText(/Avg\. Grounding Score/i)).toBeNull();
  });

  it('reports the aggregate as a count, not an average percentage', async () => {
    renderLibrary([libraryPersona(), libraryPersona({ id: 'per_lib_2', name: 'Tanvir Ahmed', grounding_score: 0.8 })]);

    await waitFor(() => expect(screen.getByText('Tanvir Ahmed')).toBeInTheDocument());

    expect(screen.getByText('Evidence-backed personas')).toBeInTheDocument();
    expect(screen.getByText(/80% evidence-backed/i)).toBeInTheDocument();
  });
});

describe('Blocker 2 — template personas are labelled in the library too', () => {
  it('renders the same template badge as step 2', async () => {
    renderLibrary([libraryPersona({ generation_model: 'bebshax/skeleton-fallback' })]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getByText(/Template — regenerate for full detail/i)).toBeInTheDocument();
  });

  it('leaves a genuinely generated persona unlabelled', async () => {
    renderLibrary([libraryPersona()]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.queryByText(/Template — regenerate for full detail/i)).toBeNull();
  });
});

describe('Major 7 — no invented budget', () => {
  it('says the budget is not stated instead of printing ৳350/mo', async () => {
    renderLibrary([libraryPersona()]);

    await waitFor(() => expect(screen.getByText('Nadia Rahman')).toBeInTheDocument());

    expect(screen.getByText('Budget not stated')).toBeInTheDocument();
    expect(screen.queryByText('৳350/mo')).toBeNull();
  });
});

describe('Blocker 3 — step 5 agrees with step 2', () => {
  const renderStep5 = (personas: Persona[], report: StudyReport | null) =>
    render(
      <Step5Report
        study={null}
        personas={personas}
        report={report}
        availableReports={report ? [report] : []}
        reportError={null}
        isGeneratingReport={false}
        copiedToast={false}
        copyReportMarkdown={vi.fn()}
        exportReportMarkdown={vi.fn()}
        handleGenerateFinalReport={vi.fn()}
        verificationAssumptions={[]}
      />
    );

  const bareReport: StudyReport = {
    executive_summary: 'Summary.',
    key_findings: [],
    recommendations: [],
    metrics: { total_claims: 0 },
  };

  it('counts evidence-backed personas instead of calling them all grounded', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0 }), workflowPersona({ id: 'per_2', grounding_ratio: 0.7 })], bareReport);

    expect(screen.queryByText('Grounded Personas')).toBeNull();
    expect(screen.getByText('Personas')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 evidence-backed')).toBeInTheDocument();
  });

  it('does not claim empirical research claims when none exist', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0 })], bareReport);

    expect(screen.queryByText(/empirical research claims/i)).toBeNull();
  });

  it('mentions research claims only when the report actually has them', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0.7 })], { ...bareReport, metrics: { total_claims: 12 } });

    expect(screen.getByText(/and empirical research claims/i)).toBeInTheDocument();
  });
});

describe('Blocker 4 — step 3 does not pass a template off as generated output', () => {
  const renderStep3 = (scriptGenerated: boolean) =>
    render(
      <Step3Script
        studyId="study_123"
        questions={['How do you currently handle tasks and challenges in this area?']}
        setQuestions={vi.fn()}
        newQuestion=""
        setNewQuestion={vi.fn()}
        handleGenerateScript={vi.fn()}
        isGeneratingScript={false}
        scriptError={null}
        scriptGenerated={scriptGenerated}
        handleStepChange={vi.fn()}
      />
    );

  it('labels the seeded questions as a starting template and offers "Generate"', () => {
    renderStep3(false);

    expect(screen.getByRole('button', { name: /^Generate Questions$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Regenerate Questions/i })).toBeNull();
    expect(screen.getByText(/Starting template/i)).toBeInTheDocument();
  });

  it('only says "Regenerate" after a real generation', () => {
    renderStep3(true);

    expect(screen.getByRole('button', { name: /Regenerate Questions/i })).toBeInTheDocument();
    expect(screen.queryByText(/Starting template/i)).toBeNull();
  });
});

describe('Blocker 5 — step 2 points at the evidence laboratory', () => {
  it('explains the missing evidence and links to the lab', () => {
    render(
      <Step2Personas
        personas={[workflowPersona({ grounding_ratio: 0 })]}
        personaGenError={null}
        isGeneratingPersonas={false}
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

    expect(screen.getByText(/No research evidence has been gathered for this study yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Open Evidence Laboratory/i })).toBeInTheDocument();
    expect(screen.getByText(/You can continue without it/i)).toBeInTheDocument();
  });

  it('stays quiet once at least one persona is evidence-backed', () => {
    render(
      <Step2Personas
        personas={[workflowPersona({ grounding_ratio: 0.4 })]}
        personaGenError={null}
        isGeneratingPersonas={false}
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

    expect(screen.queryByText(/No research evidence has been gathered/i)).toBeNull();
  });
});

describe('Major 6 — the interviews list can show failure', () => {
  const interview = (overrides: Partial<Interview>): Interview =>
    ({
      id: 'itv_1',
      study_id: 'study_123',
      persona_id: 'per_1',
      persona_version: 1,
      persona_name: 'Nadia Rahman',
      objective: 'problem_discovery',
      interview_type: 'adaptive',
      length_tier: 'standard',
      max_turns: 14,
      status: 'active',
      topics_explored: {},
      question_count: 0,
      turn_count: 3,
      created_at: new Date().toISOString(),
      ...overrides,
    } as Interview);

  const renderList = (interviews: Interview[]) => {
    (api.listStudyInterviews as any).mockResolvedValue({ interviews });
    (api.getStudyInterviewMetrics as any).mockResolvedValue({
      total_interviews: interviews.length,
      active_interviews: 0,
      completed_interviews: 0,
      total_insights_generated: 0,
    });
    return render(
      <InterviewsView studyId="study_123" onOpenInterview={vi.fn()} onNavigateToPersonas={vi.fn()} />
    );
  };

  it('renders a Failed badge rather than pulsing "Active" forever', async () => {
    renderList([interview({ status: 'failed' })]);

    await waitFor(() => expect(screen.getByText('Failed', { selector: 'span' })).toBeInTheDocument());
    expect(screen.queryByText('Active', { selector: 'span' })).toBeNull();
  });

  it('still shows a running interview as Active', async () => {
    renderList([interview({ status: 'active' })]);

    await waitFor(() => expect(screen.getByText('Active', { selector: 'span' })).toBeInTheDocument());
    expect(screen.queryByText('Failed', { selector: 'span' })).toBeNull();
  });
});

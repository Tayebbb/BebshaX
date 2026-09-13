import type { ComponentProps } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  const renderStep5 = (
    personas: Persona[],
    report: StudyReport | null,
    overrides: Partial<ComponentProps<typeof Step5Report>> = {},
  ) =>
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
        {...overrides}
      />
    );

  const bareReport: StudyReport = {
    executive_summary: 'Summary.',
    key_findings: [],
    recommendations: [],
    metrics: { total_claims: 0 },
  };

  it('uses the contrast-tested heading token for strategic recommendations', () => {
    renderStep5([], bareReport);
    expect(screen.getByRole('heading', { name: 'Strategic Recommendations' }))
      .toHaveStyle({ color: 'var(--text-main)' });
  });

  const recoveryCases = [
    { errorKind: 'loading', label: 'Reload saved reports' },
    { errorKind: 'generation', label: 'Retry report generation' },
    { errorKind: 'copy', label: 'Try copying again' },
  ] as const;

  it.each([false, true])('reloads saved reports after a loading failure without generating a report (readOnly=%s)', (isReadOnly) => {
    const onReloadReports = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const handleGenerateFinalReport = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const copyReportMarkdown = vi.fn();
    renderStep5([], null, {
      reportError: 'Saved reports could not be loaded.',
      reportErrorKind: 'loading',
      onReloadReports,
      handleGenerateFinalReport,
      copyReportMarkdown,
      isReadOnly,
    });

    const alert = within(screen.getByRole('alert'));
    expect(alert.getByText(/Saved reports unavailable:/)).toBeVisible();
    const retry = alert.getByRole('button', { name: 'Reload saved reports' });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);

    expect(onReloadReports).toHaveBeenCalledTimes(1);
    expect(handleGenerateFinalReport).not.toHaveBeenCalled();
    expect(copyReportMarkdown).not.toHaveBeenCalled();
  });

  it.each([false, true])('retries copying after a copy failure without generating a report (readOnly=%s)', (isReadOnly) => {
    const onReloadReports = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const handleGenerateFinalReport = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const copyReportMarkdown = vi.fn();
    renderStep5([], bareReport, {
      reportError: 'Clipboard permission was denied.',
      reportErrorKind: 'copy',
      onReloadReports,
      handleGenerateFinalReport,
      copyReportMarkdown,
      isReadOnly,
    });

    const alert = within(screen.getByRole('alert'));
    expect(alert.getByText(/Report copy failed:/)).toBeVisible();
    const retry = alert.getByRole('button', { name: 'Try copying again' });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);

    expect(copyReportMarkdown).toHaveBeenCalledTimes(1);
    expect(handleGenerateFinalReport).not.toHaveBeenCalled();
    expect(onReloadReports).not.toHaveBeenCalled();
  });

  it.each([
    { reportError: null, label: 'Generate Decision Report' },
    { reportError: 'Report generation failed.', label: 'Retry report generation' },
  ])('disables $label for read-only studies', ({ reportError, label }) => {
    const handleGenerateFinalReport = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    renderStep5([], null, {
      reportError,
      reportErrorKind: 'generation',
      handleGenerateFinalReport,
      isReadOnly: true,
    });

    const generate = screen.getByRole('button', { name: label });
    expect(generate).toBeDisabled();
    fireEvent.click(generate);

    expect(handleGenerateFinalReport).not.toHaveBeenCalled();
  });

  it.each(recoveryCases)('keeps the saved report visible after a $errorKind failure', ({ errorKind }) => {
    const savedReport = {
      ...bareReport,
      title: 'Saved customer research',
      version: 2,
      executive_summary: 'The previously saved summary remains available.',
      key_findings: ['Participants need clearer pricing.'],
      recommendations: ['Test the revised pricing page.'],
      limitations: 'Synthetic results require customer validation.',
    };
    renderStep5([], savedReport, {
      reportError: 'The latest action failed.',
      reportErrorKind: errorKind,
    });

    expect(screen.getByRole('alert')).toHaveTextContent('Your saved report is unchanged.');
    expect(screen.getByRole('heading', { name: savedReport.title })).toBeVisible();
    expect(screen.getByText(/Decision Report Ready.*Version 2/)).toBeVisible();
    expect(screen.getByText(savedReport.executive_summary)).toBeVisible();
    expect(screen.getByText(savedReport.key_findings[0])).toBeVisible();
    expect(screen.getByText(savedReport.recommendations[0])).toBeVisible();
    expect(screen.getByText(savedReport.limitations)).toBeVisible();
    expect(screen.queryByText('No report yet')).not.toBeInTheDocument();
  });

  it.each(recoveryCases.flatMap((recovery) => [
    { ...recovery, busyFlag: 'reportsLoading' as const },
    { ...recovery, busyFlag: 'isGeneratingReport' as const },
  ]))('blocks duplicate $errorKind recovery actions while $busyFlag is set', ({ errorKind, label, busyFlag }) => {
    const onReloadReports = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const handleGenerateFinalReport = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const copyReportMarkdown = vi.fn();
    renderStep5([], bareReport, {
      reportError: 'The latest action failed.',
      reportErrorKind: errorKind,
      onReloadReports,
      handleGenerateFinalReport,
      copyReportMarkdown,
      [busyFlag]: true,
    });

    const retry = within(screen.getByRole('alert')).getByRole('button', { name: label });
    expect(retry).toBeDisabled();
    fireEvent.click(retry);
    fireEvent.click(retry);

    expect(onReloadReports).not.toHaveBeenCalled();
    expect(handleGenerateFinalReport).not.toHaveBeenCalled();
    expect(copyReportMarkdown).not.toHaveBeenCalled();
  });

  it('counts evidence-backed personas instead of calling them all grounded', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0 }), workflowPersona({ id: 'per_2', grounding_ratio: 0.7 })], bareReport);

    expect(screen.queryByText('Grounded Personas')).toBeNull();
    expect(screen.getByText('Personas')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 evidence-backed')).toBeInTheDocument();
  });

  it('does not claim research claims when none exist', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0 })], bareReport);

    expect(screen.queryByText(/research claims?\./i)).toBeNull();
  });

  // The word "empirical" overstated LLM-extracted web claims, and the count was
  // hidden; the line now names the number it actually has.
  it('mentions the claim count only when the report actually has them', () => {
    renderStep5([workflowPersona({ grounding_ratio: 0.7 })], { ...bareReport, metrics: { total_claims: 12 } });

    expect(screen.getByText(/and 12 retrieved research claims/i)).toBeInTheDocument();
    expect(screen.queryByText(/empirical/i)).toBeNull();
  });
});

describe('Blocker 4 — step 3 does not pass a template off as generated output', () => {
  const renderStep3 = (scriptGenerated: boolean, questions: string[] = ['How do you currently handle tasks and challenges in this area?']) =>
    render(
      <Step3Script
        studyId="study_123"
        questions={questions}
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

  it('ships no seeded questionnaire: an empty script shows an honest empty state and offers "Generate"', () => {
    renderStep3(false, []);

    expect(screen.getByRole('button', { name: /^Generate Questions$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Regenerate Questions/i })).toBeNull();
    expect(screen.getByTestId('script-empty-state')).toBeInTheDocument();
    expect(screen.getByText(/does not ship a generic questionnaire/i)).toBeInTheDocument();
    expect(screen.queryByText(/How do you currently handle/i)).toBeNull();
  });

  it('labels researcher-typed questions as the researcher\u2019s own, never as generated', () => {
    renderStep3(false);

    expect(screen.getByText(/Your own questions/i)).toBeInTheDocument();
    expect(screen.queryByText(/Starting template/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /Regenerate Questions/i })).toBeNull();
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

describe('Major 6 — the interviews list only shows states the backend can produce', () => {
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

  // The interview engine only ever writes "active" or "completed" — there is no
  // code path that produces a failed conversation, so the list must not offer a
  // Failed filter or badge that can never render.
  it('offers no Failed status filter', async () => {
    renderList([interview({ status: 'active' })]);

    await waitFor(() => expect(screen.getByText('Active', { selector: 'span' })).toBeInTheDocument());
    expect(screen.queryByRole('option', { name: 'Failed' })).toBeNull();
  });

  it('shows a completed interview as Completed', async () => {
    renderList([interview({ status: 'completed' })]);

    await waitFor(() =>
      expect(screen.getByText('Completed', { selector: 'span' })).toBeInTheDocument()
    );
  });

  it('still shows a running interview as Active', async () => {
    renderList([interview({ status: 'active' })]);

    await waitFor(() => expect(screen.getByText('Active', { selector: 'span' })).toBeInTheDocument());
    expect(screen.queryByText('Failed', { selector: 'span' })).toBeNull();
  });
});

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';

describe('Study Design Copilot LLM Conversational Initiation & Persona Roles Generation', () => {
  beforeEach(() => {
    api.setMockMode(true);
    api.resetMockStore();
    vi.restoreAllMocks();
  });

  const renderWorkflow = (initialPrompt?: string) => {
    return render(
      <StudyWorkflowView
        studyId="tj6FY3cXDO8oxpuxeAMb"
        initialStep={1}
        initialType="interviews"
        initialPrompt={initialPrompt || ''}
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );
  };

  it('automatically triggers Copilot LLM analysis when initial prompt is provided', async () => {
    renderWorkflow(
      'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
    );

    // Initial user bubble should appear
    expect(
      screen.getByText(
        'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
      )
    ).toBeInTheDocument();

    // Assistant response explaining User Interviews and asking about target users
    await waitFor(() => {
      expect(
        screen.getByText(/Got it — you're exploring a(n)? education or student-focused product/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/What level of students/i)
      ).toBeInTheDocument();
    });
  });

  it('progresses through multi-turn dialogue, shows role selection, generates grounded personas in Step 2, and advances to Step 3', async () => {
    renderWorkflow(
      'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
    );

    await waitFor(() => {
      expect(
        screen.getByText(/Got it — you're exploring a(n)? education or student-focused product/i)
      ).toBeInTheDocument();
    });

    // Turn 2: User responds with location
    const input = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input, { target: { value: 'specifically for bangladeshi students' } });
    const sendBtn = screen.getByLabelText(/Send prompt/i);
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByText('specifically for bangladeshi students')).toBeInTheDocument();
      expect(
        screen.getByText(/Is this B2C for students directly/i)
      ).toBeInTheDocument();
    });

    // Turn 3: User responds with audience breadth
    const input2 = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input2, { target: { value: 'include Bangladeshi students broadly' } });
    const sendBtn2 = screen.getByLabelText(/Send prompt/i);
    fireEvent.click(sendBtn2);

    // Synthesized RESEARCH GOAL Card should appear
    await waitFor(() => {
      expect(screen.getByText('RESEARCH GOAL')).toBeInTheDocument();
      expect(
        screen.getByText(/Validate whether your education or student-focused product solves a genuine need/i)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument();
    });

    // Click Approve -> Opens SUGGESTED ROLES FOR YOUR STUDY
    const approveBtn = screen.getByRole('button', { name: /Approve/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/SUGGESTED ROLES FOR YOUR STUDY/i)).toBeInTheDocument();
      expect(screen.getAllByText(/UNIVERSITY STUDENT/i)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/COLLEGE APPLICANT/i)[0]).toBeInTheDocument();
      expect(screen.getAllByText(/BUSY HIGH SCHOOLER/i)[0]).toBeInTheDocument();
      expect(screen.getByText(/Persona Panel Configured/i)).toBeInTheDocument();
    });

    // Click Generate Personas -> Advances to Step 2 (Personas)
    const generateBtn = screen.getAllByRole('button', { name: /Generate Personas/i })[0];
    fireEvent.click(generateBtn);

    // Verify Step 2 Grounded Personas rendered
    await waitFor(
      () => {
        expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
        expect(screen.getByText('The Frugal Striver')).toBeInTheDocument();
        expect(screen.getByText('Farzana Rahman')).toBeInTheDocument();
        expect(screen.getByText('Tanjila Akter')).toBeInTheDocument();
        expect(screen.getByText('Total Personas')).toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // Click View Full Profile on Nusrat Jahan
    const viewProfileBtns = screen.getAllByText(/View full profile/i);
    fireEvent.click(viewProfileBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/What this persona claims — and how we know/i)).toBeInTheDocument();
    });

    // Close Modal
    const closeBtn = screen.getAllByRole('button').find((b) => b.querySelector('svg.lucide-x'));
    if (closeBtn) fireEvent.click(closeBtn);

    // Click Generate Script -> Advances to Step 3
    const generateScriptBtn = screen.getByRole('button', { name: /Generate Script/i });
    fireEvent.click(generateScriptBtn);

    await waitFor(() => {
      expect(screen.getByText('Interview Script & Probing Rules')).toBeInTheDocument();
    });
  });

  it('answers user prompt and generates custom personas for price tracker website business idea', async () => {
    renderWorkflow();

    // User types in bottom bar and submits
    const input = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input, { target: { value: 'want to start a price tracker website for 100 taka per month' } });
    const sendBtn = screen.getByLabelText(/Send prompt/i);
    fireEvent.click(sendBtn);

    // User message bubble appears
    expect(screen.getByText('want to start a price tracker website for 100 taka per month')).toBeInTheDocument();

    // Assistant answers and provides guidance
    await waitFor(() => {
      expect(screen.getByText(/Got it — you're exploring a(n)? (\*\*)?price tracker/i)).toBeInTheDocument();
      expect(screen.getByText(/Who are your primary users/i)).toBeInTheDocument();
    });

    // Provide audience clarification
    const input2 = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input2, { target: { value: 'bargain hunters in Bangladesh who shop on Daraz and Pickaboo' } });
    fireEvent.click(screen.getByLabelText(/Send prompt/i));

    await waitFor(() => {
      expect(screen.getByText(/What specific alert channels/i)).toBeInTheDocument();
    });

    // Provide pricing model confirmation
    const input3 = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input3, { target: { value: '100 taka per month subscription via bKash' } });
    fireEvent.click(screen.getByLabelText(/Send prompt/i));

    // Goal card appears
    await waitFor(() => {
      expect(screen.getByText('RESEARCH GOAL')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument();
    });

    // Approve goal
    const approveBtn = screen.getAllByRole('button', { name: /Approve/i })[0];
    fireEvent.click(approveBtn);

    // Verify suggested roles include price tracker roles
    await waitFor(() => {
      expect(screen.getByText(/SUGGESTED ROLES FOR YOUR STUDY/i)).toBeInTheDocument();
      expect(screen.getByText(/SMART BARGAIN HUNTER/i)).toBeInTheDocument();
    });

    // Generate Personas
    const generateBtn = screen.getAllByRole('button', { name: /Generate Personas/i })[0];
    fireEvent.click(generateBtn);

    // Verify Step 2 shows generated personas for price tracker
    await waitFor(
      () => {
        expect(screen.getByText('Samiul Alam')).toBeInTheDocument();
        expect(screen.getByText('The Strategic Deal Optimizer')).toBeInTheDocument();
        expect(screen.getByText('Nabila Khan')).toBeInTheDocument();
      },
      { timeout: 4000 }
    );
  });

  it('locks forward stepper navigation until prerequisites exist and explains what is needed', () => {
    render(
      <StudyWorkflowView
        studyId="study_gating_forward"
        initialStep={1}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    // No approved goal yet → Personas step is locked with an explanation
    const personasStep = screen.getByRole('button', { name: /Personas/i });
    expect(personasStep).toHaveAttribute('aria-disabled', 'true');
    expect(personasStep.getAttribute('title')).toMatch(/approve a research goal/i);
    fireEvent.click(personasStep);
    expect(screen.getByText('Design your user interviews')).toBeInTheDocument();

    // No personas yet → Interviews step is locked with an explanation
    const interviewsStep = screen.getByRole('button', { name: /Interviews/i });
    expect(interviewsStep).toHaveAttribute('aria-disabled', 'true');
    expect(interviewsStep.getAttribute('title')).toMatch(/generate personas first/i);
    fireEvent.click(interviewsStep);
    expect(screen.getByText('Design your user interviews')).toBeInTheDocument();
  });

  it('keeps backward stepper navigation free and never writes completed status without a report', async () => {
    const updateSpy = vi.spyOn(api, 'updateStudy').mockResolvedValue({} as any);
    render(
      <StudyWorkflowView
        studyId="study_gating_backward"
        initialStep={3}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    expect(screen.getByText('Interview Script & Probing Rules')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Context/i }));
    expect(screen.getByText('Design your user interviews')).toBeInTheDocument();

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'study_gating_backward',
        expect.objectContaining({ step: 1, status: 'in_progress' })
      );
    });
    expect(updateSpy).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ status: 'completed' })
    );
  });

  it('marks the study completed only when a report is actually generated', async () => {
    const updateSpy = vi.spyOn(api, 'updateStudy').mockResolvedValue({} as any);
    vi.spyOn(api, 'generateStudyReport').mockResolvedValue({
      id: 'rep_1',
      study_id: 'study_report_flow',
      title: 'Validation Report',
      executive_summary: 'Summary',
      key_findings: [],
      recommendations: [],
      version: 1,
    } as any);

    render(
      <StudyWorkflowView
        studyId="study_report_flow"
        initialStep={4}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    expect(updateSpy).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ status: 'completed' })
    );

    fireEvent.click(screen.getByRole('button', { name: /Generate Decision Report/i }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'study_report_flow',
        expect.objectContaining({ step: 5, status: 'completed' })
      );
    });
  });

  it('surfaces the report generation error on step 5 without claiming completion', async () => {
    const updateSpy = vi.spyOn(api, 'updateStudy').mockResolvedValue({} as any);
    vi.spyOn(api, 'generateStudyReport').mockRejectedValue(new Error('LLM route exhausted'));

    render(
      <StudyWorkflowView
        studyId="study_report_fail"
        initialStep={4}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Generate Decision Report/i }));

    await waitFor(() => {
      expect(screen.getByText(/Report generation failed: LLM route exhausted/i)).toBeInTheDocument();
    });
    expect(updateSpy).toHaveBeenCalledWith(
      'study_report_fail',
      expect.objectContaining({ step: 5, status: 'in_progress' })
    );
    expect(updateSpy).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ status: 'completed' })
    );
  });

  it('closes the persona detail modal on Escape', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    vi.spyOn(api, 'generateStudyPersonas').mockResolvedValue([
      {
        id: 'per_esc_1',
        name: 'Escape Tester',
        initials: 'ET',
        role_title: 'Primary User',
        description: 'A generated persona.',
      } as GeneratedPersonas[number],
    ]);

    render(
      <StudyWorkflowView
        studyId="study_modal_escape"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));
    await waitFor(() => {
      expect(screen.getByText('Escape Tester')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/View full profile/i));
    expect(screen.getByText(/What this persona claims — and how we know/i)).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByText(/What this persona claims — and how we know/i)).not.toBeInTheDocument();
    });
  });

  it('shows empty state on step 2 when no personas exist and not generating', () => {
    render(
      <StudyWorkflowView
        studyId="study_empty_state"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    expect(screen.getByText('No personas yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Generate Personas$/i })).toBeInTheDocument();
  });

  it('shows loading banner and skeleton cards while persona generation is in flight, then clears them', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    let resolveGeneration!: (personas: GeneratedPersonas) => void;
    vi.spyOn(api, 'generateStudyPersonas').mockReturnValue(
      new Promise<GeneratedPersonas>((resolve) => {
        resolveGeneration = resolve;
      })
    );

    const { container } = render(
      <StudyWorkflowView
        studyId="study_loading_state"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));

    // In-flight: status banner + shimmering skeleton cards, no empty state
    expect(screen.getByText(/Generating grounded personas/i)).toBeInTheDocument();
    expect(container.querySelectorAll('.bx-skeleton').length).toBeGreaterThan(0);
    expect(screen.queryByText('No personas yet')).not.toBeInTheDocument();

    resolveGeneration([
      {
        id: 'per_test_1',
        name: 'Test Persona',
        initials: 'TP',
        role_title: 'Primary User',
        description: 'A generated persona.',
      } as GeneratedPersonas[number],
    ]);

    // Resolved: skeletons and banner replaced by the persona card
    await waitFor(() => {
      expect(screen.getByText('Test Persona')).toBeInTheDocument();
      expect(screen.queryByText(/Generating grounded personas/i)).not.toBeInTheDocument();
      expect(container.querySelectorAll('.bx-skeleton').length).toBe(0);
    });
  });

  it('renders an honest empty state on step 5 when no report exists — never placeholder findings', () => {
    render(
      <StudyWorkflowView
        studyId="study_no_report_yet"
        initialStep={5}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    // Honest badge + empty state with a working generation CTA
    expect(screen.getByText('No report generated yet')).toBeInTheDocument();
    expect(screen.getByText('No report yet')).toBeInTheDocument();
    expect(screen.getByText(/Generate it from your study data/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Generate Decision Report/i })).toBeEnabled();

    // The previously fabricated report content must never render
    expect(screen.queryByText(/Personas indicate high adoption willingness/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Strong baseline demand exists/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Launch MVP with focused core features/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Executive Summary')).not.toBeInTheDocument();

    // Copy / Export are disabled and explain why
    const copyBtn = screen.getByRole('button', { name: /Copy/i });
    const exportBtn = screen.getByRole('button', { name: /Export Markdown/i });
    expect(copyBtn).toBeDisabled();
    expect(exportBtn).toBeDisabled();
    expect(copyBtn.getAttribute('title')).toMatch(/generate the report first/i);
    expect(exportBtn.getAttribute('title')).toMatch(/generate the report first/i);
  });

  it('generates the report from the step-5 empty state and renders only real report content', async () => {
    vi.spyOn(api, 'generateStudyReport').mockResolvedValue({
      id: 'rep_es_1',
      study_id: 'study_empty_state_report',
      title: 'Real Report',
      executive_summary: 'Real summary from study data.',
      key_findings: ['Real finding one.'],
      recommendations: ['Real recommendation one.'],
      version: 1,
    } as any);

    render(
      <StudyWorkflowView
        studyId="study_empty_state_report"
        initialStep={5}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Generate Decision Report/i }));

    await waitFor(() => {
      expect(screen.getByText('Real summary from study data.')).toBeInTheDocument();
      expect(screen.getByText('Real finding one.')).toBeInTheDocument();
      expect(screen.getByText('Real recommendation one.')).toBeInTheDocument();
    });
    expect(screen.queryByText('No report yet')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /Export Markdown/i })).toBeEnabled();
  });

  it('never invents demographics or claims in the persona modal — honest fallbacks only', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    vi.spyOn(api, 'generateStudyPersonas').mockResolvedValue([
      {
        id: 'per_sparse_1',
        name: 'Sparse Persona',
        initials: 'SP',
        role_title: 'Primary User',
        description: 'A generated persona with no verified claims yet.',
      } as GeneratedPersonas[number],
    ]);

    render(
      <StudyWorkflowView
        studyId="study_modal_honesty"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));
    await waitFor(() => {
      expect(screen.getByText('Sparse Persona')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/View full profile/i));

    // Missing demographics render "Not available" — one per missing field
    expect(screen.getAllByText('Not available')).toHaveLength(4);
    // Fabricated demographic defaults must never render
    expect(screen.queryByText('28')).not.toBeInTheDocument();
    expect(screen.queryByText('Dhaka, Bangladesh')).not.toBeInTheDocument();
    expect(screen.queryByText('Professional')).not.toBeInTheDocument();

    // Missing claims render the honest empty state, not invented claims
    expect(screen.getByText(/No verified claims recorded for this persona yet/i)).toBeInTheDocument();
    expect(screen.queryByText('Streamline daily tasks')).not.toBeInTheDocument();
    expect(screen.queryByText('High recurring cost')).not.toBeInTheDocument();

    // Focus moved into the dialog on open (focus trap entry point)
    const dialog = screen.getByRole('dialog');
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('renders the real-customer validation safeguard card with SYNTHETIC claims first, even when no report exists', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    vi.spyOn(api, 'generateStudyPersonas').mockResolvedValue([
      {
        id: 'per_prov_1',
        name: 'Provenance Persona',
        initials: 'PP',
        role_title: 'Primary User',
        description: 'A generated persona with mixed claim provenance.',
        detailed_attributes: {
          claim_provenance: {
            goals: [
              // INFERRED deliberately listed first: the card must re-rank SYNTHETIC ahead.
              { value: 'Wants offline sync for commutes', provenance: 'INFERRED' },
              { value: 'Pays 300 BDT monthly for study tools', provenance: 'SYNTHETIC' },
            ],
          },
        },
      } as unknown as GeneratedPersonas[number],
    ]);

    render(
      <StudyWorkflowView
        studyId="study_safeguard_card"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));
    await waitFor(() => {
      expect(screen.getByText('Provenance Persona')).toBeInTheDocument();
    });

    // Personas exist → the Report step is unlocked; navigate there via the stepper
    fireEvent.click(screen.getByRole('button', { name: /Report/i }));

    // No report was ever generated (report === null → honest empty state),
    // yet the safeguard card still renders with the least-grounded claims.
    await waitFor(() => {
      expect(screen.getByText('Validate with real customers next')).toBeInTheDocument();
    });
    expect(screen.getByText('No report yet')).toBeInTheDocument();
    expect(screen.getByText('Assumptions to verify in real interviews')).toBeInTheDocument();

    // Both claims listed, each with its provenance chip
    const syntheticItem = screen.getByText(/Pays 300 BDT monthly for study tools/).closest('li') as HTMLElement;
    const inferredItem = screen.getByText(/Wants offline sync for commutes/).closest('li') as HTMLElement;
    expect(syntheticItem).not.toBeNull();
    expect(inferredItem).not.toBeNull();
    expect(within(syntheticItem).getByText('SYNTHETIC')).toBeInTheDocument();
    expect(within(inferredItem).getByText('INFERRED')).toBeInTheDocument();

    // SYNTHETIC (no grounding at all) ranks ahead of INFERRED
    const items = Array.from(syntheticItem.parentElement!.children);
    expect(items.indexOf(syntheticItem)).toBeLessThan(items.indexOf(inferredItem));
  });

  // ── Regression tests for audit fixes ────────────────────────────────────

  it('Fix 2: restores persisted step from DB when initialStep is the default (1)', async () => {
    vi.spyOn(api, 'getStudy').mockResolvedValue({
      id: 'study_restore',
      step: 3,
      status: 'in_progress',
      type: 'interviews',
      title: 'Restored Study',
      copilot_messages: [],
      personas_data: [],
      suggested_roles: [],
      script_questions: [],
    } as any);

    render(
      <StudyWorkflowView
        studyId="study_restore"
        initialStep={1}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    // DB says step 3 and initialStep was default (1) → should restore to step 3
    await waitFor(() => {
      expect(screen.getByText('Interview Script & Probing Rules')).toBeInTheDocument();
    });
  });

  it('Fix 2: URL-provided step (initialStep > 1) takes precedence over DB step', async () => {
    vi.spyOn(api, 'getStudy').mockResolvedValue({
      id: 'study_url_step',
      step: 4,
      status: 'in_progress',
      type: 'interviews',
      title: 'URL Step Study',
      copilot_messages: [],
      personas_data: [],
      suggested_roles: [],
      script_questions: [],
    } as any);

    render(
      <StudyWorkflowView
        studyId="study_url_step"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    // URL says step 2 (initialStep=2 > 1) → should stay on step 2, not override to DB step 4
    await waitFor(() => {
      expect(screen.getByText('Grounded Persona Library')).toBeInTheDocument();
    });
  });

  it('Fix 7: copilot API failure shows honest error message — never fabricates a goal card', async () => {
    vi.spyOn(api, 'sendStudyCopilotMessage').mockRejectedValue(new Error('LLM providers busy'));

    render(
      <StudyWorkflowView
        studyId="study_copilot_error"
        initialStep={1}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/Type here to answer or give more context/i);
    fireEvent.change(input, { target: { value: 'my business idea' } });
    fireEvent.click(screen.getByLabelText(/Send prompt/i));

    await waitFor(() => {
      expect(screen.getByText(/I couldn't process that/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
    });

    // Must never invent a goal card
    expect(screen.queryByText('RESEARCH GOAL')).not.toBeInTheDocument();
    expect(screen.queryByText(/Understood! I've structured/i)).not.toBeInTheDocument();
  });

  it('Fix 14: Generate Script button in Step 2 is disabled when step 3 is not yet unlocked (no goal approved)', () => {
    render(
      <StudyWorkflowView
        studyId="study_step14"
        initialStep={2}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

    // No goal approved, no personas → step 3 locked → Generate Script must be disabled
    const generateScriptBtn = screen.getByRole('button', { name: /Generate Script/i });
    expect(generateScriptBtn).toBeDisabled();
    expect(generateScriptBtn).toHaveAttribute('title', 'Generate personas first');
  });
});

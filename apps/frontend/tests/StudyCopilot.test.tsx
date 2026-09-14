import { StrictMode, type ComponentProps } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { Step3Script } from '../src/components/dashboard/views/workflow/Step3Script';
import { api } from '../src/services/api';
import type { GeneratePersonasResult } from '../src/services/api';
import type { Study } from '../src/types';

/** The backend's generate-personas envelope around a list of personas. */
const envelope = (personas: GeneratePersonasResult['personas']): GeneratePersonasResult => ({
  personas,
  failed_roles: [],
  served_by: ['fake/test-model'],
});

/** Step 2 needs a business idea AND at least one selected role on the study:
 * with neither, generation is refused before any API call (no literal fallback;
 * an empty role list was always a server-side 400 — the mock hid it). Mirrors a
 * study saved in step 1; `awaitSeededStudy` resolves once the header shows it loaded. */
const seedStudyPrompt = (studyId: string, overrides: Partial<Study> = {}) =>
  vi.spyOn(api, 'getStudy').mockResolvedValue({
    id: studyId,
    title: 'Seeded Study',
    type: 'interviews',
    prompt: 'A study planner app for Bangladeshi university students at 250 BDT/month',
    status: 'in_progress',
    persona_count: 0,
    persona_ids: [],
    suggested_roles: [
      { id: 'role_1', role: 'PRIMARY USER', description: 'Core target user.', count: 1, selected: true },
    ],
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    step: 2,
    ...overrides,
  } as unknown as Study);
const awaitSeededStudy = () => screen.findByText('Seeded Study');

/** A study whose one persona has already completed an interview: the smallest
 * state from which a decision report may be generated (reports need findings,
 * never personas alone — live 2026-09-14). */
const seedInterviewedStudy = (studyId: string, overrides: Partial<Study> = {}) => {
  const persona = {
    id: `per_${studyId}`, name: 'Interviewed Persona', initials: 'IP', role_title: 'Primary User', description: 'Answered five questions.',
  } as GeneratePersonasResult['personas'][number];
  seedStudyPrompt(studyId, {
    personas_data: [persona], persona_ids: [persona.id], persona_count: 1, step: 4,
    script_questions: ['How do you plan your week today?'], ...overrides,
  });
  vi.spyOn(api, 'listStudyInterviews').mockResolvedValue({
    interviews: [{ id: `iv_${studyId}`, study_id: studyId, persona_id: persona.id, status: 'completed', turn_count: 10, created_at: '2026-01-02T00:00:00.000Z' }],
    total: 1,
  });
  vi.spyOn(api, 'getConversation').mockResolvedValue(null);
  return persona;
};

describe('Step 3 mobile layout', () => {
  const renderStep3 = (overrides: Partial<ComponentProps<typeof Step3Script>> = {}) => {
    const props: ComponentProps<typeof Step3Script> = {
      questions: [],
      setQuestions: vi.fn(),
      newQuestion: '',
      setNewQuestion: vi.fn(),
      handleGenerateScript: vi.fn().mockResolvedValue(undefined),
      isGeneratingScript: false,
      scriptError: null,
      handleStepChange: vi.fn(),
      ...overrides,
    };
    return { ...render(<Step3Script {...props} />), props };
  };

  it.each([
    { state: 'empty', overrides: {}, generationLabel: 'Generate Questions' },
    {
      state: 'generated',
      overrides: { scriptGenerated: true, questions: ['How do you solve this today?'] },
      generationLabel: 'Regenerate Questions',
    },
    { state: 'generating', overrides: { isGeneratingScript: true }, generationLabel: 'Generating...' },
    {
      state: 'read-only',
      overrides: { isReadOnly: true, scriptGenerated: true },
      generationLabel: 'Regenerate Questions',
    },
  ])('allows the header and actions to wrap in the $state state', ({ overrides, generationLabel }) => {
    renderStep3(overrides);

    const titleColumn = screen.getByRole('heading', { name: 'Interview Script & Probing Rules' }).parentElement;
    const generationButton = screen.getByRole('button', { name: generationLabel });
    const approvalButton = screen.getByRole('button', { name: 'Approve Script & Start Interviews' });

    expect(titleColumn?.parentElement).toHaveStyle({ flexWrap: 'wrap', gap: '16px', minWidth: 0 });
    expect(titleColumn).toHaveStyle({ flex: '1 1 320px', minWidth: 0, maxWidth: '100%' });
    expect(generationButton.parentElement).toBe(approvalButton.parentElement);
    expect(generationButton.parentElement).toHaveStyle({ flexWrap: 'wrap', gap: '10px', minWidth: 0, maxWidth: '100%' });
    for (const button of [generationButton, approvalButton]) {
      expect(button).toHaveStyle({ minHeight: '44px', maxWidth: '100%', whiteSpace: 'nowrap' });
    }
  });

  it('shows a compact interview action while retaining approval intent and navigation', () => {
    const { props } = renderStep3({ questions: ['How do you solve this today?'] });
    const approvalButton = screen.getByRole('button', { name: 'Approve Script & Start Interviews' });

    expect(approvalButton).toHaveTextContent(/^Start interviews$/);
    expect(approvalButton).toHaveAttribute('aria-label', 'Approve Script & Start Interviews');
    fireEvent.click(approvalButton);
    expect(props.handleStepChange).toHaveBeenCalledWith(4);
  });

  it('keeps interviews unreachable until the script has at least one filled question', () => {
    // Live 2026-09-14: an empty script could be "approved", marking step 3 done and
    // leading to a batch the server refuses (script_required).
    const empty = renderStep3();
    const approval = screen.getByRole('button', { name: 'Approve Script & Start Interviews' });
    expect(approval).toBeDisabled();
    expect(approval).toHaveAttribute('title', 'Add at least one question first');
    fireEvent.click(approval);
    expect(empty.props.handleStepChange).not.toHaveBeenCalled();
    empty.unmount();

    renderStep3({ questions: ['How do you solve this today?', '   '] });
    expect(screen.getByRole('button', { name: 'Approve Script & Start Interviews' })).toBeDisabled();
  });

  it('wraps a full generation error and keeps retry reachable', () => {
    const scriptError = `Provider unavailable: ${'LongProviderDiagnostic'.repeat(12)}`;
    const { props } = renderStep3({ scriptError });
    const alert = screen.getByRole('alert');
    const message = within(alert).getByText(`Question generation failed: ${scriptError}`);
    const retryButton = within(alert).getByRole('button', { name: 'Retry' });

    expect(alert).toHaveStyle({ flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' });
    expect(message).toHaveStyle({ minWidth: 0, overflowWrap: 'anywhere' });
    expect(retryButton).toHaveStyle({ minHeight: '44px' });
    fireEvent.click(retryButton);
    expect(props.handleGenerateScript).toHaveBeenCalledTimes(1);
  });

  it.each([
    { scriptSource: 'fallback_static' as const, scriptError: null, role: 'status', token: 'warn' },
    { scriptSource: null, scriptError: 'Provider unavailable', role: 'alert', token: 'error' },
  ])('uses the semantic $token tokens for script notices', ({ scriptSource, scriptError, role, token }) => {
    renderStep3({ scriptSource, scriptError });
    const notice = screen.getByRole(role);

    expect(notice.style.background).toBe(`var(--status-${token}-bg)`);
    expect(notice.style.border).toBe(`1px solid var(--status-${token}-border)`);
    expect(notice.style.color).toBe(`var(--status-${token}-text)`);
  });

  it('wraps generation progress while keeping generation disabled and announced as busy', () => {
    const { props } = renderStep3({ isGeneratingScript: true });
    const progress = screen.getByRole('status');
    const generationButton = screen.getByRole('button', { name: 'Generating...' });

    expect(progress).toHaveStyle({ flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' });
    expect(progress).toHaveTextContent('Writing interview questions from your study context');
    expect(generationButton).toBeDisabled();
    expect(generationButton).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(generationButton);
    expect(props.handleGenerateScript).not.toHaveBeenCalled();
  });

  it('keeps complete generated questions in shrinkable, named editable inputs', () => {
    const question = 'Describe your current process, its constraints, and the evidence behind each decision. '.repeat(12).trim();
    const nextQuestion = 'What would you change?';
    const { props } = renderStep3({ questions: [question, nextQuestion], scriptGenerated: true });
    const questionInput = screen.getByRole('textbox', { name: 'Question 1' });

    expect(questionInput.tagName).toBe('INPUT');
    expect(questionInput).toHaveValue(question);
    expect(questionInput).toBeEnabled();
    expect(questionInput).toHaveStyle({ minWidth: 0, maxWidth: '100%' });
    const editedQuestion = `${question} Include your most recent example.`;
    fireEvent.change(questionInput, { target: { value: editedQuestion } });
    expect(props.setQuestions).toHaveBeenCalledWith([editedQuestion, nextQuestion]);
  });

  it('names each delete control and removes only the selected question', () => {
    const retainedQuestion = 'Describe your complete experience without leaving out any constraints.';
    const { props } = renderStep3({ questions: [retainedQuestion, 'A question to remove'] });
    const deleteButton = screen.getByRole('button', { name: 'Delete question 2' });

    expect(deleteButton).toHaveAttribute('title', 'Delete question 2');
    expect(deleteButton).toHaveStyle({ minWidth: '44px', minHeight: '44px' });
    fireEvent.click(deleteButton);
    expect(props.setQuestions).toHaveBeenCalledWith([retainedQuestion]);
  });

  it('wraps the labeled add-question row and appends the complete new question', () => {
    const question = 'Describe a specific example and all relevant constraints. '.repeat(12).trim();
    const { props } = renderStep3({ questions: ['Existing question'], newQuestion: question });
    const newQuestionInput = screen.getByRole('textbox', { name: 'New interview question' });
    const addButton = screen.getByRole('button', { name: 'Add Question' });

    expect(newQuestionInput).toHaveValue(question);
    expect(newQuestionInput).toHaveStyle({ minWidth: 0, maxWidth: '100%' });
    expect(newQuestionInput.parentElement).toHaveStyle({ flexWrap: 'wrap', minWidth: 0, maxWidth: '100%' });
    expect(addButton).toHaveStyle({ minHeight: '44px', maxWidth: '100%' });
    fireEvent.click(addButton);
    expect(props.setQuestions).toHaveBeenCalledWith(['Existing question', question]);
    expect(props.setNewQuestion).toHaveBeenCalledWith('');
  });

  it('keeps named editing controls disabled for read-only scripts without blocking navigation', () => {
    const { props } = renderStep3({
      questions: ['A complete saved question'],
      scriptGenerated: true,
      scriptError: 'Provider unavailable',
      isReadOnly: true,
    });

    for (const input of screen.getAllByRole('textbox')) {
      expect(input).toBeDisabled();
    }
    for (const name of ['Regenerate Questions', 'Retry', 'Delete question 1', 'Add Question']) {
      const button = screen.getByRole('button', { name });
      expect(button).toBeDisabled();
      fireEvent.click(button);
    }
    expect(props.setQuestions).not.toHaveBeenCalled();
    expect(props.setNewQuestion).not.toHaveBeenCalled();
    expect(props.handleGenerateScript).not.toHaveBeenCalled();

    const approvalButton = screen.getByRole('button', { name: 'Approve Script & Start Interviews' });
    expect(approvalButton).toBeEnabled();
    fireEvent.click(approvalButton);
    expect(props.handleStepChange).toHaveBeenCalledWith(4);
  });
});

describe('Study Design Copilot LLM Conversational Initiation & Persona Roles Generation', () => {
  beforeEach(async () => {
    api.setMockMode(true);
    // resetMockStore defers the store reset behind a dynamic import — not awaiting
    // it lets the previous test's data leak into this one under parallel load.
    await api.resetMockStore();
    vi.restoreAllMocks();
    for (const id of ['tj6FY3cXDO8oxpuxeAMb', 'study_gating_forward', 'study_gating_backward', 'study_report_flow', 'study_report_fail', 'study_empty_state', 'study_no_report_yet', 'study_empty_state_report', 'study_copilot_error', 'study_step14']) {
      await api.createStudy({ id, title: 'Saved test study', type: 'interviews' });
    }
  });

  const renderWorkflow = async (initialPrompt?: string) => {
    const view = render(
      <StudyWorkflowView
        studyId="tj6FY3cXDO8oxpuxeAMb"
        initialStep={1}
        initialType="interviews"
        initialPrompt={initialPrompt || ''}
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );
    await screen.findByText('Saved test study');
    return view;
  };

  it('automatically triggers Copilot LLM analysis when initial prompt is provided', async () => {
    await renderWorkflow(
      'i want to make a study planner ai website for student and basic plan will cost 250 taaka per month'
    );

    // Initial user bubble should appear
    expect(
      await screen.findByText(
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

  it('announces the conversation and keeps user text readable on the accent surface', async () => {
    const prompt = 'A study planner for university students';
    await renderWorkflow(prompt);
    await screen.findByText(/What level of students/i);

    const conversation = screen.getByRole('log', { name: 'Study conversation' });
    expect(conversation).toHaveAttribute('aria-live', 'polite');
    const userMessage = within(conversation).getByRole('article', { name: 'Your message' });
    expect(userMessage).toHaveTextContent(prompt);
    expect(userMessage.style.color).toBe('var(--text-on-accent)');
    expect(within(conversation).getByRole('article', { name: 'Research copilot message' }))
      .toHaveTextContent(/What level of students/i);
  });

  it('starts the initial coffee copilot turn under Strict Mode with the browser scheduler', async () => {
    const prompt = 'I want to open a coffee shop for university students in Dhaka.';
    const study: Study = {
      id: 'study_strict_coffee',
      title: 'Coffee study',
      type: 'interviews',
      prompt,
      status: 'in_progress',
      step: 1,
      persona_count: 0,
      persona_ids: [],
      copilot_messages: [],
      created_at: '2026-09-09T10:00:00Z',
      updated_at: '2026-09-09T10:00:00Z',
    };
    vi.spyOn(api, 'getStudy').mockResolvedValue(study);
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable in this fixture'));
    const updateStudy = vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    type CopilotResponse = Awaited<ReturnType<typeof api.sendStudyCopilotMessage>>;
    let resolveCopilot!: (response: CopilotResponse) => void;
    const sendCopilot = vi.spyOn(api, 'sendStudyCopilotMessage').mockReturnValue(
      new Promise<CopilotResponse>((resolve) => { resolveCopilot = resolve; })
    );
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', false);
    try {
      root.render(
        <StrictMode>
          <StudyWorkflowView
            studyId={study.id}
            initialStep={1}
            initialType="interviews"
            initialPrompt={prompt}
            onExit={vi.fn()}
            onStepChange={vi.fn()}
          />
        </StrictMode>
      );

      expect(await screen.findByText(prompt)).toBeInTheDocument();
      await waitFor(() => expect(sendCopilot).toHaveBeenCalledTimes(1));
      expect(sendCopilot).toHaveBeenCalledWith([{ role: 'user', content: prompt }], 'interviews', study.id);
      expect(await screen.findByText('Synthesizing market context & assumptions...')).toBeInTheDocument();

      await act(async () => {
        resolveCopilot({
          reply: 'Which students would visit your coffee shop?',
          is_ready_for_approval: false,
          research_goal_card: null,
          suggested_roles: [],
          suggested_study_type: 'interviews',
          served_by: 'test/synthetic-fixture',
        });
      });

      expect(screen.getAllByText(prompt)).toHaveLength(1);
      expect(screen.getAllByText('Which students would visit your coffee shop?')).toHaveLength(1);
        expect(screen.queryByText('Synthesizing market context & assumptions...')).not.toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toBeEnabled();
      expect(sendCopilot).toHaveBeenCalledTimes(1);
      expect(updateStudy).toHaveBeenLastCalledWith(study.id, {
        copilot_messages: [
          expect.objectContaining({ role: 'user', content: prompt }),
          expect.objectContaining({ role: 'assistant', content: 'Which students would visit your coffee shop?' }),
        ],
      });
    } finally {
      act(() => root.unmount());
      container.remove();
      vi.unstubAllGlobals();
    }
  });

  it('progresses through multi-turn dialogue, shows role selection, generates grounded personas in Step 2, and advances to Step 3', async () => {
    await renderWorkflow(
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
      // The drawer must not claim a configured, evidence-grounded panel
      // before any persona exists.
      expect(screen.getByText(/Panel not created yet/i)).toBeInTheDocument();
      expect(screen.queryByText(/Grounded in empirical evidence/i)).toBeNull();
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
    await renderWorkflow();

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

  it('locks forward stepper navigation until prerequisites exist and explains what is needed', async () => {
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
    const personasStep = await screen.findByRole('button', { name: /Personas/i });
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

    expect(await screen.findByText('Interview Script & Probing Rules')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Context/i }));
    expect(screen.getByText('Design your user interviews')).toBeInTheDocument();

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'study_gating_backward',
        expect.objectContaining({ step: 1 })
      );
    });
    expect(updateSpy).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ status: 'completed' })
    );
  });

  it('displays the generated report while leaving completion status to the server', async () => {
    seedInterviewedStudy('study_report_flow');
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

    const generate = await screen.findByRole('button', { name: /Generate Decision Report/i });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'study_report_flow',
        expect.objectContaining({ step: 5 })
      );
    });
    expect(await screen.findByText('Validation Report')).toBeInTheDocument();
    expect(updateSpy.mock.calls.every(([, updates]) => !('status' in updates))).toBe(true);
  });

  it('surfaces the report generation error on step 5 without claiming completion', async () => {
    seedInterviewedStudy('study_report_fail');
    const updateSpy = vi.spyOn(api, 'updateStudy').mockResolvedValue({} as any);
    const generateReport = vi.spyOn(api, 'generateStudyReport')
      .mockRejectedValueOnce(new Error('LLM route exhausted'))
      .mockResolvedValueOnce({
        id: 'report_retry',
        title: 'Recovered research report',
        executive_summary: 'A synthesis of synthetic interview responses.',
        key_findings: [],
        recommendations: [],
        version: 1,
      });

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

    const generate = await screen.findByRole('button', { name: /Generate Decision Report/i });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);

    await waitFor(() => {
      expect(screen.getByText(/Report generation failed: LLM route exhausted/i)).toBeInTheDocument();
    });
    expect(updateSpy).toHaveBeenCalledWith(
      'study_report_fail',
      expect.objectContaining({ step: 5 })
    );
    expect(updateSpy).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ status: 'completed' })
    );

    fireEvent.click(screen.getByRole('button', { name: 'Retry report generation' }));
    expect(await screen.findByText('Recovered research report')).toBeInTheDocument();
    expect(generateReport).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Report generation failed:/i)).not.toBeInTheDocument();
  });

  it('closes the persona detail modal on Escape', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    seedStudyPrompt('study_modal_escape');
    vi.spyOn(api, 'generateStudyPersonasDetailed').mockResolvedValue(envelope([
      {
        id: 'per_esc_1',
        name: 'Escape Tester',
        initials: 'ET',
        role_title: 'Primary User',
        description: 'A generated persona.',
      } as GeneratedPersonas[number],
    ]));

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

    await awaitSeededStudy();
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

  it.each([false, true])('names persona removal controls and tooltips when read-only is %s', async (isReadOnly) => {
    const persona = {
      id: 'persona_removal_label', name: 'Synthetic Office Manager',
      initials: 'SO', role_title: 'Office Manager', description: 'Synthetic fixture.',
    } as GeneratePersonasResult['personas'][number];
    seedStudyPrompt('tj6FY3cXDO8oxpuxeAMb', {
      personas_data: [persona], persona_ids: [persona.id], persona_count: 1, is_demo: isReadOnly,
    });
    render(<StudyWorkflowView studyId="tj6FY3cXDO8oxpuxeAMb" initialStep={2} onExit={vi.fn()} />);
    await awaitSeededStudy();
    const archive = vi.spyOn(api, 'archiveStudyPersona').mockResolvedValue({
      study_id: 'tj6FY3cXDO8oxpuxeAMb', study_revision: 7, persona_count: 0, persona_ids: [], personas_data: [],
    });

    const remove = screen.getByRole('button', { name: `Remove persona ${persona.name}` });
    expect(remove.getAttribute('title')).toContain(`Remove persona ${persona.name}`);
    if (isReadOnly) {
      expect(remove).toBeDisabled();
      expect(remove.getAttribute('title')).toMatch(/read-only/i);
      fireEvent.click(remove);
      expect(screen.getByText(persona.name)).toBeInTheDocument();
      expect(archive).not.toHaveBeenCalled();
    } else {
      expect(remove).toBeEnabled();
      remove.focus();
      expect(remove).toHaveFocus();
      fireEvent.click(remove);
      // Removal is a server action (archive), never a local list edit that a reload would undo.
      await waitFor(() => expect(archive).toHaveBeenCalledWith('tj6FY3cXDO8oxpuxeAMb', persona.id));
      await waitFor(() => expect(screen.queryByText(persona.name)).not.toBeInTheDocument());
    }
  });

  it('keeps the persona when the server refuses the removal', async () => {
    const persona = {
      id: 'persona_removal_refused', name: 'Kept Persona',
      initials: 'KP', role_title: 'Office Manager', description: 'Synthetic fixture.',
    } as GeneratePersonasResult['personas'][number];
    seedStudyPrompt('tj6FY3cXDO8oxpuxeAMb', { personas_data: [persona], persona_ids: [persona.id], persona_count: 1 });
    vi.spyOn(api, 'archiveStudyPersona').mockRejectedValue(new Error('Removing the persona failed'));
    render(<StudyWorkflowView studyId="tj6FY3cXDO8oxpuxeAMb" initialStep={2} onExit={vi.fn()} />);
    await awaitSeededStudy();

    fireEvent.click(screen.getByRole('button', { name: `Remove persona ${persona.name}` }));
    expect(await screen.findByText(/The persona is still part of the study/i)).toBeInTheDocument();
    expect(screen.getByText(persona.name)).toBeInTheDocument();
  });

  it('asks before removing a persona that already has an interview', async () => {
    const persona = seedInterviewedStudy('tj6FY3cXDO8oxpuxeAMb', { step: 2 });
    const archive = vi.spyOn(api, 'archiveStudyPersona').mockResolvedValue({
      study_id: 'tj6FY3cXDO8oxpuxeAMb', study_revision: 8, persona_count: 0, persona_ids: [], personas_data: [],
    });
    render(<StudyWorkflowView studyId="tj6FY3cXDO8oxpuxeAMb" initialStep={2} onExit={vi.fn()} />);
    await awaitSeededStudy();
    await waitFor(() => expect(api.listStudyInterviews).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: `Remove persona ${persona.name}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Remove this persona?' });
    expect(archive).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('button', { name: 'Cancel' })).toHaveFocus();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove persona' }));
    await waitFor(() => expect(archive).toHaveBeenCalledWith('tj6FY3cXDO8oxpuxeAMb', persona.id));
    await waitFor(() => expect(screen.queryByText(persona.name)).not.toBeInTheDocument());
  });

  it('shows empty state on step 2 when no personas exist and not generating', async () => {
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

    expect(await screen.findByText('No personas yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Generate Personas$/i })).toBeInTheDocument();
  });

  it('keeps generated persona cards and identifies a study draft save failure without regenerating or copying the study', async () => {
    seedStudyPrompt('tj6FY3cXDO8oxpuxeAMb');
    const persona = {
      id: 'persona_saved_generation', name: 'Generated Office Manager',
      initials: 'GO', role_title: 'Office Manager', description: 'Synthetic fixture.',
    } as GeneratePersonasResult['personas'][number];
    const generate = vi.spyOn(api, 'generateStudyPersonasDetailed').mockResolvedValue(envelope([persona]));
    vi.spyOn(api, 'updateStudy').mockRejectedValue(new Error('Snapshot storage unavailable'));
    const createStudy = vi.spyOn(api, 'createStudy');
    const discardDraft = vi.spyOn(api, 'discardStudyDraft');
    render(<StudyWorkflowView studyId="tj6FY3cXDO8oxpuxeAMb" initialStep={2} onExit={vi.fn()} />);
    await awaitSeededStudy();
    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Study draft save failed:.*Snapshot storage unavailable/i);
    expect(alert).toHaveTextContent(/Personas were generated/i);
    expect(alert).not.toHaveTextContent(/Persona generation failed|no personas were fabricated|regenerate to retry/i);
    expect(screen.getByText(persona.name)).toBeInTheDocument();
    const regenerate = screen.getByRole('button', { name: 'Regenerate Personas' });
    expect(regenerate).toBeDisabled();
    expect(regenerate).toHaveAttribute('title', 'Save the retained draft or reload the saved version before generating new personas.');
    fireEvent.click(regenerate);
    expect(generate).toHaveBeenCalledTimes(1);
    expect(createStudy).not.toHaveBeenCalled();
    expect(discardDraft).not.toHaveBeenCalled();
  });

  it('identifies a persona generation failure separately from a study draft save failure', async () => {
    seedStudyPrompt('tj6FY3cXDO8oxpuxeAMb');
    vi.spyOn(api, 'generateStudyPersonasDetailed').mockRejectedValue(new Error('Cohort selection unavailable'));
    render(<StudyWorkflowView studyId="tj6FY3cXDO8oxpuxeAMb" initialStep={2} onExit={vi.fn()} />);
    await awaitSeededStudy();
    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/Persona generation failed:.*Cohort selection unavailable/i);
    expect(alert).not.toHaveTextContent(/Study draft save failed|Personas were generated/i);
    expect(screen.getByText('No personas yet')).toBeInTheDocument();
  });

  it('shows loading banner and skeleton cards while persona generation is in flight, then clears them', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    type Envelope = Awaited<ReturnType<typeof api.generateStudyPersonasDetailed>>;
    seedStudyPrompt('study_loading_state');
    let resolveGeneration!: (personas: GeneratedPersonas) => void;
    vi.spyOn(api, 'generateStudyPersonasDetailed').mockReturnValue(
      new Promise<Envelope>((resolve) => {
        resolveGeneration = (personas) => resolve(envelope(personas));
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

    await awaitSeededStudy();
    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));

    // In-flight: status banner + shimmering skeleton cards, no empty state
    expect(screen.getByText(/Generating personas/i)).toBeInTheDocument();
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
      expect(screen.queryByText(/Generating personas/i)).not.toBeInTheDocument();
      expect(container.querySelectorAll('.bx-skeleton').length).toBe(0);
    });
  });

  it('renders an honest empty state on step 5 when no report exists — never placeholder findings', async () => {
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

    // Honest badge + empty state: without a completed interview the report
    // cannot be generated, and the CTA says so instead of inviting a failure.
    expect(await screen.findByText('No report generated yet')).toBeInTheDocument();
    expect(screen.getByText('No report yet')).toBeInTheDocument();
    expect(screen.getByText(/Complete at least one interview in the Interviews step first/i)).toBeInTheDocument();
    const generateButton = screen.getByRole('button', { name: /Generate Decision Report/i });
    expect(generateButton).toBeDisabled();
    expect(generateButton).toHaveAttribute('title', 'Complete at least one interview first');

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
    seedInterviewedStudy('study_empty_state_report', { step: 5 });
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

    const generate = await screen.findByRole('button', { name: /Generate Decision Report/i });
    expect(await screen.findByText(/Generate it from your study data/i)).toBeInTheDocument();
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);

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
    seedStudyPrompt('study_modal_honesty');
    vi.spyOn(api, 'generateStudyPersonasDetailed').mockResolvedValue(envelope([
      {
        id: 'per_sparse_1',
        name: 'Sparse Persona',
        initials: 'SP',
        role_title: 'Primary User',
        description: 'A generated persona with no verified claims yet.',
      } as GeneratedPersonas[number],
    ]));

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

    await awaitSeededStudy();
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
    expect(screen.getByText(/No labelled claims recorded for this persona yet/i)).toBeInTheDocument();
    expect(screen.queryByText('Streamline daily tasks')).not.toBeInTheDocument();
    expect(screen.queryByText('High recurring cost')).not.toBeInTheDocument();

    // Focus moved into the dialog on open (focus trap entry point)
    const dialog = screen.getByRole('dialog');
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('renders the real-customer validation safeguard card with SYNTHETIC claims first, even when no report exists', async () => {
    type GeneratedPersonas = Awaited<ReturnType<typeof api.generateStudyPersonas>>;
    seedStudyPrompt('study_safeguard_card');
    vi.spyOn(api, 'generateStudyPersonasDetailed').mockResolvedValue(envelope([
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
    ]));

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

    await awaitSeededStudy();
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

  it('restores the persisted step only when the URL step is omitted', async () => {
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
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

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
      expect(screen.getByText('Study Personas')).toBeInTheDocument();
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

    const input = await screen.findByPlaceholderText(/Type here to answer or give more context/i);
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

  it('Fix 14: Generate Script button in Step 2 is disabled when step 3 is not yet unlocked (no goal approved)', async () => {
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
    const generateScriptBtn = await screen.findByRole('button', { name: /Generate Script/i });
    expect(generateScriptBtn).toBeDisabled();
    expect(generateScriptBtn).toHaveAttribute('title', 'Generate personas first');
  });
});

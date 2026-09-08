import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';
import { isTemplateReply, TEMPLATE_COPILOT_ROUTE } from '../src/components/dashboard/views/workflow/types';

/**
 * GROUP F — honest fallback labelling. A keyword-template copilot reply
 * (backend `served_by: bebshax/copilot-engine` / `fallback_reason`) must be
 * labelled as such and must never be approvable as an AI research goal.
 */
const renderStep1 = (studyId = 'study_template_test') =>
  render(
    <StudyWorkflowView
      studyId={studyId}
      initialStep={1}
      initialType="interviews"
      initialPrompt=""
      onExit={vi.fn()}
      onStepChange={vi.fn()}
    />
  );

const sendMessage = (text: string) => {
  const input = screen.getByPlaceholderText(/Type here to answer or give more context/i);
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByLabelText(/Send prompt/i));
};

describe('isTemplateReply predicate', () => {
  it('flags only the legacy template route — a retried model reply is still a model reply', () => {
    expect(isTemplateReply({ served_by: TEMPLATE_COPILOT_ROUTE })).toBe(true);
    expect(isTemplateReply({ served_by: 'llm7/codestral-latest', fallback_reason: 'retried_after_unparseable_reply' })).toBe(false);
    expect(isTemplateReply({ served_by: 'llm7/codestral-latest' })).toBe(false);
    expect(isTemplateReply({ served_by: 'llm7/codestral-latest', fallback_reason: null })).toBe(false);
  });
});

describe('Copilot template replies are labelled and cannot be approved', () => {
  beforeEach(async () => {
    api.setMockMode(true);
    await api.resetMockStore();
    vi.restoreAllMocks();
  });

  it('renders an amber template chip with the backend reason on a template goal card and disables approval', async () => {
    vi.spyOn(api, 'sendStudyCopilotMessage').mockResolvedValue({
      reply: 'Here is a research goal proposal:',
      suggested_study_type: 'interviews',
      is_ready_for_approval: true,
      research_goal_card: {
        title: 'RESEARCH GOAL',
        summary: 'Validate demand for a study planner among students.',
        target_audience: 'University students',
        core_hypothesis: 'Students will pay for planning help',
      },
      suggested_roles: [],
      served_by: TEMPLATE_COPILOT_ROUTE,
      fallback_reason: 'llm_error:TimeoutError',
    });

    renderStep1();
    sendMessage('a study planner for students');

    const chip = await screen.findByText(/Template reply — AI providers unavailable/i);
    expect(chip).toBeInTheDocument();
    expect(screen.getByText(/llm_error:TimeoutError/)).toBeInTheDocument();

    const approve = screen.getByRole('button', { name: /Approve Goal & Discover Personas/i });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/came from a keyword template, not the AI/i)).toBeInTheDocument();

    // Clicking the disabled button must not open the role drawer.
    fireEvent.click(approve);
    expect(screen.queryByText(/Goal Approved/i)).not.toBeInTheDocument();
  });

  it('labels a template reply even without a goal card, and leaves real LLM replies unlabelled', async () => {
    const spy = vi.spyOn(api, 'sendStudyCopilotMessage');
    spy.mockResolvedValueOnce({
      reply: 'Tell me more about your target users.',
      suggested_study_type: 'interviews',
      is_ready_for_approval: false,
      research_goal_card: null,
      suggested_roles: [],
      served_by: TEMPLATE_COPILOT_ROUTE,
      fallback_reason: 'llm_router_unavailable',
    });
    spy.mockResolvedValueOnce({
      reply: 'Great — which geography first?',
      suggested_study_type: 'interviews',
      is_ready_for_approval: false,
      research_goal_card: null,
      suggested_roles: [],
      served_by: 'llm7/codestral-latest',
      fallback_reason: null,
    });

    renderStep1('study_template_mixed');
    sendMessage('first idea');
    await screen.findByText('Tell me more about your target users.');
    expect(screen.getAllByText(/Template reply — AI providers unavailable/i)).toHaveLength(1);

    sendMessage('second detail');
    await screen.findByText('Great — which geography first?');
    // Still exactly one chip: the LLM-served reply is not labelled as a template.
    expect(screen.getAllByText(/Template reply — AI providers unavailable/i)).toHaveLength(1);
  });

  it('approval works normally for an LLM-served goal card', async () => {
    vi.spyOn(api, 'sendStudyCopilotMessage').mockResolvedValue({
      reply: 'Proposal below:',
      suggested_study_type: 'interviews',
      is_ready_for_approval: true,
      research_goal_card: {
        title: 'RESEARCH GOAL',
        summary: 'Validate demand.',
        target_audience: 'Students',
        core_hypothesis: 'Demand exists',
      },
      suggested_roles: [{ id: 'r1', role: 'STUDENT', description: 'core user', count: 3, selected: true }],
      served_by: 'llm7/codestral-latest',
    });

    renderStep1('study_llm_goal');
    sendMessage('a study planner');

    const approve = await screen.findByRole('button', { name: /Approve Goal & Discover Personas/i });
    expect(approve).not.toBeDisabled();
    expect(screen.queryByText(/Template reply/i)).not.toBeInTheDocument();
  });

  it('shows the friendly error, reason and request id when the copilot call fails', async () => {
    const err = Object.assign(new Error('All candidate routes failed'), {
      status: 503,
      errorCode: 'all_candidates_failed',
      requestId: 'req_copilot_503',
      attempts: [{ provider: 'groq', model: 'llama', failure_kind: 'RATE_LIMITED', fallback_reason: null }],
    });
    vi.spyOn(api, 'sendStudyCopilotMessage').mockRejectedValue(err);

    renderStep1('study_copilot_envelope');
    sendMessage('my idea');

    const bubble = await screen.findByText(/All AI routes failed — nothing was fabricated\. 1 attempt: groq\/llama→RATE_LIMITED/i);
    expect(bubble).toBeInTheDocument();
    expect(screen.getByText(/Request ID:/i)).toBeInTheDocument();
    expect(screen.getByText('req_copilot_503')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy request ID/i })).toBeInTheDocument();
    expect(screen.queryByText('RESEARCH GOAL')).not.toBeInTheDocument();
  });
});

describe('Step 3 script source honesty', () => {
  beforeEach(async () => {
    api.setMockMode(true);
    await api.resetMockStore();
    vi.restoreAllMocks();
  });

  const renderStep3 = (studyId: string) =>
    render(
      <StudyWorkflowView
        studyId={studyId}
        initialStep={3}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={vi.fn()}
      />
    );

  it('keeps the starter-template label when the backend served fallback_static questions', async () => {
    vi.spyOn(api, 'generateStudyScriptQuestions').mockResolvedValue({
      study_id: 'study_script_static',
      questions: ['Canned Q1?', 'Canned Q2?'],
      count: 2,
      source: 'fallback_static',
      fallback_reason: 'llm_error:AllCandidatesFailed',
    });

    renderStep3('study_script_static');
    fireEvent.click(screen.getByRole('button', { name: /^Generate Questions$/i }));

    await screen.findByDisplayValue('Canned Q1?');
    expect(screen.getByText(/Starter script \(not AI-generated for this study\)/i)).toBeInTheDocument();
    // The header still says the script is not generated — no "Regenerate" success state.
    expect(screen.getByRole('button', { name: /^Generate Questions$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Regenerate Questions/i })).not.toBeInTheDocument();
    expect(localStorage.getItem('bebshax_script_generated_study_script_static')).toBeNull();
  });

  it('marks the script as generated only when source is llm', async () => {
    vi.spyOn(api, 'generateStudyScriptQuestions').mockResolvedValue({
      study_id: 'study_script_llm',
      questions: ['Real Q1?', 'Real Q2?'],
      count: 2,
      source: 'llm',
    });

    renderStep3('study_script_llm');
    fireEvent.click(screen.getByRole('button', { name: /^Generate Questions$/i }));

    await screen.findByDisplayValue('Real Q1?');
    expect(screen.queryByText(/Starter script \(not AI-generated/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Regenerate Questions/i })).toBeInTheDocument();
    expect(localStorage.getItem('bebshax_script_generated_study_script_llm')).toBe('1');
  });
});

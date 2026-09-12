import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { api } from '../src/services/api';
import { clearRouteTimings, readRouteTimings, setRouteTimingEnabled, startRouteTiming } from '../src/performance/routeTiming';
import type { Conversation, Persona, Study } from '../src/types';

const timestamp = '2026-09-09T10:00:00Z';
const persona: Persona = {
  id: 'persona_restore', business_id: 'business_restore', name: 'Synthetic Office Manager',
  status: 'active', version: 1, archetype: 'Office Manager', tagline: 'Synthetic fixture',
  demographics: {
    age: 35, gender: 'Unspecified', occupation: 'Office Manager', income_bracket: 'Unknown',
    location: 'Test City', education: 'Unknown',
  },
  attributes: [], consistency_score: 0, grounding_ratio: 0, critic_notes: '',
  generation_model: 'test/fixture', created_at: timestamp,
};
const study = {
  id: 'study_restore_gate', title: 'Transcript restoration', type: 'interviews',
  prompt: 'Research synthetic office purchasing preferences.', status: 'in_progress', step: 4,
  is_demo: false, persona_count: 1, persona_ids: [persona.id], personas_data: [persona],
  copilot_messages: [], suggested_roles: [], script_questions: ['How do you purchase supplies?'],
  created_at: timestamp, updated_at: timestamp,
} satisfies Study;
const conversation: Conversation = {
  id: 'conversation_restore_gate', persona_id: persona.id, objective: study.prompt,
  status: 'active', created_at: timestamp,
  turns: [{ id: 'saved_reply', role: 'assistant', content: 'Previously saved response.', timestamp }],
};
const storageKey = `bebshax_conv_${study.id}_${persona.id}`;

describe('Study transcript restoration', () => {
  let previousMockMode: boolean;

  beforeEach(() => {
    previousMockMode = api.isMockMode();
    api.setMockMode(true);
    localStorage.clear();
    localStorage.setItem(storageKey, conversation.id);
    vi.spyOn(api, 'getStudy').mockResolvedValue(study);
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'listStudyInterviews').mockResolvedValue({ interviews: [], total: 0 });
    vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('Evidence unavailable'));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    setRouteTimingEnabled(false);
    clearRouteTimings();
    api.setMockMode(previousMockMode);
    localStorage.clear();
  });

  it.each(['success', 'failure'] as const)(
    'blocks early submission and releases the composer only after restoration %s is resolved',
    async (outcome) => {
      let resolveRestore!: (value: Conversation) => void;
      let rejectRestore!: (error: Error) => void;
      const restoration = new Promise<Conversation>((resolve, reject) => {
        resolveRestore = resolve;
        rejectRestore = reject;
      });
      const getConversation = vi.spyOn(api, 'getConversation').mockReturnValue(restoration);
      const startConversation = vi.spyOn(api, 'startConversation').mockResolvedValue(conversation);
      const sendMessage = vi.spyOn(api, 'sendMessage').mockResolvedValue({
        userTurn: { id: 'new_question', role: 'user', content: 'A follow-up question.', timestamp },
        assistantTurn: { id: 'new_reply', role: 'assistant', content: 'New follow-up response.', timestamp },
      });
      render(
        <StudyWorkflowView
          studyId={study.id} initialStep={4} initialType="interviews" initialPrompt=""
          onExit={vi.fn()} onStepChange={vi.fn()}
        />,
      );
      await waitFor(() => expect(getConversation).toHaveBeenCalledWith(conversation.id));
      const input = screen.getByRole('textbox', { name: 'Follow-up interview question' });
      const form = input.closest('form');
      expect(form).not.toBeNull();
      expect(input).toBeDisabled();
      fireEvent.change(input, { target: { value: 'An early question.' } });
      fireEvent.submit(form!);
      expect(sendMessage).not.toHaveBeenCalled();
      expect(startConversation).not.toHaveBeenCalled();

      await act(async () => {
        if (outcome === 'success') resolveRestore(conversation);
        else rejectRestore(new Error('Saved conversation unavailable'));
      });
      if (outcome === 'success') {
        expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
      } else {
        expect(await screen.findByRole('alert')).toHaveTextContent(/Saved conversation unavailable/);
        expect(localStorage.getItem(storageKey)).toBe(conversation.id);
        expect(input).toBeDisabled();
        fireEvent.submit(form!);
        expect(startConversation).not.toHaveBeenCalled();
        expect(sendMessage).not.toHaveBeenCalled();
        getConversation.mockResolvedValueOnce(conversation);
        fireEvent.click(screen.getByRole('button', { name: 'Retry transcript' }));
      }
      await waitFor(() => expect(input).toBeEnabled());
      fireEvent.change(input, { target: { value: 'A follow-up question.' } });
      fireEvent.submit(form!);
      expect(await screen.findByText('New follow-up response.')).toBeInTheDocument();
      expect(sendMessage).toHaveBeenCalledTimes(1);
      expect(startConversation).not.toHaveBeenCalled();
      expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
    },
  );

  it('retains the restored transcript and conversation when the active persona is selected again', async () => {
    const getConversation = vi.spyOn(api, 'getConversation').mockResolvedValue(conversation);
    const startConversation = vi.spyOn(api, 'startConversation').mockResolvedValue(conversation);
    const sendMessage = vi.spyOn(api, 'sendMessage').mockResolvedValue({
      userTurn: { id: 'reselected_question', role: 'user', content: 'A follow-up question.', timestamp },
      assistantTurn: { id: 'reselected_reply', role: 'assistant', content: 'Same conversation response.', timestamp },
    });
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText('Previously saved response.');

    fireEvent.click(screen.getByRole('button', { name: new RegExp(persona.name) }));

    expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
    expect(localStorage.getItem(storageKey)).toBe(conversation.id);
    expect(getConversation).toHaveBeenCalledTimes(1);
    const input = screen.getByRole('textbox', { name: 'Follow-up interview question' });
    expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: 'A follow-up question.' } });
    fireEvent.submit(input.closest('form')!);

    expect(await screen.findByText('Same conversation response.')).toBeInTheDocument();
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage.mock.calls[0][0]).toBe(conversation.id);
    expect(startConversation).not.toHaveBeenCalled();
    expect(screen.getByText('Previously saved response.')).toBeInTheDocument();
    expect(localStorage.getItem(storageKey)).toBe(conversation.id);
  });

  it('labels restored interview messages and uses readable text on the user bubble', async () => {
    vi.spyOn(api, 'getConversation').mockResolvedValue({
      ...conversation,
      turns: [
        { id: 'saved_question', role: 'user', content: 'How do you purchase supplies?', timestamp },
        ...conversation.turns,
      ],
    });
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText('Previously saved response.');

    const transcript = screen.getByRole('log', { name: 'Interview transcript' });
    expect(transcript).toHaveAttribute('aria-live', 'polite');
    const userMessage = within(transcript).getByRole('article', { name: 'Your question' });
    expect(userMessage).toHaveTextContent('How do you purchase supplies?');
    expect(userMessage.style.color).toBe('var(--text-on-accent)');
    expect(within(transcript).getByRole('article', { name: 'Synthetic persona response' }))
      .toHaveTextContent('Previously saved response.');
  });

  it('names the send control and lets the question field shrink on narrow screens', async () => {
    vi.spyOn(api, 'getConversation').mockResolvedValue(conversation);
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText('Previously saved response.');

    const input = screen.getByRole('textbox', { name: 'Follow-up interview question' });
    expect(Number.parseFloat(input.style.minWidth)).toBe(0);
    const send = screen.getByRole('button', { name: 'Send question' });
    expect(send).toBeDisabled();
    fireEvent.change(input, { target: { value: 'A follow-up question.' } });
    expect(send).toBeEnabled();
  });

  it.each([
    { personas: [], questions: ['How do you purchase supplies?'], reason: 'Select at least one persona before running interviews.' },
    { personas: [persona], questions: [], reason: 'Add at least one question in Script before running interviews.' },
    { personas: [persona], questions: ['   '], reason: 'Fill in or remove empty script questions before running interviews.' },
    { personas: [persona], questions: ['How do you purchase supplies?', ''], reason: 'Fill in or remove empty script questions before running interviews.' },
  ])('blocks a fresh batch for personas=$personas.length and questions=$questions with an accessible reason', async (inputs) => {
    vi.mocked(api.getStudy).mockResolvedValue({
      ...study,
      personas_data: inputs.personas,
      persona_ids: inputs.personas.map((entry) => entry.id),
      persona_count: inputs.personas.length,
      script_questions: inputs.questions,
    });
    vi.spyOn(api, 'getConversation').mockResolvedValue(conversation);
    const startBatch = vi.spyOn(api, 'runBatchStudyInterviews').mockRejectedValue(new Error('Unexpected batch request'));
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText(study.title);

    const run = screen.getByRole('button', { name: 'Run All Synthetic Interviews' });
    expect(run).toBeDisabled();
    expect(run).toHaveAccessibleDescription(inputs.reason);
    expect(run).toHaveAttribute('title', inputs.reason);
    expect(screen.getByText(inputs.reason)).toBeInTheDocument();
    fireEvent.click(run);
    expect(startBatch).not.toHaveBeenCalled();
  });

  it('resumes a saved batch without local personas or questions and never submits a fresh request', async () => {
    api.setMockMode(false);
    vi.mocked(api.getStudy).mockResolvedValue({
      ...study, personas_data: [], persona_ids: [], persona_count: 0, script_questions: [],
    });
    vi.spyOn(api, 'getPendingJobHandle').mockImplementation((studyId, kind) =>
      studyId === study.id && kind === 'batch' ? 'batch_saved_progress' : null,
    );
    const getStatus = vi.spyOn(api, 'getBatchRunStatus').mockResolvedValue({
      job_id: 'batch_saved_progress', status: 'completed', personas: {},
    });
    const forgetJob = vi.spyOn(api, 'forgetJobHandle').mockImplementation(() => {});
    const fetchRequest = vi.fn().mockRejectedValue(new Error('Unexpected fresh request'));
    vi.stubGlobal('fetch', fetchRequest);
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText(study.title);

    const run = screen.getByRole('button', { name: 'Run All Synthetic Interviews' });
    expect(run).toBeEnabled();
    fireEvent.click(run);
    await waitFor(() => expect(forgetJob).toHaveBeenCalledWith(study.id, 'batch'));
    expect(getStatus).toHaveBeenCalledWith(study.id, 'batch_saved_progress', expect.any(AbortSignal));
    expect(fetchRequest).not.toHaveBeenCalled();
  });

  it('rechecks fresh-batch prerequisites if the saved job handle disappears before a resume click', async () => {
    vi.mocked(api.getStudy).mockResolvedValue({
      ...study, personas_data: [], persona_ids: [], persona_count: 0, script_questions: [],
    });
    let pendingJob: string | null = 'batch_disappearing_handle';
    vi.spyOn(api, 'getPendingJobHandle').mockImplementation((studyId, kind) =>
      studyId === study.id && kind === 'batch' ? pendingJob : null,
    );
    const startBatch = vi.spyOn(api, 'runBatchStudyInterviews').mockResolvedValue({
      job_id: 'unexpected_batch', status: 'completed', personas: {},
    });
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText(study.title);
    const run = screen.getByRole('button', { name: 'Run All Synthetic Interviews' });
    expect(run).toBeEnabled();

    pendingJob = null;
    fireEvent.click(run);

    expect(startBatch).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent('Select at least one persona before running interviews.');
    expect(run).toBeDisabled();
  });

  it('starts a fresh batch with the selected personas and complete nonempty questions', async () => {
    const question = 'Describe every constraint on purchasing supplies. '.repeat(12).trim();
    vi.mocked(api.getStudy).mockResolvedValue({ ...study, script_questions: [question] });
    vi.spyOn(api, 'getConversation').mockResolvedValue(conversation);
    const startBatch = vi.spyOn(api, 'runBatchStudyInterviews').mockResolvedValue({
      job_id: 'batch_fresh', status: 'completed', personas: { [persona.id]: { status: 'completed' } },
    });
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText('Previously saved response.');

    const run = screen.getByRole('button', { name: 'Run All Synthetic Interviews' });
    expect(run).toBeEnabled();
    fireEvent.click(run);

    await waitFor(() => expect(startBatch).toHaveBeenCalledWith(study.id, [persona.id], [question], expect.any(AbortSignal)));
    expect(startBatch).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole('button', { name: `${persona.name} Completed` })).toBeInTheDocument();
  });

  it('does not count a saved-transcript spinner as primary content', async () => {
    let finish!: (value: Conversation) => void;
    vi.spyOn(api, 'getConversation').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const frames = new Map<number, FrameRequestCallback>();
    let frameId = 0;
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => { frames.delete(id); });
    const paint = () => {
      for (let pass = 0; pass < 3; pass += 1) {
        const callbacks = [...frames.values()];
        frames.clear();
        callbacks.forEach((callback) => callback(0));
      }
    };
    setRouteTimingEnabled(true);
    startRouteTiming(`/research/${study.id}/step4`);
    render(<StudyWorkflowView studyId={study.id} initialStep={4} onExit={vi.fn()} />);
    await screen.findByText('Loading saved transcript...');
    act(paint);
    expect(readRouteTimings()).toEqual([]);

    await act(async () => { finish(conversation); });
    act(paint);
    expect(readRouteTimings()).toEqual([expect.objectContaining({ route: 'workflow-4', stage: 'primary-content', outcome: 'content' })]);
  });
});
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';
import { api } from '../src/services/api';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { knownStudyRevision, rememberStudyRevision } from '../src/services/studyPersistence';
import type { Study } from '../src/types';

/* Live 2026-09-14 (sweep B): approving a goal fired the study PATCH and the
 * research run together, so admission refused with 409 research_input_changed;
 * with two proposals on screen, approving one flipped both to "Goal Approved";
 * the card's target audience was never persisted; a chat message sent after
 * approval — and even a step change — overwrote the approved goal, which every
 * interview then received as its objective; "Generate Questions" accepted a
 * double-click and billed two LLM requests; and the report projection's
 * revision bump surfaced as a 412 on the next save. */

type CopilotResponse = Awaited<ReturnType<typeof api.sendStudyCopilotMessage>>;

const study: Study = {
  id: 'study_goal_approval', title: 'Goal approval study', type: 'interviews', prompt: 'A laundry pickup service for students',
  status: 'in_progress', step: 1, persona_count: 0, persona_ids: [], copilot_messages: [],
  created_at: '2026-09-14T00:00:00Z', updated_at: '2026-09-14T00:00:00Z',
};

const proposal = (summary: string, target_audience: string): CopilotResponse => ({
  reply: 'Here is the proposal. Does this capture what you\'re looking for?',
  is_ready_for_approval: true,
  research_goal_card: { title: 'RESEARCH GOAL', summary, target_audience, core_hypothesis: 'Students pay for convenience' },
  suggested_roles: [{ id: 'role_1', role: 'HOSTEL STUDENT', description: 'Primary user', count: 3, selected: true }],
  suggested_study_type: 'interviews',
  served_by: 'fake/test-model',
});

const CARD_A = 'Validate whether Dhaka University hostel students will pay 300 BDT/week for laundry pickup.';
const CARD_B = 'Validate whether NSU students in Bashundhara will pay 300 BDT/week for laundry pickup.';

async function renderStep1(saved: Partial<Study> = {}) {
  vi.spyOn(api, 'getStudy').mockResolvedValue({ ...study, ...saved });
  vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
  vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(null as any);
  vi.spyOn(api, 'getSuggestedPersonaRoles').mockResolvedValue([
    { id: 'role_1', role: 'HOSTEL STUDENT', description: 'Primary user', count: 3, selected: true },
  ]);
  render(<StudyWorkflowView studyId={study.id} initialStep={1} initialType="interviews" initialPrompt="" onExit={vi.fn()} onStepChange={vi.fn()} />);
  await screen.findByText(study.title);
}

function send(text: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Describe your idea or answer the copilot' }), { target: { value: text } });
  fireEvent.click(screen.getByLabelText(/Send prompt/i));
}

describe('Goal approval owns the study prompt', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(true);
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('saves the approved goal and audience before the research run is admitted', async () => {
    let finishSave!: (value: Study) => void;
    const updateStudy = vi.spyOn(api, 'updateStudy').mockReturnValue(new Promise((resolve) => { finishSave = resolve; }));
    const research = vi.spyOn(api, 'triggerStudyResearch').mockResolvedValue({ id: 'run_1', status: 'queued' });
    vi.spyOn(api, 'sendStudyCopilotMessage').mockResolvedValue(proposal(CARD_A, 'Hostel students at Dhaka University'));
    await renderStep1();

    send('Laundry pickup for DU hostel students');
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Goal & Discover Personas' }));

    await waitFor(() => expect(updateStudy).toHaveBeenCalledWith(study.id, expect.objectContaining({
      prompt: CARD_A, step: 2, target_audience: 'Hostel students at Dhaka University',
    })));
    // Admission snapshots prompt + revision: the run must not start until the save landed.
    await act(async () => {});
    expect(research).not.toHaveBeenCalled();
    await act(async () => { finishSave({ ...study, prompt: CARD_A, step: 2 }); });
    await waitFor(() => expect(research).toHaveBeenCalledWith(study.id));
  });

  it('marks only the approved proposal as approved and keeps the other one approvable', async () => {
    vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    vi.spyOn(api, 'triggerStudyResearch').mockResolvedValue({ id: 'run_1', status: 'queued' });
    vi.spyOn(api, 'sendStudyCopilotMessage')
      .mockResolvedValueOnce(proposal(CARD_A, 'Hostel students at Dhaka University'))
      .mockResolvedValueOnce(proposal(CARD_B, 'NSU students in Bashundhara'));
    await renderStep1();

    send('Laundry pickup for DU hostel students');
    await screen.findByText(CARD_A);
    send('Actually, NSU students instead');
    await screen.findByText(CARD_B);
    const approveButtons = screen.getAllByRole('button', { name: 'Approve Goal & Discover Personas' });
    expect(approveButtons).toHaveLength(2);

    fireEvent.click(approveButtons[0]);

    expect(await screen.findByRole('button', { name: /Goal Approved/ })).toHaveAttribute('aria-pressed', 'true');
    const other = screen.getByRole('button', { name: 'Approve This Goal Instead' });
    expect(other).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getAllByRole('button', { name: /Goal Approved/ })).toHaveLength(1);
  });

  it('recognises the approved proposal after a reload from the saved prompt', async () => {
    const saved: Partial<Study> = {
      prompt: CARD_A,
      suggested_roles: [{ id: 'role_1', role: 'HOSTEL STUDENT', description: 'Primary user', count: 3, selected: true }],
      copilot_messages: [
        { id: 'u1', role: 'user', content: 'Laundry pickup for DU hostel students' },
        { id: 'a1', role: 'assistant', content: 'Proposal A', isGoalCard: true, goalCardData: { title: 'RESEARCH GOAL', summary: CARD_A, target_audience: 'DU', core_hypothesis: 'x' } },
        { id: 'u2', role: 'user', content: 'Or NSU?' },
        { id: 'a2', role: 'assistant', content: 'Proposal B', isGoalCard: true, goalCardData: { title: 'RESEARCH GOAL', summary: CARD_B, target_audience: 'NSU', core_hypothesis: 'y' } },
      ] as any,
    };
    await renderStep1(saved);

    const approved = await screen.findByRole('button', { name: /Goal Approved/ });
    expect(approved.closest('article')).toHaveTextContent(CARD_A);
    expect(screen.getByRole('button', { name: 'Approve This Goal Instead' }).closest('article')).toHaveTextContent(CARD_B);
  });

  it('stops chat messages from overwriting the prompt once a goal is approved', async () => {
    const updateStudy = vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    vi.spyOn(api, 'triggerStudyResearch').mockResolvedValue({ id: 'run_1', status: 'queued' });
    vi.spyOn(api, 'sendStudyCopilotMessage')
      .mockResolvedValueOnce(proposal(CARD_A, 'Hostel students at Dhaka University'))
      .mockResolvedValue({ reply: 'Noted.', is_ready_for_approval: false, research_goal_card: null, suggested_roles: [], suggested_study_type: 'interviews', served_by: 'fake/test-model' });
    await renderStep1();

    send('Laundry pickup for DU hostel students');
    // Before approval the latest idea text is the working prompt.
    expect(updateStudy).toHaveBeenCalledWith(study.id, expect.objectContaining({ prompt: 'Laundry pickup for DU hostel students' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve Goal & Discover Personas' }));
    await screen.findByRole('button', { name: /Goal Approved/ });
    updateStudy.mockClear();

    send('Some long follow-up paragraph that is not a research goal.');

    await waitFor(() => expect(updateStudy).toHaveBeenCalled());
    for (const [, changes] of updateStudy.mock.calls) expect(changes).not.toHaveProperty('prompt');
  });

  it('does not resend a stale prompt on step navigation', async () => {
    const updateStudy = vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    await renderStep1({
      step: 2, prompt: CARD_A,
      suggested_roles: [{ id: 'role_1', role: 'HOSTEL STUDENT', description: 'Primary user', count: 3, selected: true }],
      copilot_messages: [{ id: 'a1', role: 'assistant', content: 'Proposal A', isGoalCard: true, goalCardData: { title: 'RESEARCH GOAL', summary: CARD_A, target_audience: 'DU', core_hypothesis: 'x' } }] as any,
    });

    fireEvent.click(screen.getByRole('button', { name: /Step 2: Personas/i }));

    await waitFor(() => expect(updateStudy).toHaveBeenCalledWith(study.id, expect.objectContaining({ step: 2 })));
    for (const [, changes] of updateStudy.mock.calls) expect(changes).not.toHaveProperty('prompt');
  });
});

describe('Script generation double-click', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(true);
    vi.restoreAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  it('sends exactly one generation request for two rapid clicks', async () => {
    vi.spyOn(api, 'getStudy').mockResolvedValue({
      ...study, step: 3,
      suggested_roles: [{ id: 'role_1', role: 'HOSTEL STUDENT', description: 'Primary user', count: 1, selected: true }],
      personas_data: [{ id: 'per_1', name: 'Persona One', initials: 'PO', role_title: 'Hostel student', description: 'x' }] as any,
      persona_ids: ['per_1'], persona_count: 1,
    });
    vi.spyOn(api, 'getStudyReports').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(null as any);
    vi.spyOn(api, 'updateStudy').mockResolvedValue(study);
    let finish!: (value: Awaited<ReturnType<typeof api.generateStudyScriptQuestions>>) => void;
    const generate = vi.spyOn(api, 'generateStudyScriptQuestions').mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    render(<StudyWorkflowView studyId={study.id} initialStep={3} initialType="interviews" initialPrompt="" onExit={vi.fn()} onStepChange={vi.fn()} />);
    await screen.findByText(study.title);

    const button = screen.getByRole('button', { name: 'Generate Questions' });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(generate).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ study_id: study.id, questions: ['How do you do laundry today?'], count: 1, source: 'llm' }); });
    expect(await screen.findByDisplayValue('How do you do laundry today?')).toBeInTheDocument();
    // The guard releases once the request settles: a later click is a real regenerate.
    fireEvent.click(screen.getByRole('button', { name: 'Regenerate Questions' }));
    expect(generate).toHaveBeenCalledTimes(2);
  });
});

describe('Report completion adopts the projected study revision', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    api.setMockMode(false);
    api.setAuthToken('owner-fixture');
    api.setStoredUser({ id: 'owner', email: 'owner@example.test', full_name: 'Owner', is_active: true, is_verified: true, auth_provider: 'email', created_at: '2026-09-09' });
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    api.clearSession();
    api.setMockMode(true);
  });

  const report = (metrics: Record<string, unknown>) => ({
    id: 'rep_1', study_id: 'study_rev', version: 1, title: 'Report', executive_summary: 'Summary.',
    key_findings: ['One'], recommendations: ['Do it'], metrics,
  });
  const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

  it('moves the known revision forward so the next save does not bounce off a 412', async () => {
    rememberStudyRevision({ ...study, id: 'study_rev', revision: 4 } as Study);
    api.rememberJobHandle('study_rev', 'report', 'job_1');
    const completed = report({ study_projection_applied: true, published_study_revision: 5 });
    vi.mocked(fetch)
      .mockResolvedValueOnce(response({ job_id: 'job_1', status: 'completed', result: completed }))
      .mockResolvedValueOnce(response(completed));

    await expect(api.resumeStudyReport('study_rev')).resolves.toMatchObject({ id: 'rep_1' });

    expect(knownStudyRevision('study_rev')).toBe(5);
  });

  it('leaves the revision alone when the report was not projected onto the study', async () => {
    rememberStudyRevision({ ...study, id: 'study_rev', revision: 4 } as Study);
    api.rememberJobHandle('study_rev', 'report', 'job_2');
    const completed = report({ study_projection_applied: false, published_study_revision: null });
    vi.mocked(fetch)
      .mockResolvedValueOnce(response({ job_id: 'job_2', status: 'completed', result: completed }))
      .mockResolvedValueOnce(response(completed));

    await api.resumeStudyReport('study_rev');

    expect(knownStudyRevision('study_rev')).toBe(4);
  });
});

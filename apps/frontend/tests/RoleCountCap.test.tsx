import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { MAX_PERSONAS_PER_ROLE } from '../src/components/dashboard/views/workflow/types';
import { EvidenceSummary, Persona, PersonaRoleSuggestion, Study } from '../src/types';
import { api } from '../src/services/api';
import { discardStudyDraft, pendingStudyDraft, queueStudyWrite, rememberStudyRevision } from '../src/services/studyPersistence';
import { NavigationProvider, useNavigation } from '../src/context/NavigationContext';

vi.mock('../src/services/api', () => {
  const stub = {
    getStudy: vi.fn(),
    getStudyReports: vi.fn(),
    getPendingJobHandle: vi.fn().mockReturnValue(null),
    getPendingStudyDraft: vi.fn().mockReturnValue(undefined),
    getStoredUser: vi.fn().mockReturnValue(null),
    getEvidenceSummary: vi.fn(),
    updateStudy: vi.fn(),
    generateStudyPersonas: vi.fn(),
    generateStudyPersonasDetailed: vi.fn(),
    triggerStudyResearch: vi.fn(),
    getConversation: vi.fn(),
  };
  return { api: stub, default: stub };
});

const roles = (): PersonaRoleSuggestion[] => [
  {
    id: 'role_student',
    role: 'UNIVERSITY STUDENT',
    description: 'Core target user.',
    count: 1,
    selected: true,
  },
  {
    id: 'role_parent',
    role: 'PARENTAL BUYER',
    description: 'Pays for the tool but never uses it.',
    count: 0,
    selected: false,
  },
];

/** An approved goal card is what re-opens the role drawer on restore. */
const approvedChat = () => [
  { id: 'msg_u_1', role: 'user' as const, content: 'A study planner for Dhaka university students' },
  {
    id: 'msg_a_1',
    role: 'assistant' as const,
    content: 'Here is your research goal.',
    isGoalCard: true,
    goalCardData: {
      title: 'Study planner validation',
      summary: 'Validate demand for a paid study planner among Dhaka university students.',
      target_audience: 'University students in Dhaka',
      core_hypothesis: 'Students will pay 250 BDT/month for planning help.',
    },
  },
];

const study = (overrides: Partial<Study>): Study =>
  ({
    id: 'study_cap_01',
    title: 'Untitled Study',
    type: 'interviews',
    goal: 'demand_validation',
    prompt: 'A study planner for Dhaka university students',
    status: 'in_progress',
    persona_count: 0,
    persona_ids: [],
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    is_demo: false,
    step: 1,
    copilot_messages: approvedChat(),
    suggested_roles: roles(),
    personas_data: [],
    script_questions: [],
    ...overrides,
  } as unknown as Study);

const emptySummary: EvidenceSummary = {
  study_id: 'study_cap_01',
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
} as EvidenceSummary;

const persona = { id: 'per_1', name: 'Nusrat Jahan', archetype: 'Planner' } as unknown as Persona;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  (api.getStudyReports as any).mockResolvedValue([]);
  (api.getEvidenceSummary as any).mockResolvedValue(emptySummary);
  (api.updateStudy as any).mockResolvedValue({});
  (api.triggerStudyResearch as any).mockResolvedValue({});
  (api.generateStudyPersonasDetailed as any).mockResolvedValue({
    personas: [persona],
    failed_roles: [],
    served_by: ['fake/test-model'],
  });
});

const renderWorkflow = (initialStep: number) =>
  render(
    <StudyWorkflowView
      studyId="study_cap_01"
      initialStep={initialStep}
      initialType="interviews"
      initialPrompt=""
      onExit={vi.fn()}
      onStepChange={vi.fn()}
    />
  );

const plusButton = () => screen.getByRole('button', { name: /Increase UNIVERSITY STUDENT count/i });

const clickPlusFiveTimes = async () => {
  await screen.findByRole('button', { name: /Increase UNIVERSITY STUDENT count/i });
  for (let i = 0; i < 5; i += 1) {
    fireEvent.click(plusButton());
  }
};

describe('Accessible role selection', () => {
  it.each(['Enter', ' '] as const)('toggles the native role checkbox with %s and synchronizes its count', async (key) => {
    vi.mocked(api.getStudy).mockResolvedValue(study({}));
    renderWorkflow(1);

    const checkbox = await screen.findByRole('checkbox', { name: 'UNIVERSITY STUDENT' });
    expect(checkbox.tagName).toBe('INPUT');
    expect(checkbox).toHaveAttribute('type', 'checkbox');
    expect(checkbox).toBeChecked();
    expect(checkbox.closest('label')).not.toBeNull();
    expect(checkbox.closest('label')!.querySelector('button')).toBeNull();
    checkbox.focus();
    expect(checkbox).toHaveFocus();

    fireEvent.keyDown(checkbox, { key });
    fireEvent.keyUp(checkbox, { key });
    expect(checkbox).not.toBeChecked();
    expect(within(plusButton().parentElement!).getByText('0')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Generate Personas$/i })).toBeDisabled();

    fireEvent.keyDown(checkbox, { key });
    fireEvent.keyUp(checkbox, { key });
    expect(checkbox).toBeChecked();
    expect(within(plusButton().parentElement!).getByText(String(MAX_PERSONAS_PER_ROLE))).toBeInTheDocument();
    expect(plusButton()).toBeDisabled();
    fireEvent.keyDown(checkbox, { key, repeat: true });
    expect(checkbox).toBeChecked();
    expect(fireEvent.keyDown(checkbox, { key: 'Tab' })).toBe(true);
    expect(api.generateStudyPersonasDetailed).not.toHaveBeenCalled();
  });

  it('keeps the checkbox synchronized when independent count buttons select and deselect a role', async () => {
    vi.mocked(api.getStudy).mockResolvedValue(study({}));
    renderWorkflow(1);

    const checkbox = await screen.findByRole('checkbox', { name: 'PARENTAL BUYER' });
    const increase = screen.getByRole('button', { name: 'Increase PARENTAL BUYER count' });
    const decrease = screen.getByRole('button', { name: 'Decrease PARENTAL BUYER count' });
    expect(checkbox).not.toBeChecked();
    expect(increase.closest('label')).toBeNull();
    expect(decrease.closest('label')).toBeNull();
    fireEvent.click(increase);
    expect(checkbox).toBeChecked();
    expect(within(increase.parentElement!).getByText('1')).toBeInTheDocument();
    fireEvent.click(decrease);
    expect(checkbox).not.toBeChecked();
    expect(within(increase.parentElement!).getByText('0')).toBeInTheDocument();
    expect(decrease).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'UNIVERSITY STUDENT' })).toBeChecked();
  });

  it('disables role checkboxes and count buttons for a read-only example', async () => {
    vi.mocked(api.getStudy).mockResolvedValue(study({ is_demo: true }));
    renderWorkflow(1);

    expect(await screen.findByRole('checkbox', { name: 'UNIVERSITY STUDENT' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: 'PARENTAL BUYER' })).toBeDisabled();
    expect(plusButton()).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Decrease UNIVERSITY STUDENT count' })).toBeDisabled();
    expect(api.generateStudyPersonasDetailed).not.toHaveBeenCalled();
  });
});

describe('Role count cap — the UI never asks for more personas per role than the server delivers', () => {
  it('clicking "+" five times leaves the count at the cap and disables the button', async () => {
    (api.getStudy as any).mockResolvedValue(study({}));
    renderWorkflow(1);

    await clickPlusFiveTimes();

    const plus = plusButton();
    // The count lives in the stepper next to the button, the chip in the row header.
    expect(within(plus.parentElement as HTMLElement).getByText(String(MAX_PERSONAS_PER_ROLE))).toBeInTheDocument();
    expect(screen.getByText(`Active (${MAX_PERSONAS_PER_ROLE})`)).toBeInTheDocument();
    expect(plus).toBeDisabled();
    expect(plus).toHaveAttribute('aria-disabled', 'true');
    expect(plus).toHaveAttribute('title', 'Up to 3 personas per role');
    // The untouched role's "+" stays live.
    expect(screen.getByRole('button', { name: /Increase PARENTAL BUYER count/i })).toBeEnabled();
  });

  it('the persona request never carries a role count above the cap and omits unselected roles', async () => {
    (api.getStudy as any).mockResolvedValue(study({}));
    renderWorkflow(1);

    await clickPlusFiveTimes();
    fireEvent.click(screen.getByRole('button', { name: /^Generate Personas$/i }));

    await waitFor(() => expect(api.generateStudyPersonasDetailed).toHaveBeenCalledTimes(1));
    const [, prompt, sentRoles] = (api.generateStudyPersonasDetailed as any).mock.calls[0] as [
      string,
      string,
      PersonaRoleSuggestion[],
      string,
    ];
    expect(prompt).toBe('A study planner for Dhaka university students');
    expect(sentRoles.length).toBeGreaterThan(0);
    expect(sentRoles.every((r) => r.selected && r.count >= 1 && r.count <= MAX_PERSONAS_PER_ROLE)).toBe(true);
    expect(sentRoles.find((r) => r.id === 'role_student')?.count).toBe(MAX_PERSONAS_PER_ROLE);
    expect(sentRoles.some((r) => r.id === 'role_parent')).toBe(false);
  });
});

describe('No fabricated business idea', () => {
  it('with no prompt anywhere, generating personas does not call the API and explains why', async () => {
    (api.getStudy as any).mockResolvedValue(
      study({ prompt: '', copilot_messages: [], step: 2 })
    );
    renderWorkflow(2);

    const generate = await screen.findByRole('button', { name: /^Generate Personas$/i });
    fireEvent.click(generate);

    const message = await screen.findByText(
      /Describe your business idea first — there is nothing to generate personas from\./
    );
    expect(message.closest('[role="alert"]')).not.toBeNull();
    expect(api.generateStudyPersonasDetailed).not.toHaveBeenCalled();
    // The generating state was released — the CTA is usable again.
    expect(screen.getByRole('button', { name: /Regenerate Personas/i })).toBeEnabled();
  });
});

describe('Guards run before the step change', () => {
  it('deselecting every role disables Generate in step 1 and refuses without leaving the step', async () => {
    (api.getStudy as any).mockResolvedValue(study({}));
    const onStepChange = vi.fn();
    render(
      <StudyWorkflowView
        studyId="study_cap_01"
        initialStep={1}
        initialType="interviews"
        initialPrompt=""
        onExit={vi.fn()}
        onStepChange={onStepChange}
      />
    );

    fireEvent.click(await screen.findByText('UNIVERSITY STUDENT'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Generate Personas$/i })).toBeDisabled()
    );
    expect(screen.getByRole('button', { name: /^Generate Personas$/i })).toHaveAttribute(
      'title',
      'Pick at least one role first'
    );
    expect(api.generateStudyPersonasDetailed).not.toHaveBeenCalled();
    // Never moved to step 2 while the user still had roles to pick.
    expect(onStepChange).not.toHaveBeenCalledWith(2);
  });
});

describe('Generated persona draft-save recovery', () => {
  it.each([1, 2])('blocks generation from step %i until the failed draft is retried and keeps generated personas', async (step) => {
    const original = study({ revision: 1 });
    const persist = vi.fn()
      .mockResolvedValueOnce(study({ revision: 2, step: 2 }))
      .mockRejectedValueOnce(new Error('Draft save unavailable'))
      .mockResolvedValueOnce(study({ revision: 3, step: 2 }));
    vi.mocked(api.getStudy).mockResolvedValue(original);
    rememberStudyRevision(original);
    vi.mocked(api.updateStudy).mockImplementation((id, updates) =>
      queueStudyWrite(id, 'anonymous', updates, async () => original, persist));
    const view = renderWorkflow(2);

    try {
      fireEvent.click(await screen.findByRole('button', { name: /^Generate Personas$/i }));
      const retry = await screen.findByRole('button', { name: 'Retry save' });
      expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
      expect(persist).toHaveBeenCalledTimes(2);
      const retainedDraft = pendingStudyDraft('anonymous', original.id);
      expect(retainedDraft).toBeDefined();
      await waitFor(() => expect(retry).toBeEnabled());

      view.rerender(<StudyWorkflowView studyId={original.id} initialStep={step} onExit={vi.fn()} />);
      fireEvent.click(screen.getByRole('button', { name: step === 1 ? 'Generate Personas' : 'Regenerate Personas' }));
      await act(async () => {});
      expect(api.generateStudyPersonasDetailed).toHaveBeenCalledTimes(1);
      expect(persist).toHaveBeenCalledTimes(2);
      expect(pendingStudyDraft('anonymous', original.id)).toEqual(retainedDraft);
      if (step === 1) expect(screen.getByRole('checkbox', { name: 'UNIVERSITY STUDENT' })).toBeInTheDocument();

      view.rerender(<StudyWorkflowView studyId={original.id} initialStep={2} onExit={vi.fn()} />);
      const retainedRetry = await screen.findByRole('button', { name: 'Retry save' });
      await waitFor(() => expect(retainedRetry).toBeEnabled());
      expect(screen.getByRole('button', { name: 'Regenerate Personas' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Regenerate Personas' })).toHaveAttribute('title',
        'Save the retained draft or reload the saved version before generating new personas.');
      fireEvent.click(retainedRetry);

      await waitFor(() => expect(persist).toHaveBeenCalledTimes(3));
      await waitFor(() => expect(screen.queryByText(/Study draft save failed:/)).not.toBeInTheDocument());
      expect(persist.mock.calls[2][0]).toEqual(retainedDraft);
      expect(api.generateStudyPersonasDetailed).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
      expect(pendingStudyDraft('anonymous', original.id)).toBeUndefined();
      expect(screen.getByRole('button', { name: 'Regenerate Personas' })).toBeEnabled();
    } finally {
      view.unmount();
      discardStudyDraft('anonymous', original.id);
    }
  });

  it('blocks overlapping retries and offers recovery again after another failed save', async () => {
    const original = study({ revision: 1 });
    let rejectRetry: (error: Error) => void = () => {};
    const pendingRetry = new Promise<Study>((_resolve, reject) => { rejectRetry = reject; });
    const persist = vi.fn()
      .mockResolvedValueOnce(study({ revision: 2, step: 2 }))
      .mockRejectedValueOnce(new Error('Draft save unavailable'))
      .mockReturnValueOnce(pendingRetry)
      .mockResolvedValueOnce(study({ revision: 3, step: 2 }));
    vi.mocked(api.getStudy).mockResolvedValue(original);
    rememberStudyRevision(original);
    vi.mocked(api.updateStudy).mockImplementation((id, updates) =>
      queueStudyWrite(id, 'anonymous', updates, async () => original, persist));
    const view = renderWorkflow(1);

    try {
      fireEvent.click(await screen.findByRole('button', { name: /^Generate Personas$/i }));
      const retry = await screen.findByRole('button', { name: 'Retry save' });
      await waitFor(() => expect(retry).toBeEnabled());
      fireEvent.click(retry);
      fireEvent.click(retry);
      await waitFor(() => expect(persist).toHaveBeenCalledTimes(3));
      expect(screen.getByRole('button', { name: 'Saving draft' })).toBeDisabled();
      expect(screen.getByRole('button', { name: /Regenerate Personas/i })).toBeDisabled();
      await act(async () => { rejectRetry(new Error('Draft still unavailable')); });

      const nextRetry = await screen.findByRole('button', { name: 'Retry save' });
      await waitFor(() => expect(nextRetry).toBeEnabled());
      expect(screen.getByRole('button', { name: 'Regenerate Personas' })).toBeDisabled();
      fireEvent.click(nextRetry);
      await waitFor(() => expect(persist).toHaveBeenCalledTimes(4));
      await waitFor(() => expect(screen.queryByText(/Study draft save failed:/)).not.toBeInTheDocument());
      expect(api.generateStudyPersonasDetailed).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
    } finally {
      view.unmount();
      discardStudyDraft('anonymous', original.id);
    }
  });

  it('offers reload after browser Back cancels a deferred retry without another step save', async () => {
    const original = study({ revision: 1, step: 2 });
    const saved = study({ revision: 3, step: 2 });
    let finishRetry!: (value: Study) => void;
    const pendingRetry = new Promise<Study>((resolve) => { finishRetry = resolve; });
    const persist = vi.fn()
      .mockResolvedValueOnce(study({ revision: 2, step: 2 }))
      .mockRejectedValueOnce(new Error('Draft save unavailable'))
      .mockReturnValueOnce(pendingRetry);
    vi.mocked(api.getStudy).mockResolvedValue(original);
    rememberStudyRevision(original);
    vi.mocked(api.updateStudy).mockImplementation((id, updates) =>
      queueStudyWrite(id, 'anonymous', updates, async () => original, persist));
    const onStepChange = vi.fn();
    const RoutedWorkflow = () => {
      const { currentPath } = useNavigation();
      return <StudyWorkflowView studyId={original.id} initialStep={currentPath.endsWith('/step1') ? 1 : 2}
        onExit={vi.fn()} onStepChange={onStepChange} />;
    };
    const previousPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    window.history.replaceState({}, '', `/research/${original.id}/step2`);
    const view = render(<NavigationProvider><RoutedWorkflow /></NavigationProvider>);

    try {
      fireEvent.click(await screen.findByRole('button', { name: 'Generate Personas' }));
      const retry = await screen.findByRole('button', { name: 'Retry save' });
      await waitFor(() => expect(retry).toBeEnabled());
      const retainedDraft = pendingStudyDraft('anonymous', original.id);
      fireEvent.click(retry);
      await waitFor(() => expect(persist).toHaveBeenCalledTimes(3));
      expect(screen.getByText('Saving changes...')).toBeInTheDocument();

      act(() => {
        window.history.replaceState({}, '', `/research/${original.id}/step1`);
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      expect(screen.getByRole('textbox', { name: 'Describe your idea or answer the copilot' })).toBeInTheDocument();
      expect(onStepChange).toHaveBeenCalledTimes(1);
      expect(api.updateStudy).toHaveBeenCalledTimes(2);
      await act(async () => { finishRetry(saved); });

      expect(screen.queryByText('Saving changes...')).not.toBeInTheDocument();
      expect(screen.getByText(/Save confirmation was cancelled/).closest('[role="alert"]')).not.toBeNull();
      expect(screen.getByRole('button', { name: 'Reload saved version' })).toBeEnabled();
      expect(pendingStudyDraft('anonymous', original.id)).toEqual(retainedDraft);
      expect(persist).toHaveBeenCalledTimes(3);
      expect(api.generateStudyPersonasDetailed).toHaveBeenCalledTimes(1);

      act(() => {
        window.history.replaceState({}, '', `/research/${original.id}/step2`);
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      expect(screen.getByText('Nusrat Jahan')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Regenerate Personas' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Retry save' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Reload saved version' })).toBeEnabled();
    } finally {
      view.unmount();
      await act(async () => { finishRetry(saved); });
      discardStudyDraft('anonymous', original.id);
      window.history.replaceState({}, '', previousPath);
    }
  });
});

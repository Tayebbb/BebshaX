import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { MAX_PERSONAS_PER_ROLE } from '../src/components/dashboard/views/workflow/types';
import { EvidenceSummary, Persona, PersonaRoleSuggestion, Study } from '../src/types';
import { api } from '../src/services/api';

vi.mock('../src/services/api', () => {
  const stub = {
    getStudy: vi.fn(),
    getStudyReports: vi.fn(),
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

    // Deselect the only active role (the row is a div onClick; the click
    // bubbles up from the role name).
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

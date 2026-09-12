import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { StudyWorkflowView } from '../src/components/dashboard/views/StudyWorkflowView';
import { READ_ONLY_TITLE } from '../src/components/dashboard/views/workflow/types';
import { EvidenceSummary, Study } from '../src/types';
import { api } from '../src/services/api';

vi.mock('../src/services/api', () => {
  const stub = {
    getStudy: vi.fn(),
    getStudyReports: vi.fn(),
    getPendingJobHandle: vi.fn().mockReturnValue(null),
    getPendingStudyDraft: vi.fn().mockReturnValue(undefined),
    getEvidenceSummary: vi.fn(),
    updateStudy: vi.fn(),
    generateStudyPersonas: vi.fn(),
    generateStudyPersonasDetailed: vi.fn(),
    triggerStudyResearch: vi.fn(),
    getConversation: vi.fn(),
  };
  return { api: stub, default: stub };
});

const study = (overrides: Partial<Study>): Study =>
  ({
    id: 'study_demo_01',
    title: 'Coffee Subscriptions in Dhaka',
    type: 'interviews',
    goal: 'demand_validation',
    prompt: 'A demo prompt',
    status: 'completed',
    persona_count: 1,
    persona_ids: ['per_1'],
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    is_demo: true,
    step: 5,
    // A study that reached step 2 always carries its selected roles; without
    // one, Generate is refused client-side before any request (the server
    // 400s an empty role list too), so the 403 path could never be reached.
    suggested_roles: [
      { id: 'role_1', role: 'COFFEE DRINKER', description: 'Core target user.', count: 1, selected: true },
    ],
    personas_data: [{ id: 'per_1', name: 'Sarah Rahman', archetype: 'Founder' }],
    script_questions: ['How do you buy coffee today?'],
    ...overrides,
  } as unknown as Study);

const emptySummary: EvidenceSummary = {
  study_id: 'study_demo_01',
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

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  (api.getStudyReports as any).mockResolvedValue([]);
  (api.getEvidenceSummary as any).mockResolvedValue(emptySummary);
  (api.updateStudy as any).mockResolvedValue({});
  (api.triggerStudyResearch as any).mockResolvedValue({});
});

const renderWorkflow = (initialStep: number, studyId = 'study_demo_01') =>
  render(
    <StudyWorkflowView
      studyId={studyId}
      initialStep={initialStep}
      initialType="interviews"
      initialPrompt=""
      onExit={vi.fn()}
      onStepChange={vi.fn()}
    />
  );

/* ────────────────────────────────────────────────────────────────────────
   Fix 2 — the demo (example) study renders read-only: notice shown, every
   mutating CTA disabled with an explanation, content still viewable.
   ──────────────────────────────────────────────────────────────────────── */

describe('Fix 2 — demo study is read-only in the workflow', () => {
  it('shows the read-only notice and disables persona generation on step 2, keeping content viewable', async () => {
    (api.getStudy as any).mockResolvedValue(study({}));

    renderWorkflow(2);

    await waitFor(() =>
      expect(screen.getByText(/Example study — read-only\./i)).toBeInTheDocument()
    );
    expect(screen.getByText(/Create your own study to run these steps/i)).toBeInTheDocument();

    const regen = screen.getByRole('button', { name: /Regenerate Personas/i });
    expect(regen).toBeDisabled();
    expect(regen).toHaveAttribute('title', READ_ONLY_TITLE);

    // Content stays fully viewable.
    expect(screen.getByText('Sarah Rahman')).toBeInTheDocument();
  });

  it('disables the copilot send box on step 1', async () => {
    (api.getStudy as any).mockResolvedValue(study({}));

    renderWorkflow(2);
    await waitFor(() =>
      expect(screen.getByText(/Example study — read-only\./i)).toBeInTheDocument()
    );
    // Backtrack to step 1 — exactly the judge path that used to expose live CTAs.
    fireEvent.click(screen.getByRole('button', { name: /Context/i }));

    const send = screen.getByLabelText(/Send prompt/i);
    expect(send).toBeDisabled();
    expect(send).toHaveAttribute('title', READ_ONLY_TITLE);
    expect(
      screen.getByPlaceholderText(/Example study — read-only\. Create your own study to chat/i)
    ).toBeDisabled();
    // Read-only studies never expose the evidence-run trigger.
    expect(screen.queryByRole('button', { name: /Run evidence research/i })).toBeNull();
  });

  it('disables interview and report CTAs on step 4', async () => {
    (api.getStudy as any).mockResolvedValue(study({ step: 4 }));

    renderWorkflow(4);
    await waitFor(() =>
      expect(screen.getByText(/Example study — read-only\./i)).toBeInTheDocument()
    );

    const runAll = screen.getByRole('button', { name: /Run All Synthetic Interviews/i });
    expect(runAll).toBeDisabled();
    expect(runAll).toHaveAttribute('title', READ_ONLY_TITLE);
    expect(screen.getByRole('button', { name: /Generate Decision Report/i })).toBeDisabled();
    expect(screen.getByLabelText(/Follow-up interview question/i)).toBeDisabled();
  });

  it('shows no read-only notice and keeps CTAs live for a normal study', async () => {
    (api.getStudy as any).mockResolvedValue(study({ id: 'study_own', is_demo: false, step: 2 }));

    renderWorkflow(2, 'study_own');

    await waitFor(() => expect(screen.getByText('Sarah Rahman')).toBeInTheDocument());
    expect(screen.queryByText(/Example study — read-only\./i)).toBeNull();
    expect(screen.getByRole('button', { name: /Regenerate Personas/i })).toBeEnabled();
  });

  it('renders a 403 write refusal as a calm notice, not a failure alert', async () => {
    (api.getStudy as any).mockResolvedValue(study({ id: 'study_own', is_demo: false, step: 2 }));
    const refusalMsg =
      'This is a read-only example study — create your own study to generate personas.';
    (api.generateStudyPersonasDetailed as any).mockRejectedValue(
      Object.assign(new Error(refusalMsg), { status: 403 })
    );

    renderWorkflow(2, 'study_own');
    await waitFor(() => expect(screen.getByText('Sarah Rahman')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /Regenerate Personas/i }));

    const notice = await screen.findByText(refusalMsg);
    expect(notice.closest('[role="status"]')).not.toBeNull();
    expect(screen.queryByText(/Persona generation failed/i)).toBeNull();
  });
});

/* ────────────────────────────────────────────────────────────────────────
   Fix 6 — step 1's not_run state can start the evidence run directly
   (never for demo studies — covered above).
   ──────────────────────────────────────────────────────────────────────── */

describe('Fix 6 — evidence run can start from step 1', () => {
  it('offers "Run evidence research" in the not_run state and triggers the existing research path', async () => {
    (api.getStudy as any).mockResolvedValue(study({ id: 'study_own', is_demo: false, step: 1 }));

    renderWorkflow(1, 'study_own');

    const runBtn = await screen.findByRole('button', { name: /Run evidence research/i });
    fireEvent.click(runBtn);

    await waitFor(() => expect(api.triggerStudyResearch).toHaveBeenCalledWith('study_own'));
  });
});

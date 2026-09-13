import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BehavioralTestingView } from '../src/components/dashboard/views/BehavioralTestingView';
import { BehavioralTestDetailView } from '../src/components/dashboard/views/BehavioralTestDetailView';
import { BehavioralComparisonView } from '../src/components/dashboard/views/BehavioralComparisonView';
import { CreateBehavioralTestModal } from '../src/components/dashboard/modals/CreateBehavioralTestModal';
import { StartInterviewModal } from '../src/components/dashboard/modals/StartInterviewModal';
import { api } from '../src/services/api';
import {
  BehavioralTest,
  BehavioralTestRun,
  BehavioralMetricsResponse,
  SyntheticPersona,
  MarketSegment,
} from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    getBehavioralTests: vi.fn(),
    getBehavioralMetrics: vi.fn(),
    getBehavioralTestDetail: vi.fn(),
    getBehavioralTestRuns: vi.fn(),
    getBehavioralRunResults: vi.fn(),
    createBehavioralTest: vi.fn(),
    triggerBehavioralTestRun: vi.fn(),
    compareBehavioralRuns: vi.fn(),
    getStudyPersonas: vi.fn(),
    listStudySegments: vi.fn(),
    retryFailedBehavioralRun: vi.fn(),
    startPersonaInterview: vi.fn(),
  },
}));

const mockMetrics: BehavioralMetricsResponse = {
  study_id: 'std_test_1',
  total_tests: 2,
  total_runs: 3,
  completed_runs: 3,
  total_personas_simulated: 6,
  average_buy_likelihood: 0.68,
  average_buy_likelihood_percentage: 68,
};

const mockTest: BehavioralTest = {
  id: 'bt_pricing_1',
  study_id: 'std_test_1',
  name: 'Student Meal App Pricing Test',
  description: 'Evaluate student willingness to pay ৳299/mo for automated meal planning.',
  test_type: 'pricing_test',
  configuration: { price: '৳299', billing_period: 'monthly' },
  status: 'completed',
  scenarios: [
    {
      id: 'sc_1',
      title: 'Monthly Subscription',
      scenario_text: 'Student receives in-app offer for ৳299/mo',
      structured_parameters: { price: '৳299' },
    },
  ],
  run_count: 2,
  latest_run: {
    id: 'run_1',
    status: 'completed',
    persona_count: 2,
    completed_count: 2,
    average_likelihood: 0.68,
  },
};

const mockRun: BehavioralTestRun = {
  id: 'run_1',
  behavioral_test_id: 'bt_pricing_1',
  study_id: 'std_test_1',
  scenario_snapshot: {
    title: 'Monthly Subscription',
    scenario_text: 'Student receives in-app offer for ৳299/mo',
    structured_parameters: { price: '৳299' },
  },
  target_population_type: 'all',
  target_persona_ids: ['p1', 'p2'],
  status: 'completed',
  persona_count: 2,
  completed_count: 2,
  failed_count: 0,
  aggregate_metrics: {
    total_personas: 2,
    positive_count: 1,
    neutral_count: 1,
    negative_count: 0,
    positive_percentage: 50.0,
    neutral_percentage: 50.0,
    negative_percentage: 0.0,
    average_likelihood: 0.68,
    average_likelihood_percentage: 68,
    confidence_breakdown: { high: 2 },
  },
  segment_analysis: [
    {
      segment_id: 'seg_students',
      segment_name: 'Budget-Conscious Students',
      persona_count: 2,
      positive_percentage: 50.0,
      negative_percentage: 0.0,
      average_likelihood: 0.68,
      top_objection: 'High monthly recurring cost',
    },
  ],
  cross_persona_patterns: {
    top_motivators: ['Time savings', 'Healthy diet'],
    top_objections: ['High monthly recurring cost'],
    top_decision_factors: [{ name: 'Price Sensitivity', frequency: 2 }],
  },
  risks: [
    {
      type: 'risk',
      title: 'Price Friction for Low Allowance Students',
      description: '৳299 exceeds typical ৳150 budget ceiling.',
      severity: 'high',
    },
  ],
  opportunities: [
    {
      type: 'opportunity',
      title: 'Exam Season Time-Saving Appeal',
      description: 'High willingness during finals to save cooking time.',
      appeal: 'high',
    },
  ],
  results: [
    {
      id: 'res_1',
      persona_id: 'p1',
      persona_name: 'Nadia Rahman',
      persona_version: 1,
      segment_name: 'Budget-Conscious Students',
      decision: 'likely_to_buy',
      decision_label: 'Likely to Buy',
      probability: 0.72,
      confidence: 'high',
      confidence_score: 0.88,
      key_factors: [
        {
          name: 'Convenience Benefit',
          impact: 'high',
          direction: 'positive',
          description: 'Saves 1 hour daily',
        },
      ],
      motivators: ['Time savings'],
      objections: ['Recurring fee'],
      reasoning_summary: 'Nadia finds the time saving worth the ৳299 budget allocation.',
      simulation_context_sources: {
        persona_profile: true,
        interview_insights: true,
        research_evidence: true,
      },
      interview_signals_used: ['Struggles with hostel meal planning'],
      status: 'completed',
    },
  ],
};

const mockPersonas: SyntheticPersona[] = [
  {
    id: 'p1',
    study_id: 'std_test_1',
    name: 'Nadia Rahman',
    status: 'ready',
    version: 1,
    demographics: { age: 22, occupation: 'Student' },
    commercial_profile: { monthly_budget_bdt: 400 },
    technology_profile: { familiarity: 'High', primary_devices: ['Android'], platforms: ['bKash'] },
    evidence_citations: [],
    goals: ['Save time'],
    needs: ['Affordable food'],
    pain_points: ['No time to cook'],
    behaviors: ['bKash user'],
    preferences: ['Budget friendly'],
    motivations: ['Exam success'],
    objections: ['Cancel if price > 400'],
    dataset_refs: [],
    grounding_score: 0.92,
    confidence: 0.95,
    validation_warnings: [],
    is_synthetic: true,
    created_at: '2026-08-25T20:00:00Z',
  },
];

const mockSegments: MarketSegment[] = [
  {
    id: 'seg_students',
    study_id: 'std_test_1',
    segmentation_run_id: 'srun_1',
    name: 'Budget-Conscious Students',
    cluster_label: 'cluster_0',
    description: 'Hostel students in Dhaka',
    population_count: 450,
    population_percentage: 45,
    confidence_score: 0.92,
    characteristics: {
      demographics: { median_age: 21 },
      economics: { monthly_budget: { min: 200, median: 400, max: 600 } },
    },
    variable_distributions: {},
    evidence_citations: [],
    created_at: '2026-08-25T20:00:00Z',
  },
];

function deferred<Value>() {
  let resolve!: (value: Value) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function activateWithEnter(control: HTMLElement): void {
  expect(control).toHaveFocus();
  const useNativeActivation = fireEvent.keyDown(control, { key: 'Enter', code: 'Enter' });
  if (useNativeActivation && control instanceof HTMLButtonElement && !control.disabled) {
    fireEvent.click(control, { detail: 0 });
  }
  fireEvent.keyUp(control, { key: 'Enter', code: 'Enter' });
}

function selectWithSpace(control: HTMLElement): void {
  expect(control).toBeInstanceOf(HTMLInputElement);
  expect(control).toHaveAttribute('type', 'radio');
  expect(control.tabIndex).toBe(0);
  control.focus();
  expect(control).toHaveFocus();
  const useNativeActivation = fireEvent.keyDown(control, { key: ' ', code: 'Space' });
  fireEvent.keyUp(control, { key: ' ', code: 'Space' });
  if (useNativeActivation && control instanceof HTMLInputElement && !control.disabled) {
    fireEvent.click(control, { detail: 0 });
  }
}

async function configurePricingSimulation(population: 'all' | 'selected_personas' = 'all'): Promise<void> {
  fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
  fireEvent.change(screen.getByLabelText('Test Name'), { target: { value: 'Saved pricing experiment' } });
  fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
  fireEvent.change(screen.getByLabelText('Billing Period'), { target: { value: 'yearly' } });
  fireEvent.change(screen.getByLabelText('Current Alternative Personas Use'), { target: { value: 'Manual planning' } });
  fireEvent.change(screen.getByLabelText(/Detailed Scenario Context/), { target: { value: 'A yearly plan offered during exams.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  await screen.findByText(/Simulate across all 1 synthetic personas/);
  if (population === 'selected_personas') {
    fireEvent.click(screen.getByRole('radio', { name: /Selected Personas/ }));
    expect(screen.getByRole('checkbox', { name: 'Include Nadia Rahman' })).toBeChecked();
  }
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
}

function mockBehavioralDetail(run: BehavioralTestRun = mockRun): void {
  vi.mocked(api.getBehavioralTestDetail).mockResolvedValue(mockTest);
  vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([run]);
  vi.mocked(api.getBehavioralRunResults).mockResolvedValue(run);
}

describe('Part 7: Behavioral Testing & Simulation Frontend Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getStudyPersonas).mockResolvedValue({ personas: mockPersonas, total: 1, represented_segments: 1, average_grounding_score: 0.92 });
    vi.mocked(api.listStudySegments).mockResolvedValue(mockSegments);
  });

  it('opens a behavioral test from its primary action using Enter', async () => {
    vi.mocked(api.getBehavioralTests).mockResolvedValue([mockTest]);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
    const onOpenTest = vi.fn();

    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={onOpenTest} />);

    const openTest = await screen.findByRole('button', { name: /Student Meal App Pricing Test/i });
    expect(openTest).toBeInstanceOf(HTMLButtonElement);
    expect(openTest.querySelector('button')).toBeNull();
    openTest.focus();
    activateWithEnter(openTest);

    expect(onOpenTest).toHaveBeenCalledExactlyOnceWith('bt_pricing_1', 'run_1');
  });

  it('submits a non-default interview objective and depth through native keyboard activation', () => {
    vi.mocked(api.startPersonaInterview).mockImplementation(() => new Promise(() => {}));
    render(
      <StartInterviewModal
        isOpen={true}
        onClose={vi.fn()}
        persona={{ ...mockPersonas[0], generation_run_id: 'generation_1' }}
        studyId="std_test_1"
        onInterviewStarted={vi.fn()}
      />
    );

    const defaultObjective = screen.getByRole('radio', { name: 'Problem & Pain Point Discovery' });
    const pricingObjective = screen.getByRole('radio', { name: 'Pricing & Willingness to Pay' });
    expect(defaultObjective).toBeChecked();
    selectWithSpace(pricingObjective);
    expect(pricingObjective).toBeChecked();
    expect(defaultObjective).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Short Pulse' })).toBeChecked();

    const deepInterview = screen.getByRole('radio', { name: 'Deep Ethnography' });
    selectWithSpace(deepInterview);
    expect(deepInterview).toBeChecked();
    expect(screen.getByRole('radio', { name: 'Short Pulse' })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: 'Standard Discovery' })).not.toBeChecked();

    const startInterview = screen.getByRole('button', { name: 'Start Adaptive Interview' });
    startInterview.focus();
    activateWithEnter(startInterview);

    expect(api.startPersonaInterview).toHaveBeenCalledExactlyOnceWith('std_test_1', 'p1', {
      objective: 'Pricing & Willingness to Pay',
      custom_objective: undefined,
      length_tier: 'deep',
      generation_run_id: 'generation_1',
    });
    expect(screen.getByRole('button', { name: 'Initializing Interview...' })).toBeDisabled();
  });

  it.each(['Cancel', 'Close interview setup dialog', 'Escape'])(
    'ignores an accepted interview after dismissal with %s',
    async (dismissal) => {
      const request = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
      vi.mocked(api.startPersonaInterview).mockReturnValue(request.promise);
      const onClose = vi.fn();
      const onInterviewStarted = vi.fn();
      render(<StartInterviewModal isOpen onClose={onClose} persona={mockPersonas[0]} studyId="std_test_1" onInterviewStarted={onInterviewStarted} />);

      fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
      if (dismissal === 'Escape') {
        fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      } else {
        fireEvent.click(screen.getByRole('button', { name: dismissal }));
      }
      expect(onClose).toHaveBeenCalledTimes(1);

      await act(async () => {
        request.resolve({ id: 'accepted-after-close' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
      });

      expect(onInterviewStarted).not.toHaveBeenCalled();
      expect(onClose).toHaveBeenCalledTimes(1);
    }
  );

  it('ignores an accepted interview after the modal unmounts', async () => {
    const request = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
    vi.mocked(api.startPersonaInterview).mockReturnValue(request.promise);
    const onClose = vi.fn();
    const onInterviewStarted = vi.fn();
    const view = render(<StartInterviewModal isOpen onClose={onClose} persona={mockPersonas[0]} studyId="std_test_1" onInterviewStarted={onInterviewStarted} />);
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
    view.unmount();

    await act(async () => {
      request.resolve({ id: 'accepted-after-unmount' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
    });

    expect(onInterviewStarted).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('keeps a reopened interview request pending when the dismissed request completes', async () => {
    const previous = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
    const current = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
    vi.mocked(api.startPersonaInterview).mockReturnValueOnce(previous.promise).mockReturnValueOnce(current.promise);
    const props = { onClose: vi.fn(), persona: mockPersonas[0], studyId: 'std_test_1', onInterviewStarted: vi.fn() };
    const view = render(<StartInterviewModal {...props} isOpen />);
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    view.rerender(<StartInterviewModal {...props} isOpen={false} />);
    view.rerender(<StartInterviewModal {...props} isOpen />);
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));

    await act(async () => {
      previous.resolve({ id: 'previous' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
    });
    expect(props.onInterviewStarted).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Initializing Interview...' })).toBeDisabled();

    await act(async () => {
      current.resolve({ id: 'current' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
    });
    expect(props.onInterviewStarted).toHaveBeenCalledExactlyOnceWith('current');
    expect(props.onClose).toHaveBeenCalledTimes(2);
  });

  it.each(['study', 'persona'])(
    'ignores an interview completion after the modal %s changes',
    async (owner) => {
      const request = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
      vi.mocked(api.startPersonaInterview).mockReturnValue(request.promise);
      const props = { onClose: vi.fn(), persona: mockPersonas[0], studyId: 'std_test_1', onInterviewStarted: vi.fn() };
      const view = render(<StartInterviewModal {...props} isOpen />);
      fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
      view.rerender(<StartInterviewModal {...props} isOpen studyId={owner === 'study' ? 'other-study' : props.studyId} persona={owner === 'persona' ? { ...mockPersonas[0], id: 'other-persona' } : props.persona} />);

      await act(async () => {
        request.resolve({ id: 'previous-owner' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
      });

      expect(props.onInterviewStarted).not.toHaveBeenCalled();
      expect(props.onClose).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Start Adaptive Interview' })).toBeEnabled();
    }
  );

  it('locks interview choices while starting and preserves them for retry after failure', async () => {
    const request = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
    vi.mocked(api.startPersonaInterview).mockReturnValueOnce(request.promise).mockResolvedValueOnce({ id: 'retried' } as Awaited<ReturnType<typeof api.startPersonaInterview>>);
    const onInterviewStarted = vi.fn();
    render(<StartInterviewModal isOpen onClose={vi.fn()} persona={mockPersonas[0]} studyId="std_test_1" onInterviewStarted={onInterviewStarted} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Custom Research Objective' }));
    const objective = screen.getByRole('textbox', { name: 'Custom research objective' });
    fireEvent.change(objective, { target: { value: '  Explore meal budgets  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));

    expect(objective).toBeDisabled();
    for (const choice of screen.getAllByRole('radio')) expect(choice).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();

    await act(async () => { request.reject(new Error('Interview service unavailable')); });
    expect(screen.getByRole('alert')).toHaveTextContent('Interview service unavailable');
    expect(objective).toHaveValue('  Explore meal budgets  ');
    expect(objective).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
    await waitFor(() => expect(onInterviewStarted).toHaveBeenCalledExactlyOnceWith('retried'));
    expect(vi.mocked(api.startPersonaInterview).mock.calls[1]).toEqual(vi.mocked(api.startPersonaInterview).mock.calls[0]);
  });

  it('does not surface a dismissed interview error in the reopened modal', async () => {
    const request = deferred<Awaited<ReturnType<typeof api.startPersonaInterview>>>();
    vi.mocked(api.startPersonaInterview).mockReturnValue(request.promise);
    const props = { onClose: vi.fn(), persona: mockPersonas[0], studyId: 'std_test_1', onInterviewStarted: vi.fn() };
    const view = render(<StartInterviewModal {...props} isOpen />);
    fireEvent.click(screen.getByRole('button', { name: 'Start Adaptive Interview' }));
    view.rerender(<StartInterviewModal {...props} isOpen={false} />);
    view.rerender(<StartInterviewModal {...props} isOpen />);

    await act(async () => { request.reject(new Error('Dismissed request failed')); });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start Adaptive Interview' })).toBeEnabled();
  });

  it('requires a nonblank custom objective before starting an interview', () => {
    render(<StartInterviewModal isOpen onClose={vi.fn()} persona={mockPersonas[0]} studyId="std_test_1" onInterviewStarted={vi.fn()} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Custom Research Objective' }));
    const objective = screen.getByRole('textbox', { name: 'Custom research objective' });
    const start = screen.getByRole('button', { name: 'Start Adaptive Interview' });
    expect(start).toBeDisabled();
    fireEvent.change(objective, { target: { value: '   ' } });
    expect(start).toBeDisabled();
    fireEvent.change(objective, { target: { value: 'Explore budgets' } });
    expect(start).toBeEnabled();
  });

  it('renders BehavioralTestingView with metrics, tests, and filter controls', async () => {
    vi.mocked(api.getBehavioralTests).mockResolvedValue([mockTest]);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);

    const onOpenTest = vi.fn();
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={onOpenTest} />);

    expect(screen.getByText('Behavioral Testing & Simulation')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Student Meal App Pricing Test')).toBeInTheDocument();
      expect(screen.getAllByText('68%').length).toBeGreaterThan(0);
    });

    const testCard = screen.getByText('Student Meal App Pricing Test');
    fireEvent.click(testCard);
    expect(onOpenTest).toHaveBeenCalledWith('bt_pricing_1', 'run_1');
  });

  it('announces test-list loading and disables duplicate refresh requests', async () => {
    const request = deferred<BehavioralTest[]>();
    vi.mocked(api.getBehavioralTests).mockReturnValue(request.promise);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
    expect(screen.getByRole('status', { name: 'Loading behavioral tests' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(api.getBehavioralTests).toHaveBeenCalledTimes(1);
    await act(async () => { request.resolve([mockTest]); });
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled();
    expect(screen.queryByRole('status', { name: 'Loading behavioral tests' })).not.toBeInTheDocument();
  });

  it('submits behavioral search, type, and status filters and refreshes the same selection', async () => {
    vi.mocked(api.getBehavioralTests).mockResolvedValue([mockTest]);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
    await screen.findByRole('button', { name: `View Results: ${mockTest.name}` });
    const search = screen.getByRole('textbox', { name: 'Search behavioral tests' });
    fireEvent.change(search, { target: { value: 'Meal' } });
    fireEvent.submit(search.closest('form')!);
    await waitFor(() => expect(api.getBehavioralTests).toHaveBeenLastCalledWith('std_test_1', 'Meal', 'all', 'all'));
    fireEvent.change(screen.getByRole('combobox', { name: 'Test type' }), { target: { value: 'pricing_test' } });
    await waitFor(() => expect(api.getBehavioralTests).toHaveBeenLastCalledWith('std_test_1', 'Meal', 'pricing_test', 'all'));
    fireEvent.change(screen.getByRole('combobox', { name: 'Test status' }), { target: { value: 'completed' } });
    await waitFor(() => expect(api.getBehavioralTests).toHaveBeenLastCalledWith('std_test_1', 'Meal', 'pricing_test', 'completed'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Refresh' })).toBeEnabled());
    const requestCount = vi.mocked(api.getBehavioralTests).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(api.getBehavioralTests).toHaveBeenCalledTimes(requestCount + 1));
    expect(api.getBehavioralTests).toHaveBeenLastCalledWith('std_test_1', 'Meal', 'pricing_test', 'completed');
  });

  it('shows a failed test list as unavailable instead of empty and recovers on retry', async () => {
    vi.mocked(api.getBehavioralTests).mockRejectedValueOnce(new Error('Tests unavailable')).mockResolvedValueOnce([mockTest]);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Tests unavailable');
    expect(screen.queryByText('No Behavioral Tests Created Yet')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await screen.findByRole('button', { name: `View Results: ${mockTest.name}` });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('distinguishes an empty filtered list from a study without tests', async () => {
    vi.mocked(api.getBehavioralTests).mockResolvedValueOnce([mockTest]).mockResolvedValue([]);
    vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
    await screen.findByRole('button', { name: `View Results: ${mockTest.name}` });
    fireEvent.change(screen.getByRole('combobox', { name: 'Test type' }), { target: { value: 'feature_test' } });
    expect(await screen.findByText('No Matching Behavioral Tests')).toBeInTheDocument();
    expect(screen.queryByText('No Behavioral Tests Created Yet')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create First Behavioral Test' })).not.toBeInTheDocument();
  });

  it('keeps tests usable when metrics fail and recovers metrics on refresh', async () => {
    vi.mocked(api.getBehavioralTests).mockResolvedValue([mockTest]);
    vi.mocked(api.getBehavioralMetrics).mockRejectedValueOnce(new Error('Metrics unavailable')).mockResolvedValueOnce(mockMetrics);
    render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Behavioral metrics unavailable');
    expect(screen.getByRole('button', { name: `View Results: ${mockTest.name}` })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(api.getBehavioralMetrics).toHaveBeenCalledTimes(2);
  });

  it.each(['New Behavioral Test', 'Create First Behavioral Test'])(
    'opens setup from %s and keeps focus on its trigger after closing',
    async (action) => {
      vi.mocked(api.getBehavioralTests).mockResolvedValue([]);
      vi.mocked(api.getBehavioralMetrics).mockResolvedValue(mockMetrics);
      render(<BehavioralTestingView studyId="std_test_1" onOpenTest={vi.fn()} />);
      await screen.findByText('No Behavioral Tests Created Yet');
      const open = screen.getByRole('button', { name: action });
      open.focus();
      activateWithEnter(open);
      expect(screen.getByRole('dialog', { name: 'New Behavioral Simulation' })).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Close new behavioral simulation dialog' }));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(open).toHaveFocus();
    }
  );

  it('handles 4-step wizard in CreateBehavioralTestModal', async () => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: mockPersonas,
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0.92,
    });
    vi.mocked(api.listStudySegments).mockResolvedValue(mockSegments);
    vi.mocked(api.createBehavioralTest).mockResolvedValue(mockTest);
    vi.mocked(api.triggerBehavioralTestRun).mockResolvedValue(mockRun);

    const onClose = vi.fn();
    const onTestCreated = vi.fn();

    render(
      <CreateBehavioralTestModal
        isOpen={true}
        onClose={onClose}
        studyId="std_test_1"
        onTestCreated={onTestCreated}
      />
    );

    expect(screen.getByText('New Behavioral Simulation')).toBeInTheDocument();
    expect(screen.getByText(/Choose Test Type/i)).toBeInTheDocument();

    // Step 1 -> Select Pricing Sensitivity card
    const pricingCard = screen.getByText('Pricing Sensitivity');
    fireEvent.click(pricingCard);

    // Step 2 -> Configure Scenario
    await waitFor(() => {
      expect(screen.getByText(/Configure Scenario/i)).toBeInTheDocument();
      expect(screen.getByText(/Proposed Price/i)).toBeInTheDocument();
    });

    // No unrelated prefilled scenario: the price is required before continuing.
    const priceInput = screen.getByLabelText(/Proposed Price/i);
    expect(priceInput).toHaveValue('');
    const continueBtn = screen.getByRole('button', { name: /Continue/ });
    expect(continueBtn).toBeDisabled();
    fireEvent.click(continueBtn);
    expect(screen.queryByText(/Select Population/i)).not.toBeInTheDocument();

    fireEvent.change(priceInput, { target: { value: '৳600' } });
    expect(continueBtn).toBeEnabled();
    fireEvent.click(continueBtn);

    // Step 3 -> Select Population
    await waitFor(() => {
      expect(screen.getByText(/Select Population/i)).toBeInTheDocument();
      expect(screen.getByText('All Personas in Study')).toBeInTheDocument();
    });

    const continueBtn2 = screen.getByText('Continue');
    fireEvent.click(continueBtn2);

    // Step 4 -> Preview & Verification
    await waitFor(() => {
      expect(screen.getByText(/Preview & Confirm/i)).toBeInTheDocument();
      expect(screen.getByText('Synthetic Simulation')).toBeInTheDocument();
    });

    const runBtn = screen.getByText('Run Simulation');
    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(api.createBehavioralTest).toHaveBeenCalled();
      expect(api.triggerBehavioralTestRun).toHaveBeenCalled();
      expect(onTestCreated).toHaveBeenCalledWith('bt_pricing_1', 'run_1');
    });
    expect(vi.mocked(api.createBehavioralTest).mock.calls[0][1]).toMatchObject({
      test_type: 'pricing_test',
      configuration: expect.objectContaining({ price: '৳600' }),
    });
  });

  it('retries only the saved behavioral run with the original configuration after start fails', async () => {
    vi.mocked(api.createBehavioralTest).mockResolvedValue(mockTest);
    vi.mocked(api.triggerBehavioralTestRun).mockRejectedValueOnce(new Error('Run unavailable')).mockResolvedValueOnce(mockRun);
    const onTestCreated = vi.fn();
    const onClose = vi.fn();
    render(<CreateBehavioralTestModal isOpen onClose={onClose} studyId="std_test_1" onTestCreated={onTestCreated} />);
    await configurePricingSimulation('selected_personas');
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    await screen.findByRole('alert');
    expect(onTestCreated).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /^(Run Simulation|Retry Run)$/ }));

    await waitFor(() => expect(onTestCreated).toHaveBeenCalledExactlyOnceWith(mockTest.id, mockRun.id));
    expect(api.createBehavioralTest).toHaveBeenCalledTimes(1);
    expect(api.triggerBehavioralTestRun).toHaveBeenCalledTimes(2);
    const firstRequest = vi.mocked(api.triggerBehavioralTestRun).mock.calls[0];
    expect(firstRequest[2]).toMatchObject({
      scenario_title: 'Saved pricing experiment',
      scenario_text: 'A yearly plan offered during exams.',
      parameters: { price: '600', billing_period: 'yearly', alternative: 'Manual planning' },
      target_population_type: 'selected_personas',
      target_persona_ids: ['p1'],
    });
    expect(vi.mocked(api.triggerBehavioralTestRun).mock.calls[1]).toEqual(firstRequest);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('locks a saved simulation configuration and lets the researcher open the saved test after run failure', async () => {
    vi.mocked(api.createBehavioralTest).mockResolvedValue(mockTest);
    vi.mocked(api.triggerBehavioralTestRun).mockRejectedValue(new Error('Run unavailable'));
    const onTestCreated = vi.fn();
    const onClose = vi.fn();
    render(<CreateBehavioralTestModal isOpen onClose={onClose} studyId="std_test_1" onTestCreated={onTestCreated} />);
    await configurePricingSimulation();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/test saved.*run.*failed/i);
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Retry Run' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Open Saved Test' }));
    expect(onTestCreated).toHaveBeenCalledExactlyOnceWith(mockTest.id);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(api.createBehavioralTest).toHaveBeenCalledTimes(1);
  });

  it('preserves editable configuration and retries creation when the test was not saved', async () => {
    vi.mocked(api.createBehavioralTest).mockRejectedValueOnce(new Error('Save unavailable')).mockResolvedValueOnce(mockTest);
    vi.mocked(api.triggerBehavioralTestRun).mockResolvedValue(mockRun);
    const onTestCreated = vi.fn();
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={onTestCreated} />);
    await configurePricingSimulation();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/test.*not.*saved/i);
    expect(api.triggerBehavioralTestRun).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Back' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Open Saved Test' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    await waitFor(() => expect(onTestCreated).toHaveBeenCalledExactlyOnceWith(mockTest.id, mockRun.id));
    expect(api.createBehavioralTest).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.createBehavioralTest).mock.calls[1]).toEqual(vi.mocked(api.createBehavioralTest).mock.calls[0]);
  });

  it.each([
    ['create', 'Close new behavioral simulation dialog'],
    ['create', 'Cancel'],
    ['create', 'Escape'],
    ['create', 'backdrop'],
    ['run', 'Close new behavioral simulation dialog'],
    ['run', 'Cancel'],
    ['run', 'Escape'],
    ['run', 'backdrop'],
  ])('ignores completion of the %s request after dismissal with %s', async (phase, dismissal) => {
    const createRequest = deferred<BehavioralTest>();
    const runRequest = deferred<BehavioralTestRun>();
    vi.mocked(api.createBehavioralTest).mockReturnValue(phase === 'create' ? createRequest.promise : Promise.resolve(mockTest));
    vi.mocked(api.triggerBehavioralTestRun).mockReturnValue(runRequest.promise);
    const onTestCreated = vi.fn();
    const onClose = vi.fn();
    render(<CreateBehavioralTestModal isOpen onClose={onClose} studyId="std_test_1" onTestCreated={onTestCreated} />);
    await configurePricingSimulation();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    if (phase === 'run') await waitFor(() => expect(api.triggerBehavioralTestRun).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Starting Simulation...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
    if (dismissal === 'Escape') {
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    } else if (dismissal === 'backdrop') {
      fireEvent.click(screen.getByRole('dialog').parentElement!);
    } else {
      fireEvent.click(screen.getByRole('button', { name: dismissal }));
    }
    expect(onClose).toHaveBeenCalledTimes(1);

    await act(async () => {
      createRequest.resolve(mockTest);
      runRequest.resolve(mockRun);
    });

    expect(onTestCreated).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(api.triggerBehavioralTestRun).toHaveBeenCalledTimes(phase === 'create' ? 0 : 1);
  });

  it.each([
    ['create', 'unmount'], ['run', 'unmount'],
    ['create', 'study'], ['run', 'study'],
    ['create', 'persona'], ['run', 'persona'],
  ])('ignores a pending %s completion after simulation owner %s changes', async (phase, departure) => {
    const createRequest = deferred<BehavioralTest>();
    const runRequest = deferred<BehavioralTestRun>();
    vi.mocked(api.createBehavioralTest).mockReturnValue(phase === 'create' ? createRequest.promise : Promise.resolve(mockTest));
    vi.mocked(api.triggerBehavioralTestRun).mockReturnValue(runRequest.promise);
    const props = { onClose: vi.fn(), onTestCreated: vi.fn(), studyId: 'std_test_1' };
    const view = render(<CreateBehavioralTestModal {...props} isOpen />);
    await configurePricingSimulation();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    if (phase === 'run') await waitFor(() => expect(api.triggerBehavioralTestRun).toHaveBeenCalledTimes(1));
    if (departure === 'unmount') view.unmount();
    else view.rerender(<CreateBehavioralTestModal {...props} isOpen studyId={departure === 'study' ? 'next-study' : props.studyId} initialPersonaId={departure === 'persona' ? 'p1' : undefined} />);
    await act(async () => {
      createRequest.resolve(mockTest);
      runRequest.resolve(mockRun);
    });
    expect(props.onTestCreated).not.toHaveBeenCalled();
    expect(props.onClose).not.toHaveBeenCalled();
    expect(api.triggerBehavioralTestRun).toHaveBeenCalledTimes(phase === 'create' ? 0 : 1);
  });

  it('discards population data that arrives after the study changes', async () => {
    const previous = deferred<Awaited<ReturnType<typeof api.getStudyPersonas>>>();
    vi.mocked(api.getStudyPersonas).mockReturnValueOnce(previous.promise).mockResolvedValueOnce({ personas: [], total: 0, represented_segments: 0, average_grounding_score: 0 });
    const props = { onClose: vi.fn(), onTestCreated: vi.fn() };
    const view = render(<CreateBehavioralTestModal {...props} isOpen studyId="previous-study" />);
    view.rerender(<CreateBehavioralTestModal {...props} isOpen studyId="current-study" />);
    await act(async () => { previous.resolve({ personas: mockPersonas, total: 1, represented_segments: 1, average_grounding_score: 0.92 }); });
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
    fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText(/Simulate across all 0 synthetic personas/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('opens a fresh simulation wizard without a dismissed request error', async () => {
    const request = deferred<BehavioralTest>();
    vi.mocked(api.createBehavioralTest).mockReturnValue(request.promise);
    const props = { onClose: vi.fn(), studyId: 'std_test_1', onTestCreated: vi.fn() };
    const view = render(<CreateBehavioralTestModal {...props} isOpen />);
    await configurePricingSimulation();
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }));
    view.rerender(<CreateBehavioralTestModal {...props} isOpen={false} />);
    view.rerender(<CreateBehavioralTestModal {...props} isOpen />);

    await act(async () => { request.reject(new Error('Dismissed save failed')); });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Pricing Sensitivity' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
    expect(screen.getByLabelText(/Proposed Price/)).toHaveValue('');
    expect(props.onTestCreated).not.toHaveBeenCalled();
  });

  it('announces population loading and blocks confirmation until the population is available', async () => {
    const request = deferred<Awaited<ReturnType<typeof api.getStudyPersonas>>>();
    vi.mocked(api.getStudyPersonas).mockReturnValue(request.promise);
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
    fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(screen.getByRole('status')).toHaveTextContent(/loading population/i);
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    await act(async () => { request.resolve({ personas: mockPersonas, total: 1, represented_segments: 1, average_grounding_score: 0.92 }); });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled();
  });

  it('announces population errors and reloads the population on explicit retry', async () => {
    vi.mocked(api.getStudyPersonas).mockRejectedValueOnce(new Error('Population unavailable')).mockResolvedValueOnce({ personas: mockPersonas, total: 1, represented_segments: 1, average_grounding_score: 0.92 });
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Population unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry Population' }));
    await configurePricingSimulation();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.getStudyPersonas).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Run Simulation' })).toBeEnabled();
  });

  it.each(['All Personas in Study', 'Specific Market Segment', 'Selected Personas'])(
    'blocks an empty %s target before preview',
    async (population) => {
      vi.mocked(api.getStudyPersonas).mockResolvedValue({ personas: [], total: 0, represented_segments: 0, average_grounding_score: 0 });
      vi.mocked(api.listStudySegments).mockResolvedValue([]);
      render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
      fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
      fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
      fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
      await act(async () => {});
      fireEvent.click(screen.getByRole('radio', { name: new RegExp(population) }));

      expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
      expect(api.createBehavioralTest).not.toHaveBeenCalled();
    }
  );

  it('does not substitute every persona when a selected segment has no members', async () => {
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
    fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByText(/Simulate across all 1 synthetic personas/);
    fireEvent.click(screen.getByRole('radio', { name: /Specific Market Segment/ }));
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    expect(screen.getByText(/no personas.*selected segment/i)).toBeInTheDocument();
  });

  it('keeps a missing initial persona target empty instead of silently choosing the whole study', async () => {
    render(<CreateBehavioralTestModal isOpen initialPersonaId="missing-persona" onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole('radio', { name: 'Pricing Sensitivity' }));
    fireEvent.change(screen.getByLabelText(/Proposed Price/), { target: { value: '600' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByText(/Simulate across all 1 synthetic personas/);
    expect(screen.getByRole('radio', { name: /Selected Personas/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Include Nadia Rahman' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it.each([
    ['Feature Utility', /Feature Name/],
    ['Marketing Copy', /Marketing Headline/],
    ['Purchase Decision', /Detailed Scenario Context/],
    ['Product Concept', /Detailed Scenario Context/],
    ['Promotional Offer', /Detailed Scenario Context/],
    ['Competitor Switching', /Detailed Scenario Context/],
    ['Adoption Barriers', /Detailed Scenario Context/],
  ])('requires scenario input for %s and keeps it when moving back', async (testType, field) => {
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    const typeControl = screen.getByRole('radio', { name: testType as string });
    typeControl.focus();
    fireEvent.keyDown(typeControl, { key: ' ', code: 'Space' });
    const input = screen.getByLabelText(field as RegExp);
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    fireEvent.change(input, { target: { value: 'Specific research scenario' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    await screen.findByText(/Simulate across all 1 synthetic personas/);
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(screen.getByLabelText(field as RegExp)).toHaveValue('Specific research scenario');
  });

  it('uses neutral simulation-modal surfaces without decorative gradients or colored glow', async () => {
    render(<CreateBehavioralTestModal isOpen onClose={vi.fn()} studyId="std_test_1" onTestCreated={vi.fn()} />);
    await configurePricingSimulation();
    const dialog = screen.getByRole('dialog');
    const surfaces = [dialog, ...dialog.querySelectorAll<HTMLElement>('[style]')];
    expect(surfaces.some((surface) => /gradient|blur\(/.test(surface.getAttribute('style') || ''))).toBe(false);
    expect(surfaces.some((surface) => /0 0 (15|20|30)px/.test(surface.style.boxShadow))).toBe(false);
  });

  it.each(['all', 'segment', 'selected_personas'] as const)(
    'reruns the selected saved scenario with its original %s target',
    async (populationType) => {
      const selectedRun: BehavioralTestRun = {
        ...mockRun,
        id: 'selected-run',
        scenario_id: 'sc_2',
        scenario_snapshot: { title: 'Recorded annual offer', scenario_text: 'An annual exam-season offer.', structured_parameters: { price: '900', billing_period: 'yearly' } },
        target_population_type: populationType,
        target_segment_id: populationType === 'segment' ? 'saved-segment' : null,
        target_persona_ids: ['saved-persona'],
      };
      mockBehavioralDetail(selectedRun);
      vi.mocked(api.getBehavioralTestDetail).mockResolvedValue({ ...mockTest, scenarios: [...mockTest.scenarios, { id: 'sc_2', title: 'Edited later', scenario_text: 'A changed scenario', structured_parameters: { price: '1500' } }] });
      vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([mockRun, selectedRun]);
      vi.mocked(api.triggerBehavioralTestRun).mockReturnValue(new Promise(() => {}));
      render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} initialRunId={selectedRun.id} onBack={vi.fn()} />);

      fireEvent.click(await screen.findByRole('button', { name: 'Re-Run Simulation' }));

      const target = populationType === 'segment' ? { target_segment_id: 'saved-segment' }
        : populationType === 'selected_personas' ? { target_persona_ids: ['saved-persona'] } : {};
      expect(api.triggerBehavioralTestRun).toHaveBeenCalledExactlyOnceWith('std_test_1', mockTest.id, {
        scenario_title: selectedRun.scenario_snapshot.title,
        scenario_text: selectedRun.scenario_snapshot.scenario_text,
        parameters: selectedRun.scenario_snapshot.structured_parameters,
        target_population_type: populationType,
        ...target,
      }, expect.any(AbortSignal));
      expect(screen.getByRole('button', { name: 'Starting...' })).toBeDisabled();
      expect(screen.getByRole('button', { name: /Run #2/ })).toBeDisabled();
    }
  );

  it.each<[string, Partial<BehavioralTestRun>]>([
    ['missing scenario', { scenario_snapshot: {} }],
    ['blank scenario', { scenario_snapshot: { scenario_text: '   ', structured_parameters: {} } }],
    ['missing parameters', { scenario_snapshot: { scenario_text: 'Recorded offer' } }],
    ['missing segment', { target_population_type: 'segment', target_segment_id: null }],
    ['blank segment', { target_population_type: 'segment', target_segment_id: '  ' }],
    ['empty selected personas', { target_population_type: 'selected_personas', target_persona_ids: [] }],
    ['blank persona ID', { target_population_type: 'selected_personas', target_persona_ids: ['  '] }],
  ])('refuses rerun with %s and offers an explicit return to configuration', async (_condition, override) => {
    mockBehavioralDetail({ ...mockRun, ...override });
    const onBack = vi.fn();
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={onBack} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Re-Run Simulation' }));

    expect(api.triggerBehavioralTestRun).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/saved.*configuration/i);
    expect(screen.getByRole('alert')).toHaveTextContent(/configure a new simulation/i);
    fireEvent.click(screen.getByRole('button', { name: 'Back to Behavioral Tests' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('does not enable rerun for a test without a saved run', async () => {
    mockBehavioralDetail();
    vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([]);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    expect(await screen.findByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
    expect(screen.getByText(/no saved runs/i)).toBeInTheDocument();
    expect(api.triggerBehavioralTestRun).not.toHaveBeenCalled();
  });

  it('announces loading when switching runs and prevents rerun of the previous experiment', async () => {
    mockBehavioralDetail();
    const nextRun = { ...mockRun, id: 'next-run' };
    const request = deferred<BehavioralTestRun>();
    vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([mockRun, nextRun]);
    vi.mocked(api.getBehavioralRunResults).mockResolvedValueOnce(mockRun).mockReturnValueOnce(request.promise);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run #1/ }));

    expect(screen.getByRole('status')).toHaveTextContent(/loading run/i);
    expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
    await act(async () => { request.resolve(nextRun); });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run #1/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeEnabled();
  });

  it('retries a failed initial detail load and clears the error after recovery', async () => {
    mockBehavioralDetail();
    vi.mocked(api.getBehavioralTestDetail).mockRejectedValueOnce(new Error('Detail unavailable')).mockResolvedValueOnce(mockTest);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: mockTest.name })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('retries loading the selected run after its result request fails', async () => {
    mockBehavioralDetail();
    vi.mocked(api.getBehavioralRunResults).mockRejectedValueOnce(new Error('Results unavailable')).mockResolvedValueOnce(mockRun);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('button', { name: 'Open reasoning for Nadia Rahman' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('resumes serial polling after four 503 failures and Retry returns the same running run', async () => {
    vi.useFakeTimers();
    const runningRun: BehavioralTestRun = { ...mockRun, status: 'running', completed_count: 0, results: [] };
    const nextPoll = deferred<BehavioralTestRun>();
    const unavailable = Object.assign(new Error('Updates temporarily unavailable'), { status: 503 });
    mockBehavioralDetail(runningRun);
    const readResults = vi.mocked(api.getBehavioralRunResults)
      .mockResolvedValueOnce(runningRun)
      .mockRejectedValueOnce(unavailable)
      .mockRejectedValueOnce(unavailable)
      .mockRejectedValueOnce(unavailable)
      .mockRejectedValueOnce(unavailable)
      .mockResolvedValueOnce(runningRun)
      .mockReturnValueOnce(nextPoll.promise)
      .mockResolvedValue(mockRun);
    const view = render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);

    try {
      await act(async () => {});
      await act(async () => { await vi.advanceTimersByTimeAsync(7500); });
      expect(readResults).toHaveBeenCalledTimes(5);
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(readResults).toHaveBeenCalledTimes(5);

      await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })); });
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
      expect(screen.queryByRole('button', { name: 'Open reasoning for Nadia Rahman' })).not.toBeInTheDocument();
      const readsWhilePending = readResults.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(readResults).toHaveBeenCalledTimes(readsWhilePending);

      await act(async () => { nextPoll.resolve(runningRun); });
      await act(async () => { await vi.advanceTimersByTimeAsync(2500); });
      expect(screen.getByRole('button', { name: 'Open reasoning for Nadia Rahman' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeEnabled();
      expect(readResults).toHaveBeenCalledTimes(8);
      await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
      expect(readResults).toHaveBeenCalledTimes(8);
      expect(api.triggerBehavioralTestRun).not.toHaveBeenCalled();
      expect(api.retryFailedBehavioralRun).not.toHaveBeenCalled();
    } finally {
      view.unmount();
      vi.useRealTimers();
    }
  });

  it.each(['study', 'test', 'run', 'unmount'] as const)(
    'aborts retried polling and ignores late results after the %s changes',
    async (owner) => {
      vi.useFakeTimers();
      const runningRun: BehavioralTestRun = { ...mockRun, status: 'running', completed_count: 0, results: [] };
      const nextRun: BehavioralTestRun = {
        ...mockRun,
        id: owner === 'run' ? 'next-run' : mockRun.id,
        study_id: owner === 'study' ? 'next-study' : mockRun.study_id,
        behavioral_test_id: owner === 'test' ? 'next-test' : mockRun.behavioral_test_id,
        results: [{ ...mockRun.results![0], id: 'current-result', persona_name: 'Current persona' }],
      };
      const stalePoll = deferred<BehavioralTestRun>();
      const unavailable = Object.assign(new Error('Updates temporarily unavailable'), { status: 503 });
      mockBehavioralDetail(runningRun);
      if (owner === 'run') vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([runningRun, nextRun]);
      const readResults = vi.mocked(api.getBehavioralRunResults)
        .mockResolvedValueOnce(runningRun)
        .mockRejectedValueOnce(unavailable)
        .mockRejectedValueOnce(unavailable)
        .mockRejectedValueOnce(unavailable)
        .mockRejectedValueOnce(unavailable)
        .mockResolvedValueOnce(runningRun)
        .mockReturnValueOnce(stalePoll.promise)
        .mockResolvedValue(nextRun);
      const props = { studyId: mockRun.study_id, testId: mockTest.id, initialRunId: mockRun.id, onBack: vi.fn() };
      const view = render(<BehavioralTestDetailView {...props} />);

      try {
        await act(async () => {});
        await act(async () => { await vi.advanceTimersByTimeAsync(7500); });
        expect(readResults).toHaveBeenCalledTimes(5);
        await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })); });
        expect(readResults).toHaveBeenCalledTimes(7);
        const pollingSignal = readResults.mock.calls[6][2]!;
        expect(pollingSignal.aborted).toBe(false);

        vi.mocked(api.getBehavioralTestDetail).mockResolvedValue({ ...mockTest, id: nextRun.behavioral_test_id, study_id: nextRun.study_id });
        vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([nextRun]);
        await act(async () => {
          if (owner === 'unmount') view.unmount();
          else if (owner === 'run') fireEvent.click(screen.getByRole('button', { name: /Run #1/ }));
          else view.rerender(<BehavioralTestDetailView {...props} studyId={nextRun.study_id} testId={nextRun.behavioral_test_id} />);
        });
        expect(pollingSignal.aborted).toBe(true);

        await act(async () => {
          stalePoll.resolve({ ...mockRun, results: [{ ...mockRun.results![0], persona_name: 'Stale persona' }] });
        });
        expect(screen.queryByRole('button', { name: 'Open reasoning for Stale persona' })).not.toBeInTheDocument();
        expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        if (owner !== 'unmount') expect(screen.getByRole('button', { name: 'Open reasoning for Current persona' })).toBeInTheDocument();
        const readsAfterChange = readResults.mock.calls.length;
        await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
        expect(readResults).toHaveBeenCalledTimes(readsAfterChange);
      } finally {
        view.unmount();
        vi.useRealTimers();
      }
    }
  );

  it('locks conflicting run actions during a failed-persona retry and clears a recovered start error', async () => {
    const failedRun = { ...mockRun, status: 'completed_with_warnings' as const, failed_count: 1 };
    mockBehavioralDetail(failedRun);
    const retryRequest = deferred<BehavioralTestRun>();
    vi.mocked(api.retryFailedBehavioralRun).mockReturnValue(retryRequest.promise);
    vi.mocked(api.triggerBehavioralTestRun).mockRejectedValueOnce(new Error('Start unavailable')).mockResolvedValueOnce(mockRun);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Retry Failed Simulations' }));
    expect(screen.getByRole('button', { name: 'Retrying...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeDisabled();
    await act(async () => { retryRequest.reject(new Error('Retry unavailable')); });
    expect(screen.getByRole('alert')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Re-Run Simulation' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Re-Run Simulation' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeEnabled());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.retryFailedBehavioralRun).toHaveBeenCalledExactlyOnceWith('std_test_1', mockRun.id, expect.any(AbortSignal));
  });

  it('offers failed-persona retry even when a failed run has no aggregate metrics', async () => {
    mockBehavioralDetail({ ...mockRun, status: 'failed', failed_count: 2, aggregate_metrics: null as unknown as BehavioralTestRun['aggregate_metrics'] });
    vi.mocked(api.retryFailedBehavioralRun).mockResolvedValue(mockRun);
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Retry Failed Simulations' }));
    await waitFor(() => expect(api.retryFailedBehavioralRun).toHaveBeenCalledTimes(1));
  });

  it.each(['Enter', 'Space'])('opens a native reasoning button with %s and restores focus on dismissal', async (key) => {
    mockBehavioralDetail();
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    const result = await screen.findByRole('button', { name: 'Open reasoning for Nadia Rahman' });
    expect(result).toBeInstanceOf(HTMLButtonElement);
    expect(result).toHaveAttribute('aria-haspopup', 'dialog');
    result.focus();
    if (key === 'Enter') activateWithEnter(result);
    else {
      fireEvent.keyDown(result, { key: ' ', code: 'Space' });
      fireEvent.keyUp(result, { key: ' ', code: 'Space' });
      fireEvent.click(result, { detail: 0 });
    }
    const dialog = screen.getByRole('dialog', { name: /Nadia Rahman.*Behavioral Evaluation/ });
    expect(dialog).toHaveTextContent(mockRun.results![0].reasoning_summary);
    const close = screen.getByRole('button', { name: 'Close behavioral evaluation' });
    await waitFor(() => expect(close).toHaveFocus());
    if (key === 'Enter') fireEvent.click(close);
    else fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(result).toHaveFocus();
  });

  it('keeps reasoning open on content click and restores focus when the backdrop closes it', async () => {
    mockBehavioralDetail();
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    const result = await screen.findByRole('button', { name: 'Open reasoning for Nadia Rahman' });
    result.focus();
    fireEvent.click(result);
    fireEvent.click(screen.getByRole('dialog'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('persona-modal'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(result).toHaveFocus();
  });

  it('retains semantic decision labels on neutral detail and reasoning surfaces', async () => {
    mockBehavioralDetail();
    const { container } = render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} />);
    fireEvent.click(await screen.findByTestId('persona-result-card'));
    const styled = [...container.querySelectorAll<HTMLElement>('[style]')];
    expect(styled.some((surface) => /linear-gradient|blur\(/.test(surface.getAttribute('style') || ''))).toBe(false);
    expect(styled.some((surface) => surface.style.boxShadow.includes('0 0 15px'))).toBe(false);
    expect(screen.getAllByText('Likely to Buy').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Identified Risks & Friction' }).parentElement!.parentElement!.style.backgroundColor).toBe('var(--bg-card)');
    expect(screen.getByRole('heading', { name: 'Opportunities & Drivers' }).parentElement!.parentElement!.style.backgroundColor).toBe('var(--bg-card)');
  });

  it('renders BehavioralTestDetailView with results, risks, opportunities, and persona drawer', async () => {
    vi.mocked(api.getBehavioralTestDetail).mockResolvedValue(mockTest);
    vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([mockRun]);
    vi.mocked(api.getBehavioralRunResults).mockResolvedValue(mockRun);

    const onBack = vi.fn();

    render(
      <BehavioralTestDetailView
        studyId="std_test_1"
        testId="bt_pricing_1"
        initialRunId="run_1"
        onBack={onBack}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Student Meal App Pricing Test')).toBeInTheDocument();
      expect(screen.getAllByText('68%').length).toBeGreaterThan(0);
      expect(screen.getByText('Identified Risks & Friction')).toBeInTheDocument();
      expect(screen.getByText('Price Friction for Low Allowance Students')).toBeInTheDocument();
      expect(screen.getByText('Opportunities & Drivers')).toBeInTheDocument();
      expect(screen.getByText('Exam Season Time-Saving Appeal')).toBeInTheDocument();
      expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
    });

    // Click persona to open modal drawer
    const personaCard = screen.getByTestId('persona-result-card');
    fireEvent.click(personaCard);

    await waitFor(() => {
      expect(screen.getByTestId('persona-modal')).toBeInTheDocument();
      expect(screen.getByText(/Nadia Rahman — Behavioral Evaluation/i)).toBeInTheDocument();
      expect(screen.getByText(/Simulated Persona Reasoning/i)).toBeInTheDocument();
    });
  });

  it('compares all listed run IDs through the detail comparison control', async () => {
    mockBehavioralDetail();
    vi.mocked(api.getBehavioralTestRuns).mockResolvedValue([mockRun, { ...mockRun, id: 'run_2' }]);
    const onCompareRuns = vi.fn();
    render(<BehavioralTestDetailView studyId="std_test_1" testId={mockTest.id} onBack={vi.fn()} onCompareRuns={onCompareRuns} />);
    const compare = await screen.findByRole('button', { name: 'Compare Runs (2)' });
    compare.focus();
    activateWithEnter(compare);
    expect(onCompareRuns).toHaveBeenCalledExactlyOnceWith(['run_1', 'run_2']);
  });

  it('announces comparison loading and keeps the back control available', async () => {
    vi.mocked(api.compareBehavioralRuns).mockReturnValue(new Promise(() => {}));
    const onBack = vi.fn();
    render(<BehavioralComparisonView studyId="std_test_1" runIds={['run_1']} onBack={onBack} />);
    expect(screen.getByRole('status', { name: 'Loading simulation comparison' })).toBeInTheDocument();
    const back = screen.getByRole('button', { name: 'Back to Tests' });
    expect(back).toBeEnabled();
    back.focus();
    activateWithEnter(back);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('retries a failed comparison for the same selected run IDs', async () => {
    vi.mocked(api.compareBehavioralRuns).mockRejectedValueOnce(new Error('Comparison unavailable')).mockResolvedValueOnce({ study_id: 'std_test_1', compared_run_count: 1, runs: [mockRun] });
    render(<BehavioralComparisonView studyId="std_test_1" runIds={['run_1']} onBack={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Comparison unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry Comparison' }));
    expect(await screen.findByRole('heading', { name: 'Monthly Subscription' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.compareBehavioralRuns).toHaveBeenCalledTimes(2);
    expect(api.compareBehavioralRuns).toHaveBeenLastCalledWith('std_test_1', ['run_1']);
  });

  it('renders comparison empty state and allows returning to tests', async () => {
    vi.mocked(api.compareBehavioralRuns).mockResolvedValue({ study_id: 'std_test_1', compared_run_count: 0, runs: [] });
    const onBack = vi.fn();
    render(<BehavioralComparisonView studyId="std_test_1" runIds={[]} onBack={onBack} />);
    expect(await screen.findByText('No runs found for comparison.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to Tests' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('keeps unknown comparison scores distinct from zero and renders empty risk and driver lists', async () => {
    vi.mocked(api.compareBehavioralRuns).mockResolvedValue({ study_id: 'std_test_1', compared_run_count: 1, runs: [{ ...mockRun, aggregate_metrics: null, risks: [], opportunities: [] }] });
    render(<BehavioralComparisonView studyId="std_test_1" runIds={['run_1']} onBack={vi.fn()} />);
    expect(await screen.findByTitle('Not measured for this run')).not.toHaveTextContent('0%');
    expect(screen.getAllByText('None')).toHaveLength(2);
  });

  it('renders BehavioralComparisonView comparing simulation runs', async () => {
    vi.mocked(api.compareBehavioralRuns).mockResolvedValue({
      study_id: 'std_test_1',
      compared_run_count: 1,
      runs: [mockRun],
    });

    const onBack = vi.fn();

    render(
      <BehavioralComparisonView
        studyId="std_test_1"
        runIds={['run_1']}
        onBack={onBack}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Simulation Run Comparison')).toBeInTheDocument();
      expect(screen.getByText('Monthly Subscription')).toBeInTheDocument();
      expect(screen.getByText('68%')).toBeInTheDocument();
    });
  });
});

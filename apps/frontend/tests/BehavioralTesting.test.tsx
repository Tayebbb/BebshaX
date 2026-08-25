import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BehavioralTestingView } from '../src/components/dashboard/views/BehavioralTestingView';
import { BehavioralTestDetailView } from '../src/components/dashboard/views/BehavioralTestDetailView';
import { BehavioralComparisonView } from '../src/components/dashboard/views/BehavioralComparisonView';
import { CreateBehavioralTestModal } from '../src/components/dashboard/modals/CreateBehavioralTestModal';
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
    getStudySegments: vi.fn(),
    retryFailedBehavioralRun: vi.fn(),
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

describe('Part 7: Behavioral Testing & Simulation Frontend Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('handles 4-step wizard in CreateBehavioralTestModal', async () => {
    vi.mocked(api.getStudyPersonas).mockResolvedValue({
      personas: mockPersonas,
      total: 1,
      represented_segments: 1,
      average_grounding_score: 0.92,
    });
    vi.mocked(api.getStudySegments).mockResolvedValue(mockSegments);
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

    const continueBtn = screen.getByText('Continue');
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

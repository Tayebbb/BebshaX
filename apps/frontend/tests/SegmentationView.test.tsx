import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SegmentationView } from '../src/components/dashboard/views/SegmentationView';
import { api } from '../src/services/api';
import {
  MarketSegment,
  SegmentationReadiness,
  SegmentationRun,
  SegmentComparisonResult,
} from '../src/types/segmentation';

// Mock API methods
vi.mock('../src/services/api', () => ({
  api: {
    getSegmentationReadiness: vi.fn(),
    listStudySegments: vi.fn(),
    listSegmentationRuns: vi.fn(),
    runSegmentation: vi.fn(),
    compareSegments: vi.fn(),
  },
  default: {
    getSegmentationReadiness: vi.fn(),
    listStudySegments: vi.fn(),
    listSegmentationRuns: vi.fn(),
    runSegmentation: vi.fn(),
    compareSegments: vi.fn(),
  },
}));

const mockReadiness: SegmentationReadiness = {
  status: 'ready',
  can_run: true,
  dataset_count: 1,
  total_records: 1200,
  usable_variables_count: 3,
  usable_variables: [
    {
      name: 'monthly_budget_bdt',
      type: 'numeric',
      source_dataset_name: 'Student Survey',
      source_dataset_id: 'ds_1',
      coverage_percentage: 98.5,
      missing_percentage: 1.5,
      usefulness: 'high',
    },
    {
      name: 'study_hours_per_day',
      type: 'numeric',
      source_dataset_name: 'Student Survey',
      source_dataset_id: 'ds_1',
      coverage_percentage: 99.0,
      missing_percentage: 1.0,
      usefulness: 'high',
    },
  ],
  evidence_claim_count: 4,
  supported_claims_count: 3,
  guidance_message: 'Ready for segmentation with 1 connected dataset and 4 evidence claims.',
  study_id: 'study_123',
};

const mockSegments: MarketSegment[] = [
  {
    id: 'seg_01',
    study_id: 'study_123',
    segmentation_run_id: 'segrun_01',
    name: 'Budget-Conscious Students (৳350/mo)',
    cluster_label: 'cluster_0',
    description: 'Students facing budget constraints below ৳400/month. Highly sensitive to price.',
    population_count: 540,
    population_percentage: 45.0,
    confidence_score: 0.92,
    status: 'data_backed',
    characteristics: {
      name_hint: 'monthly_budget 250–500',
      partition_method: 'quantile_bands',
      partition_variable: 'monthly_budget',
      band: { lower: 250, upper: 500 },
      observed: {
        monthly_budget: { count: 540, min: 250, median: 350, max: 500 },
        age: { count: 540, min: 18, median: 20, max: 22 },
        device: { count: 540, top_categories: [{ category: 'phone', count: 500, percentage: 92.6 }] },
      },
      interpretation_source: 'llm',
      served_by: 'pollinations/deepseek-r1',
    },
    variable_distributions: { monthly_budget: { min: 250, median: 350, max: 500, count: 540 } },
    evidence_citations: [
      { claim_id: 'clm_1', claim_text: 'Students prefer bKash micro-payments', category: 'pricing', status: 'supported', confidence: 0.88 },
    ],
    differentiation_summary: 'Differs by lower monthly spending tolerance and high prioritization of affordable plans.',
    created_at: '2026-08-25T10:00:00Z',
    updated_at: '2026-08-25T10:00:00Z',
  },
  {
    id: 'seg_02',
    study_id: 'study_123',
    segmentation_run_id: 'segrun_01',
    name: 'Exam-Driven Achievers (৳750/mo)',
    cluster_label: 'cluster_1',
    description: 'High-urgency admission seekers willing to pay for score improvement.',
    population_count: 420,
    population_percentage: 35.0,
    confidence_score: 0.88,
    status: 'data_backed',
    characteristics: {
      name_hint: 'monthly_budget 500–1200',
      partition_method: 'quantile_bands',
      partition_variable: 'monthly_budget',
      band: { lower: 500, upper: 1200 },
      observed: {
        monthly_budget: { count: 420, min: 500, median: 750, max: 1200 },
        age: { count: 420, min: 19, median: 21, max: 23 },
        device: { count: 420, top_categories: [{ category: 'laptop', count: 300, percentage: 71.4 }] },
      },
    },
    variable_distributions: { monthly_budget: { min: 500, median: 750, max: 1200, count: 420 } },
    evidence_citations: [
      { claim_id: 'clm_2', claim_text: 'Candidates pay premium before exams', category: 'behavior', status: 'supported', confidence: 0.90 },
    ],
    differentiation_summary: 'Differs by high daily study intensity and elevated willingness to pay.',
    created_at: '2026-08-25T10:00:00Z',
    updated_at: '2026-08-25T10:00:00Z',
  },
];

const mockRun: SegmentationRun = {
  id: 'segrun_01',
  study_id: 'study_123',
  status: 'completed',
  method: 'hybrid_quantile_clustering',
  configuration: {},
  dataset_versions: [
    { dataset_id: 'ds_1', name: 'Student Survey', content_hash: 'hash_abc123', row_count: 1200, file_type: 'csv' },
  ],
  evidence_snapshot: { claim_count: 4 },
  segment_count: 2,
  started_at: '2026-08-25T10:00:00Z',
  completed_at: '2026-08-25T10:00:03Z',
  created_at: '2026-08-25T10:00:00Z',
};

const mockComparison: SegmentComparisonResult = {
  study_id: 'study_123',
  compared_count: 2,
  comparison_matrix: [
    {
      segment_id: 'seg_01',
      name: 'Budget-Conscious Students',
      cluster_label: 'cluster_0',
      population_count: 540,
      population_percentage: 45.0,
      confidence_score: 0.92,
      status: 'data_backed',
      partition_variable: 'monthly_budget',
      headline_range: '250–500',
      headline_median: 350,
      top_categories: { device: 'phone' },
      observed_variables: ['monthly_budget', 'age', 'device'],
      evidence_citations_count: 1,
      differentiation: 'Lower spending tolerance',
    },
    {
      segment_id: 'seg_02',
      name: 'Exam-Driven Achievers',
      cluster_label: 'cluster_1',
      population_count: 420,
      population_percentage: 35.0,
      confidence_score: 0.88,
      status: 'data_backed',
      partition_variable: 'monthly_budget',
      headline_range: '500–1200',
      headline_median: 750,
      top_categories: { device: 'laptop' },
      observed_variables: ['monthly_budget', 'age', 'device'],
      evidence_citations_count: 1,
      differentiation: 'High urgency for score improvement',
    },
  ],
};

describe('SegmentationView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getSegmentationReadiness as any).mockResolvedValue(mockReadiness);
    (api.listStudySegments as any).mockResolvedValue(mockSegments);
    (api.listSegmentationRuns as any).mockResolvedValue([mockRun]);
    (api.runSegmentation as any).mockResolvedValue({ run: mockRun, segments: mockSegments });
    (api.compareSegments as any).mockResolvedValue(mockComparison);
  });

  it('renders readiness status, banner metrics, and segment cards', async () => {
    render(<SegmentationView studyId="study_123" />);

    expect(await screen.findByText('Market Segmentation')).toBeInTheDocument();
    expect(screen.getByText('Ready for segmentation with 1 connected dataset and 4 evidence claims.')).toBeInTheDocument();
    expect(screen.getByText('monthly_budget_bdt')).toBeInTheDocument();

    // Verify segment cards
    expect(screen.getByText('Budget-Conscious Students (৳350/mo)')).toBeInTheDocument();
    expect(screen.getByText('Exam-Driven Achievers (৳750/mo)')).toBeInTheDocument();
  });

  it('triggers runSegmentation and displays updated segments', async () => {
    render(<SegmentationView studyId="study_123" />);

    const runBtn = await screen.findByTestId('run-segmentation-btn');
    expect(runBtn).toBeInTheDocument();

    fireEvent.click(runBtn);

    await waitFor(() => {
      expect(api.runSegmentation).toHaveBeenCalledWith('study_123', { desired_clusters: 3 });
    });
  });

  it('opens and navigates tabs in the Deep Dive Inspection Modal', async () => {
    render(<SegmentationView studyId="study_123" />);

    const deepDiveBtn = await screen.findByTestId('deep-dive-btn-seg_01');
    fireEvent.click(deepDiveBtn);

    // Modal is open
    expect(await screen.findByTestId('segment-detail-modal')).toBeInTheDocument();
    expect(screen.getByTestId('tab-content-overview')).toBeInTheDocument();
    expect(screen.getByText(/written by pollinations\/deepseek-r1/i)).toBeInTheDocument();

    // Observed variables tab: the real per-cluster distributions, no assumed fields
    fireEvent.click(screen.getByTestId('modal-tab-observed'));
    const observedTab = await screen.findByTestId('tab-content-observed');
    expect(observedTab.textContent).toContain('Quantile band of monthly budget');
    expect(observedTab.textContent).toContain('350');
    expect(observedTab.textContent).toContain('phone');
    expect(observedTab.textContent).toContain('540 observations');
    expect(observedTab.textContent).not.toContain('৳');
    expect(observedTab.textContent).not.toContain('Tech Familiarity');

    // Switch to Evidence tab
    fireEvent.click(screen.getByTestId('modal-tab-evidence'));
    expect(await screen.findByTestId('tab-content-evidence')).toBeInTheDocument();
    expect(screen.getByText(/Students prefer bKash micro-payments/i)).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByTestId('close-detail-modal-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('segment-detail-modal')).not.toBeInTheDocument();
    });
  });

  it('selects multiple segments and opens side-by-side comparison modal', async () => {
    render(<SegmentationView studyId="study_123" />);

    const check1 = await screen.findByTestId('compare-checkbox-seg_01');
    const check2 = await screen.findByTestId('compare-checkbox-seg_02');

    fireEvent.click(check1);
    fireEvent.click(check2);

    // Floating bar appears
    expect(await screen.findByTestId('floating-compare-bar')).toBeInTheDocument();

    // Click compare selected button
    const compareBtn = screen.getByTestId('compare-selected-btn');
    fireEvent.click(compareBtn);

    await waitFor(() => {
      expect(api.compareSegments).toHaveBeenCalledWith('study_123', ['seg_01', 'seg_02']);
    });

    // Verify comparison modal table
    const comparisonModal = await screen.findByTestId('comparison-modal');
    expect(screen.getByText('Side-by-Side Segment Comparison')).toBeInTheDocument();
    expect(comparisonModal.textContent).toContain('250–500');
    expect(comparisonModal.textContent).toContain('device: laptop');
    expect(comparisonModal.textContent).not.toContain('Tech Familiarity');
  });

  it('filters segments using search input', async () => {
    render(<SegmentationView studyId="study_123" />);

    await screen.findByText('Budget-Conscious Students (৳350/mo)');

    const searchInput = screen.getByTestId('search-segments-input');
    fireEvent.change(searchInput, { target: { value: 'Achievers' } });

    expect(screen.queryByText('Budget-Conscious Students (৳350/mo)')).not.toBeInTheDocument();
    expect(screen.getByText('Exam-Driven Achievers (৳750/mo)')).toBeInTheDocument();
  });

  it('renders no invented numbers or labels when a segment has all optional fields absent', async () => {
    const bareSegment: MarketSegment = {
      id: 'seg_bare',
      study_id: 'study_123',
      segmentation_run_id: 'segrun_01',
      name: 'Sparse Cluster',
      cluster_label: 'cluster_9',
      description: 'Cluster with no optional characteristics extracted.',
      population_count: 120,
      population_percentage: 10.0,
      confidence_score: 0.51,
      status: 'inference_assisted',
      characteristics: {},
      variable_distributions: {},
      evidence_citations: [],
      created_at: '2026-08-25T10:00:00Z',
    };
    (api.listStudySegments as any).mockResolvedValue([bareSegment]);

    render(<SegmentationView studyId="study_123" />);

    // Card grid: no fabricated age cohort / tech familiarity / currency.
    await screen.findByText('Sparse Cluster');
    expect(screen.queryByText(/18–24 yrs/)).not.toBeInTheDocument();
    expect(screen.queryByText('Medium')).not.toBeInTheDocument();
    expect(screen.queryByText(/৳/)).not.toBeInTheDocument();
    expect(screen.getByText('No categorical variables observed')).toBeInTheDocument();

    // Overview: differentiation omitted, provenance stated honestly.
    fireEvent.click(screen.getByTestId('deep-dive-btn-seg_bare'));
    await screen.findByTestId('segment-detail-modal');
    expect(screen.queryByText(/Key Differentiation Rationale/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Distinct behavior and economic limits/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Affordable and distraction-free experience/i)).not.toBeInTheDocument();

    // Observed variables: nothing measured -> said plainly, no numbers invented.
    fireEvent.click(screen.getByTestId('modal-tab-observed'));
    const observedTab = await screen.findByTestId('tab-content-observed');
    expect(observedTab.textContent).toContain('Partition method not recorded');
    expect(observedTab.textContent).toContain('nothing is assumed in their place');
    expect(observedTab.textContent).not.toContain('18 – 24 years');
    expect(observedTab.textContent).not.toContain('৳');
    expect(observedTab.textContent).not.toContain('bKash');
  });
});

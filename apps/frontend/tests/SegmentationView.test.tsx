import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
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

const nextRun: SegmentationRun = {
  ...mockRun,
  id: 'segrun_next',
  dataset_versions: [{ ...mockRun.dataset_versions[0], name: 'Updated survey', content_hash: 'hash_next' }],
};
const nextResult = {
  run: nextRun,
  segments: [{ ...mockSegments[0], id: 'seg_next', segmentation_run_id: nextRun.id, name: 'Updated cohort' }],
};
const segmentRequest = <Value,>() => {
  let resolve!: (value: Value) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
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

  it.each(['readiness', 'history'] as const)('shows saved segments while %s is pending', async (metadata) => {
    const request = metadata === 'readiness' ? api.getSegmentationReadiness : api.listSegmentationRuns;
    vi.mocked(request).mockReturnValueOnce(new Promise<never>(() => {}));

    render(<SegmentationView studyId="study_123" />);

    expect(await screen.findByTestId('deep-dive-btn-seg_01')).toBeInTheDocument();
    expect(screen.queryByText('Loading segmentation data…')).not.toBeInTheDocument();
  });

  it.each(['readiness', 'history'] as const)('shows saved segments when %s fails', async (metadata) => {
    const request = metadata === 'readiness' ? api.getSegmentationReadiness : api.listSegmentationRuns;
    vi.mocked(request).mockRejectedValueOnce(new Error(`${metadata} unavailable`));

    render(<SegmentationView studyId="study_123" />);

    expect(await screen.findByTestId('deep-dive-btn-seg_01')).toBeInTheDocument();
    expect(screen.queryByText('Loading segmentation data…')).not.toBeInTheDocument();
  });

  it.each(['readiness', 'history'] as const)('isolates a %s failure to its dependent actions', async (metadata) => {
    const request = metadata === 'readiness' ? api.getSegmentationReadiness : api.listSegmentationRuns;
    vi.mocked(request).mockRejectedValueOnce(new Error(`${metadata} unavailable`));
    render(<SegmentationView studyId="study_123" />);

    expect(await screen.findByTestId('deep-dive-btn-seg_01')).toBeEnabled();
    expect(screen.getByTestId('export-csv-btn')).toBeEnabled();
    expect(screen.getByRole('alert')).toHaveTextContent(metadata === 'readiness' ? 'Data readiness unavailable' : 'Run history unavailable');
    if (metadata === 'readiness') expect(screen.getByTestId('run-segmentation-btn')).toBeDisabled();
    else expect(screen.getByTestId('run-segmentation-btn')).toBeEnabled();
  });

  it('shows the selected older run dataset versions instead of the newest run', async () => {
    vi.mocked(api.listSegmentationRuns).mockResolvedValueOnce([nextRun, mockRun]);
    render(<SegmentationView studyId="study_123" />);
    fireEvent.click(await screen.findByTestId('deep-dive-btn-seg_01'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));

    expect(screen.getByTestId('tab-content-provenance')).toHaveTextContent('hash_abc123');
    expect(screen.getByTestId('tab-content-provenance')).not.toHaveTextContent('hash_next');
  });

  it.each(['missing', 'other study'] as const)('does not substitute %s run history for selected lineage', async (history) => {
    vi.mocked(api.listSegmentationRuns).mockResolvedValueOnce(history === 'missing'
      ? [nextRun] : [{ ...mockRun, study_id: 'another-study' }]);
    render(<SegmentationView studyId="study_123" />);
    fireEvent.click(await screen.findByTestId('deep-dive-btn-seg_01'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));

    const provenance = screen.getByTestId('tab-content-provenance');
    expect(provenance).toHaveTextContent(mockRun.id);
    expect(provenance).toHaveTextContent('Dataset provenance is unavailable for this run.');
    expect(provenance).not.toHaveTextContent('hash_abc123');
    expect(provenance).not.toHaveTextContent('hash_next');
  });

  it('closes an older segment selected during a run when replacement segments arrive', async () => {
    const execution = segmentRequest<typeof nextResult>();
    vi.mocked(api.runSegmentation).mockReturnValueOnce(execution.promise);
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    fireEvent.click(screen.getByTestId('run-segmentation-btn'));
    fireEvent.click(screen.getByTestId('deep-dive-btn-seg_01'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));
    expect(screen.getByTestId('tab-content-provenance')).toHaveTextContent('hash_abc123');

    await act(async () => execution.resolve(nextResult));
    expect(screen.queryByTestId('segment-detail-modal')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('deep-dive-btn-seg_next'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));
    expect(screen.getByTestId('tab-content-provenance')).toHaveTextContent('hash_next');
    expect(screen.getByTestId('tab-content-provenance')).not.toHaveTextContent('hash_abc123');
  });

  it.each(['pending', 'failed'] as const)('finishes primary run results while history refresh is %s', async (history) => {
    vi.mocked(api.runSegmentation).mockResolvedValueOnce(nextResult);
    vi.mocked(api.listSegmentationRuns).mockResolvedValueOnce([mockRun]);
    if (history === 'pending') vi.mocked(api.listSegmentationRuns).mockReturnValueOnce(new Promise<never>(() => {}));
    else vi.mocked(api.listSegmentationRuns).mockRejectedValueOnce(new Error('History refresh failed'));
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    fireEvent.click(screen.getByTestId('run-segmentation-btn'));

    expect(await screen.findByTestId('deep-dive-btn-seg_next')).toBeInTheDocument();
    expect(screen.getByTestId('run-segmentation-btn')).toBeEnabled();
    expect(screen.queryByText('Segmentation Engine in Progress')).not.toBeInTheDocument();
    if (history === 'failed') expect(screen.getByRole('alert')).toHaveTextContent('Run history unavailable: History refresh failed');
    fireEvent.click(screen.getByTestId('deep-dive-btn-seg_next'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));
    expect(screen.getByTestId('tab-content-provenance')).toHaveTextContent('hash_next');
  });

  it('ignores stale history after a new run has completed', async () => {
    const history = segmentRequest<SegmentationRun[]>();
    vi.mocked(api.listSegmentationRuns).mockReturnValueOnce(history.promise);
    vi.mocked(api.runSegmentation).mockResolvedValueOnce(nextResult);
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    fireEvent.click(screen.getByTestId('run-segmentation-btn'));
    fireEvent.click(await screen.findByTestId('deep-dive-btn-seg_next'));
    fireEvent.click(screen.getByTestId('modal-tab-provenance'));

    await act(async () => history.resolve([mockRun]));
    expect(screen.getByTestId('tab-content-provenance')).toHaveTextContent('hash_next');
    expect(screen.getByTestId('tab-content-provenance')).not.toHaveTextContent('hash_abc123');
  });

  it.each(['history', 'run'] as const)('does not reopen dismissed details after a late %s completion', async (completion) => {
    const history = segmentRequest<SegmentationRun[]>();
    const execution = segmentRequest<typeof nextResult>();
    if (completion === 'history') vi.mocked(api.listSegmentationRuns).mockReturnValueOnce(history.promise);
    else vi.mocked(api.runSegmentation).mockReturnValueOnce(execution.promise);
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    if (completion === 'run') fireEvent.click(screen.getByTestId('run-segmentation-btn'));
    fireEvent.click(screen.getByTestId('deep-dive-btn-seg_01'));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('segment-detail-modal')).not.toBeInTheDocument();

    await act(async () => {
      if (completion === 'history') history.resolve([mockRun]);
      else execution.resolve(nextResult);
    });
    expect(screen.queryByTestId('segment-detail-modal')).not.toBeInTheDocument();
  });

  it('keeps cached segments available during a retry that fails', async () => {
    const refresh = segmentRequest<MarketSegment[]>();
    vi.mocked(api.getSegmentationReadiness).mockRejectedValueOnce(new Error('Readiness failed'));
    vi.mocked(api.listStudySegments).mockResolvedValueOnce(mockSegments).mockReturnValueOnce(refresh.promise);
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    fireEvent.click(screen.getByRole('button', { name: 'Retry metadata' }));
    expect(screen.getByTestId('deep-dive-btn-seg_01')).toBeEnabled();

    await act(async () => refresh.reject(new Error('Segment refresh failed')));
    expect(screen.getByRole('alert')).toHaveTextContent('Segment refresh failed');
    expect(screen.getByTestId('deep-dive-btn-seg_01')).toBeEnabled();
    expect(screen.getByTestId('export-json-btn')).toBeEnabled();
  });

  it.each(['success', 'failure'] as const)('ignores stale reads and auxiliary %s after a study change', async (outcome) => {
    const segments = segmentRequest<MarketSegment[]>();
    const readiness = segmentRequest<SegmentationReadiness>();
    const history = segmentRequest<SegmentationRun[]>();
    vi.mocked(api.listStudySegments).mockReturnValueOnce(segments.promise).mockResolvedValueOnce(nextResult.segments);
    vi.mocked(api.getSegmentationReadiness).mockReturnValueOnce(readiness.promise);
    vi.mocked(api.listSegmentationRuns).mockReturnValueOnce(history.promise).mockResolvedValueOnce([nextRun]);
    const { rerender } = render(<SegmentationView studyId="study-old" />);
    rerender(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_next');

    await act(async () => {
      segments.resolve(mockSegments);
      if (outcome === 'success') {
        readiness.resolve({ ...mockReadiness, can_run: false, guidance_message: 'Old study readiness' });
        history.resolve([mockRun]);
      } else {
        readiness.reject(new Error('Old study readiness'));
        history.reject(new Error('Old study history'));
      }
    });
    expect(screen.getByTestId('deep-dive-btn-seg_next')).toBeInTheDocument();
    expect(screen.queryByTestId('deep-dive-btn-seg_01')).not.toBeInTheDocument();
    expect(screen.queryByText(/Old study/)).not.toBeInTheDocument();
    expect(screen.getByTestId('run-segmentation-btn')).toBeEnabled();
  });

  it('does not report an empty study while primary data is pending or failed', async () => {
    const segments = segmentRequest<MarketSegment[]>();
    vi.mocked(api.listStudySegments).mockReturnValueOnce(segments.promise);
    render(<SegmentationView studyId="study_123" />);
    expect(screen.queryByTestId('no-segments-placeholder')).not.toBeInTheDocument();

    await act(async () => segments.reject(new Error('Segments unavailable')));
    expect(screen.getByRole('alert')).toHaveTextContent('Segments unavailable');
    expect(screen.queryByTestId('no-segments-placeholder')).not.toBeInTheDocument();
  });

  it('uses the black canvas token without decorative blurred overlays', async () => {
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    const view = screen.getByTestId('segmentation-view');
    expect(view).toHaveClass('bg-[var(--bg-pure)]');
    expect(view.querySelectorAll('[class*="rounded-full"][class*="blur-"]')).toHaveLength(0);
  });

  it('names the research filters and exposes each comparison selection state', async () => {
    render(<SegmentationView studyId="study_123" />);
    await screen.findByTestId('deep-dive-btn-seg_01');
    expect(screen.getByRole('textbox', { name: 'Search segments' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Segment status' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Cluster count' })).toBeInTheDocument();
    const selection = screen.getByTestId('compare-checkbox-seg_01');
    expect(selection).toHaveAccessibleName(`Compare ${mockSegments[0].name}`);
    expect(selection).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(selection);
    expect(selection).toHaveAttribute('aria-pressed', 'true');
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

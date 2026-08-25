import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import SegmentationView from '../src/components/dashboard/views/SegmentationView';
import api from '../src/services/api';
import {
  MarketSegment,
  SegmentationReadiness,
  SegmentationRun,
  SegmentComparisonResult,
} from '../src/types/segmentation';

// Mock API methods
vi.mock('../src/services/api', () => ({
  default: {
    getSegmentationReadiness: vi.fn(),
    listStudySegments: vi.fn(),
    listSegmentationRuns: vi.fn(),
    runSegmentation: vi.fn(),
    compareSegments: vi.fn(),
  },
  api: {
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
      demographics: { age_range: [18, 22], median_age: 20, dominant_occupation: 'Undergrad Student' },
      economics: { monthly_budget: { min: 250, median: 350, max: 500, currency: 'BDT' } },
      behavior: { study_hours_per_day: 4.5, technology_familiarity: 'Medium' },
      needs: ['Affordable micro-subscriptions', 'Offline mobile mode'],
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
      demographics: { age_range: [19, 23], median_age: 21, dominant_occupation: 'Admission Candidate' },
      economics: { monthly_budget: { min: 500, median: 750, max: 1200, currency: 'BDT' } },
      behavior: { study_hours_per_day: 7.2, technology_familiarity: 'High' },
      needs: ['Mock test analytics', 'Dynamic daily revision schedules'],
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
      median_budget: '৳350',
      budget_range: '৳250–৳500',
      age_range: '18–22 yrs',
      tech_familiarity: 'Medium',
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
      median_budget: '৳750',
      budget_range: '৳500–৳1200',
      age_range: '19–23 yrs',
      tech_familiarity: 'High',
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

    // Switch to Demographics tab
    fireEvent.click(screen.getByTestId('modal-tab-demographics'));
    expect(await screen.findByTestId('tab-content-demographics')).toBeInTheDocument();
    expect(screen.getByText(/18 – 22 years/i)).toBeInTheDocument();

    // Switch to Economics tab
    fireEvent.click(screen.getByTestId('modal-tab-economics'));
    const econTab = await screen.findByTestId('tab-content-economics');
    expect(econTab).toBeInTheDocument();
    expect(econTab.textContent).toContain('350');

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
    expect(await screen.findByTestId('comparison-modal')).toBeInTheDocument();
    expect(screen.getByText('Side-by-Side Segment Comparison')).toBeInTheDocument();
  });

  it('filters segments using search input', async () => {
    render(<SegmentationView studyId="study_123" />);

    await screen.findByText('Budget-Conscious Students (৳350/mo)');

    const searchInput = screen.getByTestId('search-segments-input');
    fireEvent.change(searchInput, { target: { value: 'Achievers' } });

    expect(screen.queryByText('Budget-Conscious Students (৳350/mo)')).not.toBeInTheDocument();
    expect(screen.getByText('Exam-Driven Achievers (৳750/mo)')).toBeInTheDocument();
  });
});

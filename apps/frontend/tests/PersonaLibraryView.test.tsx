import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PersonaLibraryView } from '../src/components/dashboard/views/PersonaLibraryView';
import { api } from '../src/services/api';
import { SyntheticPersona, MarketSegment, Study } from '../src/types';

// Mock API
vi.mock('../src/services/api', () => ({
  api: {
    getStudies: vi.fn(),
    getStudyPersonas: vi.fn(),
    getMarketSegments: vi.fn(),
    listStudyPersonaRuns: vi.fn(),
    generateSyntheticPersonas: vi.fn(),
    regenerateStudyPersona: vi.fn(),
  },
  default: {
    getStudies: vi.fn(),
    getStudyPersonas: vi.fn(),
    getMarketSegments: vi.fn(),
    listStudyPersonaRuns: vi.fn(),
    generateSyntheticPersonas: vi.fn(),
    regenerateStudyPersona: vi.fn(),
  },
}));

const mockStudies: Study[] = [
  {
    id: 'study_123',
    title: 'Exam Prep AI Platform',
    type: 'interviews',
    goal: 'demand_validation',
    status: 'in_progress',
    step: 3,
    persona_count: 2,
    persona_ids: ['per_01', 'per_02'],
    suggested_roles: [],
    script_questions: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockSegments: MarketSegment[] = [
  {
    id: 'seg_01',
    study_id: 'study_123',
    segmentation_run_id: 'srun_01',
    name: 'Budget-Conscious Students',
    cluster_label: 'cluster_0',
    description: 'Price-sensitive university students',
    population_count: 540,
    population_percentage: 60.0,
    confidence_score: 0.92,
    status: 'data_backed',
    characteristics: {
      demographics: { age_range: [18, 22], dominant_occupation: 'Undergrad Student' },
      economics: { monthly_budget: { min: 250, median: 350, max: 500 } },
    },
    variable_distributions: {},
    evidence_citations: [],
    created_at: new Date().toISOString(),
  },
  {
    id: 'seg_02',
    study_id: 'study_123',
    segmentation_run_id: 'srun_01',
    name: 'Exam-Driven Achievers',
    cluster_label: 'cluster_1',
    description: 'High urgency exam candidates',
    population_count: 360,
    population_percentage: 40.0,
    confidence_score: 0.88,
    status: 'data_backed',
    characteristics: {
      demographics: { age_range: [21, 24], dominant_occupation: 'Graduate Candidate' },
      economics: { monthly_budget: { min: 500, median: 750, max: 1200 } },
    },
    variable_distributions: {},
    evidence_citations: [],
    created_at: new Date().toISOString(),
  },
];

const mockPersonas: SyntheticPersona[] = [
  {
    id: 'per_01',
    study_id: 'study_123',
    segment_id: 'seg_01',
    segment_name: 'Budget-Conscious Students',
    generation_run_id: 'pgen_01',
    name: 'Nadia Rahman',
    status: 'ready',
    version: 1,
    generation_model: 'qwen3.5-grounded',
    archetype: 'Budget-Conscious Student Planner',
    demographics: {
      age: 21,
      occupation: 'Undergrad Student',
      location: 'Dhaka, Bangladesh',
      income_or_budget: '৳350/mo',
    },
    bio: 'Nadia is an undergraduate student managing a tight budget.',
    quote: 'I need an affordable tool capped under ৳350/mo.',
    goals: ['Ace midterm exams', 'Synchronize daily timetable'],
    needs: ['bKash billing', 'Offline mode'],
    pain_points: ['Expensive subscriptions requiring credit cards'],
    behaviors: ['Daily mobile user ~4.5h'],
    preferences: ['Dark mode'],
    motivations: ['High CGPA'],
    objections: ['Hidden recurring fees'],
    commercial_profile: {
      monthly_budget_bdt: 350,
      price_sensitivity: 'High',
      payment_preference: 'bKash Wallet',
      willingness_to_pay: '৳250–৳400/mo',
    },
    technology_profile: {
      primary_devices: ['Android Smartphone'],
      platforms: ['WhatsApp', 'Messenger'],
      familiarity: 'High',
    },
    evidence_citations: [
      {
        claim_id: 'clm_1',
        claim_text: 'Students prefer bKash billing capped under ৳400/mo.',
        category: 'pricing',
        confidence: 0.92,
      },
    ],
    dataset_refs: [
      { variable: 'monthly_budget', value: 350, source: 'Segment Profile' },
    ],
    grounding_score: 0.94,
    confidence: 0.90,
    validation_warnings: [],
    is_synthetic: true,
    created_at: new Date().toISOString(),
  },
  {
    id: 'per_02',
    study_id: 'study_123',
    segment_id: 'seg_02',
    segment_name: 'Exam-Driven Achievers',
    generation_run_id: 'pgen_01',
    name: 'Tanvir Ahmed',
    status: 'ready',
    version: 1,
    data_source: 'cached',
    generation_model: 'qwen3.5-grounded',
    archetype: 'Exam Achiever Archetype',
    demographics: {
      age: 23,
      occupation: 'BCS Candidate',
      location: 'Chittagong, Bangladesh',
      income_or_budget: '৳750/mo',
    },
    bio: 'Tanvir is an ambitious candidate preparing for civil service.',
    quote: 'I will pay for real-time diagnostic question banks.',
    goals: ['Rank top 5%'],
    needs: ['Diagnostic error log'],
    pain_points: ['Generic question books'],
    behaviors: ['7+ hours daily study'],
    preferences: ['Detailed metrics'],
    motivations: ['Career security'],
    objections: ['Question authenticity'],
    commercial_profile: {
      monthly_budget_bdt: 750,
      price_sensitivity: 'Moderate',
      payment_preference: 'bKash / Card',
      willingness_to_pay: '৳600–৳1000/mo',
    },
    technology_profile: {
      primary_devices: ['Android Tablet', 'Laptop'],
      platforms: ['Telegram'],
      familiarity: 'High',
    },
    evidence_citations: [
      {
        claim_id: 'clm_2',
        claim_text: 'Candidates exhibit 2.5x higher WTP for diagnostics.',
        category: 'willingness_to_pay',
        confidence: 0.89,
      },
    ],
    dataset_refs: [
      { variable: 'monthly_budget', value: 750, source: 'Segment Profile' },
    ],
    grounding_score: 0.91,
    confidence: 0.88,
    validation_warnings: [],
    is_synthetic: true,
    created_at: new Date().toISOString(),
  },
];

describe('PersonaLibraryView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getStudies as any).mockResolvedValue(mockStudies);
    (api.getStudyPersonas as any).mockResolvedValue({
      personas: mockPersonas,
      total: 2,
      represented_segments: 2,
      average_grounding_score: 0.93,
    });
    (api.getMarketSegments as any).mockResolvedValue(mockSegments);
    (api.listStudyPersonaRuns as any).mockResolvedValue({ runs: [] });
  });

  it('renders title, metrics banner, and synthetic persona cards', async () => {
    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Persona Library')).toBeInTheDocument();
      expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
      expect(screen.getByText('Tanvir Ahmed')).toBeInTheDocument();
    });

    // Verify metrics
    expect(screen.getByText('Total Synthetic Personas')).toBeInTheDocument();
    expect(screen.getByText('Represented Segments')).toBeInTheDocument();
    expect(screen.getByText('Evidence-backed personas')).toBeInTheDocument();

    // Verify badges and per-persona evidence chips
    expect(screen.getByText('94% evidence-backed')).toBeInTheDocument();
    expect(screen.getByText('91% evidence-backed')).toBeInTheDocument();
    expect(screen.getAllByText('Synthetic Persona').length).toBeGreaterThanOrEqual(2);
  });

  it('labels cached personas with a CACHED badge and leaves live ones unlabelled', async () => {
    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Tanvir Ahmed')).toBeInTheDocument();
    });

    // per_02 is data_source: 'cached'; per_01 has no data_source (live default)
    expect(screen.getAllByText('CACHED')).toHaveLength(1);
  });

  it('filters personas by search query', async () => {
    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search personas/i);
    fireEvent.change(searchInput, { target: { value: 'Nadia' } });

    expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
    expect(screen.queryByText('Tanvir Ahmed')).not.toBeInTheDocument();
  });

  it('opens generation modal and submits generation', async () => {
    (api.generateSyntheticPersonas as any).mockResolvedValue({
      run: { id: 'pgen_new', status: 'completed' },
      personas: mockPersonas,
    });

    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Generate Personas')).toBeInTheDocument();
    });

    // Open modal
    fireEvent.click(screen.getByText('Generate Personas'));
    expect(screen.getByText('Generate Synthetic Personas')).toBeInTheDocument();

    // Choose equal distribution
    fireEvent.click(screen.getByText('Equal Distribution'));

    // Trigger synthesis
    fireEvent.click(screen.getByText('Synthesize Personas'));

    await waitFor(() => {
      expect(api.generateSyntheticPersonas).toHaveBeenCalledWith('study_123', expect.objectContaining({
        distribution_strategy: 'equal',
      }));
    });
  });

  it('opens Deep Dive Inspector Modal and switches tabs', async () => {
    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
    });

    // Click Deep Dive on first persona card
    const deepDiveButtons = screen.getAllByText('Deep Dive Inspector');
    fireEvent.click(deepDiveButtons[0]);

    // Verify modal opened
    expect(screen.getByText('Consumer Bio & Direct Perspective')).toBeInTheDocument();
    expect(screen.getAllByText('Ace midterm exams')[0]).toBeInTheDocument();

    // Switch to Commercial & WTP tab
    fireEvent.click(screen.getByText('Commercial & WTP'));
    expect(screen.getByText('Estimated Monthly Budget')).toBeInTheDocument();
    expect(screen.getByText('৳350 / mo')).toBeInTheDocument();

    // Switch to Technology tab
    fireEvent.click(screen.getByText('Technology Profile'));
    expect(screen.getByText('Android Smartphone')).toBeInTheDocument();

    // Switch to Evidence Citations tab
    fireEvent.click(screen.getByText(/Evidence Citations/i));
    expect(screen.getByText(/"Students prefer bKash billing capped under ৳400\/mo\."/)).toBeInTheDocument();

    // Switch to Dataset tab
    fireEvent.click(screen.getByText('Dataset Provenance'));
    expect(screen.getByText('monthly_budget')).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByText('Close'));
    await waitFor(() => {
      expect(screen.queryByText('Consumer Bio & Direct Perspective')).not.toBeInTheDocument();
    });
  });

  it('triggers persona regeneration', async () => {
    (api.regenerateStudyPersona as any).mockResolvedValue({
      ...mockPersonas[0],
      version: 2,
      name: 'Nadia Rahman (v2)',
    });

    render(<PersonaLibraryView studyId="study_123" />);

    await waitFor(() => {
      expect(screen.getByText('Nadia Rahman')).toBeInTheDocument();
    });

    // Open deep dive modal
    fireEvent.click(screen.getAllByText('Deep Dive Inspector')[0]);

    // Click Regenerate button
    const regenBtn = screen.getByText('Regenerate');
    fireEvent.click(regenBtn);

    await waitFor(() => {
      expect(api.regenerateStudyPersona).toHaveBeenCalledWith('study_123', 'per_01');
    });
  });
});

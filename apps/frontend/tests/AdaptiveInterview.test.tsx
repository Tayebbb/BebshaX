import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { InterviewsView } from '../src/components/dashboard/views/InterviewsView';
import { InterviewWorkspace } from '../src/components/interview/InterviewWorkspace';
import { StartInterviewModal } from '../src/components/dashboard/modals/StartInterviewModal';
import { api } from '../src/services/api';
import {
  SyntheticPersona,
  Interview,
} from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    getStudyInterviewMetrics: vi.fn(),
    listStudyInterviews: vi.fn(),
    getStudyInterviewDetail: vi.fn(),
    getStudyPersonaDetail: vi.fn(),
    startPersonaInterview: vi.fn(),
    sendInterviewMessage: vi.fn(),
    sendInterviewMessageStream: vi.fn(),
    completeStudyInterview: vi.fn(),
  },
}));

const mockPersona: SyntheticPersona = {
  id: 'per_nadia',
  name: 'Nadia Rahman',
  status: 'ready',
  version: 1,
  demographics: {
    age: 21,
    occupation: 'University Student',
    location: 'Dhanmondi, Dhaka',
    education: 'Undergraduate BBA',
  },
  commercial_profile: {
    monthly_budget_bdt: 400,
    price_sensitivity: 'Very High',
    payment_preference: 'bKash',
  },
  technology_profile: {
    primary_devices: ['Android smartphone'],
  },
  evidence_citations: [
    {
      claim_text: '72% of university hostellers spend under 150 BDT on lunch',
      category: 'spending',
    },
  ],
  goals: ['Save time during exam weeks'],
  needs: ['Budget meals'],
  pain_points: ['Mess food is repetitive'],
  behaviors: ['Uses bKash daily'],
  preferences: ['Affordability'],
  motivations: ['Graduation'],
  objections: ['Will cancel if fee > 400 BDT'],
  dataset_refs: [],
  grounding_score: 0.92,
  confidence: 0.95,
  validation_warnings: [],
  is_synthetic: true,
  created_at: new Date().toISOString(),
};

const mockInterview: Interview = {
  id: 'int_001',
  study_id: 'study_123',
  persona_id: 'per_nadia',
  persona_version: 1,
  persona_name: 'Nadia Rahman',
  persona_occupation: 'University Student',
  objective: 'Problem & Pain Point Discovery',
  interview_type: 'adaptive_persona',
  length_tier: 'standard',
  max_turns: 14,
  status: 'active',
  topics_explored: {
    pain_points: 'explored',
    pricing_budget: 'explored',
  },
  question_count: 2,
  turn_count: 4,
  created_at: new Date().toISOString(),
};

// The backend returns the interview FLAT (turns/insights/suggestions at the
// top level) — this mirrors bebshax.api.interviews._serialize_interview.
const mockDetail = {
  ...mockInterview,
  turns: [
    {
      id: 't_1',
      turn_number: 1,
      role: 'interviewer',
      content: 'How do you handle meals during finals?',
      created_at: new Date().toISOString(),
    },
    {
      id: 't_2',
      turn_number: 2,
      role: 'persona',
      content: 'I usually eat at the dorm canteen, but the food is very repetitive.',
      topic: 'pain_points',
      served_by: 'openrouter/qwen3.5',
      latency_ms: 320,
      created_at: new Date().toISOString(),
    },
  ],
  structured_insights: [
    {
      id: 'ins_1',
      type: 'pain_point',
      title: 'Hostel Dining Monotony',
      description: 'The student archetype experiences high friction during exam periods with hostel food.',
      supporting_turn_numbers: [2],
      confidence: 0.9,
      is_synthetic: true,
      created_at: new Date().toISOString(),
    },
  ],
  suggested_questions: [
    'How much would you pay per month for an alternative meal service?',
    'What payment method do you use most frequently?',
  ],
};

describe('Adaptive Persona Interviews (Part 6)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders study-level interviews hub with metrics and interview cards', async () => {
    vi.mocked(api.getStudyInterviewMetrics).mockResolvedValue({
      total_interviews: 3,
      active_interviews: 1,
      completed_interviews: 2,
      total_insights_generated: 7,
    });
    vi.mocked(api.listStudyInterviews).mockResolvedValue({
      interviews: [mockInterview],
      total: 1,
    });

    render(
      <InterviewsView
        studyId="study_123"
        onOpenInterview={vi.fn()}
        onNavigateToPersonas={vi.fn()}
      />
    );

    expect(screen.getByText('Customer Interview Lab')).toBeDefined();
    await waitFor(() => {
      expect(screen.getByText('Nadia Rahman')).toBeDefined();
      expect(screen.getByText('Problem & Pain Point Discovery')).toBeDefined();
      expect(screen.getByText('Continue Interview')).toBeDefined();
    });
  });

  it('opens and submits StartInterviewModal with selected objective and length tier', async () => {
    vi.mocked(api.startPersonaInterview).mockResolvedValue(mockInterview);
    const onStarted = vi.fn();
    const onClose = vi.fn();

    render(
      <StartInterviewModal
        isOpen={true}
        onClose={onClose}
        persona={mockPersona}
        studyId="study_123"
        onInterviewStarted={onStarted}
      />
    );

    expect(screen.getByText('Interview Nadia Rahman')).toBeDefined();
    expect(screen.getByText(/Synthetic Persona/i)).toBeDefined();

    // Click Pricing Objective preset
    const pricingObj = screen.getByText('Pricing & Willingness to Pay');
    fireEvent.click(pricingObj);

    // Click Start Interview button
    const startBtn = screen.getByText('Start Adaptive Interview');
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(api.startPersonaInterview).toHaveBeenCalledWith(
        'study_123',
        'per_nadia',
        expect.objectContaining({
          objective: 'Pricing & Willingness to Pay',
        })
      );
      expect(onStarted).toHaveBeenCalledWith('int_001');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('renders InterviewWorkspace with transcript, suggestions, provenance and insights', async () => {
    vi.mocked(api.getStudyInterviewDetail).mockResolvedValue(mockDetail);
    vi.mocked(api.getStudyPersonaDetail).mockResolvedValue(mockPersona);
    const donePayload = {
      reply: '৳2,000 is way above my ৳400 monthly allowance.',
      turn_number: 4,
      turn_count: 4,
      max_turns: 14,
      is_finished: false,
      topic: 'pricing_budget',
      topics_explored: { pain_points: 'explored', pricing_budget: 'explored' },
      suggested_questions: ['What if it were ৳250/mo?'],
      latency_ms: 250,
      served_by: 'openrouter/qwen3.5',
    };
    // Streaming path: two deltas, then the canonical done payload.
    vi.mocked(api.sendInterviewMessageStream).mockImplementation(
      async (_s: string, _i: string, _c: string, onDelta: (t: string) => void) => {
        onDelta('৳2,000 is way above ');
        onDelta('my ৳400 monthly allowance.');
        return donePayload;
      }
    );

    render(
      <InterviewWorkspace
        studyId="study_123"
        interviewId="int_001"
        onBackToInterviews={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText('Nadia Rahman').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/How do you handle meals during finals/i)).toBeDefined();
      expect(screen.getByText(/I usually eat at the dorm canteen/i)).toBeDefined();
    });

    // Provenance is honest and visible on demand: the "Route" disclosure
    // reveals the concrete serving route instead of printing it as chrome.
    expect(screen.queryByText(/openrouter\/qwen3\.5/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /^Route$/ }));
    expect(screen.getByText(/openrouter\/qwen3\.5/)).toBeDefined();

    // Structured insights render with turn references.
    expect(screen.getByText('Hostel Dining Monotony')).toBeDefined();
    expect(screen.getByText('T2')).toBeDefined();

    // Suggested question chip sends the real message through the STREAM path.
    const suggestionPill = screen.getByText(
      'How much would you pay per month for an alternative meal service?'
    );
    fireEvent.click(suggestionPill);

    await waitFor(() => {
      expect(api.sendInterviewMessageStream).toHaveBeenCalledWith(
        'study_123',
        'int_001',
        'How much would you pay per month for an alternative meal service?',
        expect.any(Function)
      );
    });

    // The persona's reply lands in the transcript with its new suggestion.
    await waitFor(() => {
      expect(screen.getByText(/way above my ৳400 monthly allowance/i)).toBeDefined();
    });
  });

  it('returns the question to the composer and shows an honest error when a turn fails', async () => {
    vi.mocked(api.getStudyInterviewDetail).mockResolvedValue(mockDetail);
    vi.mocked(api.getStudyPersonaDetail).mockResolvedValue(mockPersona);
    const typedErr = new Error('No LLM route could serve this request') as Error & { kind?: string };
    typedErr.kind = 'no_route';
    vi.mocked(api.sendInterviewMessageStream).mockRejectedValue(typedErr);

    render(
      <InterviewWorkspace
        studyId="study_123"
        interviewId="int_001"
        onBackToInterviews={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/dorm canteen/i)).toBeDefined();
    });

    const input = screen.getByLabelText(/Interview question for/i);
    fireEvent.change(input, { target: { value: 'Would you pay 500 taka?' } });
    fireEvent.click(screen.getByLabelText('Send question'));

    await waitFor(() => {
      // Failure is classified (no fabricated persona reply) …
      expect(screen.getByText('No model route available')).toBeDefined();
    });
    // … and the unanswered question is preserved in the composer for retry.
    expect((input as HTMLTextAreaElement).value).toBe('Would you pay 500 taka?');
  });
});

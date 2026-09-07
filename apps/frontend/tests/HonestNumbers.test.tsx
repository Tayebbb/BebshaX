import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';
import { BehavioralTestingView } from '../src/components/dashboard/views/BehavioralTestingView';
import { InterviewsView } from '../src/components/dashboard/views/InterviewsView';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';
import type { BehavioralTest } from '../src/types';

/**
 * GROUP F — honest numbers. Unmeasured values render as "—" (or are omitted),
 * 0 stays a real 0, and sample/demo modes announce themselves.
 */

const baseTest = (overrides: Partial<BehavioralTest['latest_run']>): BehavioralTest =>
  ({
    id: `bt_${Math.random().toString(36).slice(2, 7)}`,
    study_id: 'std_1',
    name: 'Pricing Test',
    description: 'desc',
    test_type: 'pricing_test',
    configuration: {},
    status: 'completed',
    scenarios: [],
    run_count: 1,
    latest_run: {
      id: 'run_1',
      status: 'completed',
      persona_count: 4,
      completed_at: '2026-09-01T10:00:00Z',
      ...overrides,
    },
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
  }) as unknown as BehavioralTest;

describe('BehavioralTestingView likelihood is measured or "—"', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    api.setMockMode(true);
    vi.spyOn(api, 'getBehavioralMetrics').mockResolvedValue({
      study_id: 'std_1',
      total_tests: 2,
      total_runs: 2,
      completed_runs: 2,
      total_personas_simulated: 8,
      average_buy_likelihood: 0.5,
      average_buy_likelihood_percentage: 50,
    });
  });

  it('renders "—" for a missing average_likelihood and "0%" for a real zero — never a fabricated 50%', async () => {
    vi.spyOn(api, 'getBehavioralTests').mockResolvedValue([
      { ...baseTest({ average_likelihood: undefined }), name: 'No likelihood yet' },
      { ...baseTest({ average_likelihood: 0 }), name: 'Nobody would buy' },
    ]);

    render(<BehavioralTestingView studyId="std_1" onOpenTest={vi.fn()} />);

    await screen.findByText('No likelihood yet');
    const cards = screen.getAllByText('Likelihood').map((el) => el.parentElement as HTMLElement);
    const values = cards.map((c) => c.textContent?.replace('Likelihood', '').trim());
    expect(values).toContain('—');
    expect(values).toContain('0%');
    expect(values).not.toContain('50%');
  });
});

describe('InterviewsView never invents a max_turns', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    api.setMockMode(true);
    vi.spyOn(api, 'getStudyInterviewMetrics').mockResolvedValue({
      total_interviews: 2,
      active_interviews: 1,
      completed_interviews: 1,
      total_insights_generated: 0,
    });
  });

  it('shows "Turns: N / max" only when max_turns is present', async () => {
    vi.spyOn(api, 'listStudyInterviews').mockResolvedValue({
      interviews: [
        {
          id: 'i_known',
          study_id: 'std_1',
          persona_id: 'p1',
          persona_name: 'Known Max',
          persona_version: 1,
          objective: 'Problem & Pain Point Discovery',
          interview_type: 'adaptive_persona',
          length_tier: 'standard',
          max_turns: 6,
          status: 'active',
          topics_explored: {},
          question_count: 2,
          turn_count: 2,
          created_at: '2026-09-01T10:00:00Z',
        },
        {
          id: 'i_unknown',
          study_id: 'std_1',
          persona_id: 'p2',
          persona_name: 'Unknown Max',
          persona_version: 1,
          objective: 'Problem & Pain Point Discovery',
          interview_type: 'adaptive_persona',
          length_tier: 'standard',
          max_turns: undefined,
          status: 'active',
          topics_explored: {},
          question_count: 3,
          turn_count: 3,
          created_at: '2026-09-01T10:00:00Z',
        },
      ] as any,
      total: 2,
    });

    render(<InterviewsView studyId="std_1" onOpenInterview={vi.fn()} onNavigateToPersonas={vi.fn()} />);

    const known = (await screen.findByText('Known Max')).closest('.group') as HTMLElement;
    expect(within(known).getByText(/Turns:/)).toHaveTextContent('Turns: 2 / 6');
    const unknown = screen.getByText('Unknown Max').closest('.group') as HTMLElement;
    expect(within(unknown).getByText(/Turns:/)).toHaveTextContent(/^Turns: 3$/);
    expect(within(unknown).getByText(/Turns:/)).not.toHaveTextContent('14');
  });
});

describe('Dashboard honesty banners', () => {
  beforeEach(() => {
    api.setMockMode(true);
    window.history.pushState({}, '', '/create-study');
  });

  const renderDashboard = (health?: { demo_mode: boolean }) =>
    render(
      <NavigationProvider>
        <AuthProvider>
          <DashboardLayout
            health={health ? { status: 'ok', app: 'bebshax', version: '0', environment: 'test', demo_mode: health.demo_mode } : null}
          />
        </AuthProvider>
      </NavigationProvider>
    );

  it('announces sample data in mock mode and cached results in demo mode', async () => {
    renderDashboard({ demo_mode: true });
    await waitFor(() => {
      expect(screen.getByTestId('mock-mode-banner')).toHaveTextContent(/Showing sample data \(mock mode\)/);
    });
    expect(screen.getByTestId('demo-mode-banner')).toHaveTextContent(/Demo mode — cached results are labeled/);
  });

  it('omits the demo banner when the backend is not in demo mode', async () => {
    renderDashboard({ demo_mode: false });
    await waitFor(() => expect(screen.getByTestId('mock-mode-banner')).toBeInTheDocument());
    expect(screen.queryByTestId('demo-mode-banner')).not.toBeInTheDocument();
  });
});

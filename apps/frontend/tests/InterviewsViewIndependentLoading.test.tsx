import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InterviewsView } from '../src/components/dashboard/views/InterviewsView';
import { api } from '../src/services/api';
import type { Interview, InterviewMetrics } from '../src/types';

vi.mock('../src/services/api', () => ({
  api: {
    listStudyInterviews: vi.fn(),
    getStudyInterviewMetrics: vi.fn(),
  },
}));

function deferred<Value>() {
  let resolve!: (value: Value) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const interview: Interview = {
  id: 'interview-current',
  study_id: 'study-current',
  persona_id: 'persona-current',
  persona_version: 1,
  persona_name: 'Current Persona',
  objective: 'problem_discovery',
  interview_type: 'adaptive_persona',
  length_tier: 'standard',
  max_turns: 14,
  status: 'active',
  topics_explored: {},
  question_count: 2,
  turn_count: 4,
  created_at: '2026-09-09T00:00:00Z',
};

const metrics: InterviewMetrics = {
  total_interviews: 23,
  active_interviews: 11,
  completed_interviews: 12,
  total_insights_generated: 37,
};

function listResponse(interviews: Interview[]) {
  return { interviews, total: interviews.length };
}

const props = {
  studyId: 'study-current',
  onOpenInterview: vi.fn(),
  onNavigateToPersonas: vi.fn(),
};

describe('InterviewsView independent request loading', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('displays the list while metrics are pending and updates metrics when ready', async () => {
    const pendingMetrics = deferred<InterviewMetrics>();
    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValue(pendingMetrics.promise);

    render(<InterviewsView {...props} />);

    expect(await screen.findByText('Current Persona')).toBeInTheDocument();
    expect(screen.queryByText('Loading study interviews...')).not.toBeInTheDocument();

    await act(async () => pendingMetrics.resolve(metrics));

    expect(screen.getByText('23')).toBeInTheDocument();
  });

  it('shows pending metrics as unknown instead of zero', async () => {
    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([]));
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValue(deferred<InterviewMetrics>().promise);

    render(<InterviewsView {...props} />);

    expect(await screen.findByText('No Interviews Found')).toBeInTheDocument();
    expect(screen.getByText('Loading interview metrics...')).toBeInTheDocument();
    expect(screen.queryAllByText('0')).toHaveLength(0);
  });

  it('keeps the list loading independently when metrics fail first and allows retry', async () => {
    const pendingList = deferred<ReturnType<typeof listResponse>>();
    vi.mocked(api.listStudyInterviews).mockReturnValueOnce(pendingList.promise);
    vi.mocked(api.getStudyInterviewMetrics).mockRejectedValueOnce(new Error('Metrics offline'));

    render(<InterviewsView {...props} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load interview metrics: Metrics offline');
    expect(screen.getByText('Loading study interviews...')).toBeInTheDocument();
    expect(screen.queryAllByText('0')).toHaveLength(0);
    await act(async () => pendingList.resolve(listResponse([interview])));
    expect(screen.getByText('Current Persona')).toBeInTheDocument();

    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics).mockResolvedValue(metrics);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('23')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows a list failure without presenting it as an empty list while metrics succeed', async () => {
    vi.mocked(api.listStudyInterviews).mockRejectedValue(new Error('List offline'));
    vi.mocked(api.getStudyInterviewMetrics).mockResolvedValue(metrics);

    render(<InterviewsView {...props} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to load interviews: List offline');
    expect(screen.getByText('23')).toBeInTheDocument();
    expect(screen.queryByText('No Interviews Found')).not.toBeInTheDocument();
  });

  it('shows both request failures with honest fallback errors for non-Error rejections', async () => {
    vi.mocked(api.listStudyInterviews).mockRejectedValue(null);
    vi.mocked(api.getStudyInterviewMetrics).mockRejectedValue('offline');

    render(<InterviewsView {...props} />);

    expect(await screen.findAllByRole('alert')).toHaveLength(2);
    expect(screen.getByText('Failed to load interviews: Please retry.')).toBeInTheDocument();
    expect(screen.getByText('Failed to load interview metrics: Please retry.')).toBeInTheDocument();
  });

  it.each(['study', 'status', 'objective', 'search'] as const)(
    'ignores old successful responses after a %s change',
    async (change) => {
      const oldList = deferred<ReturnType<typeof listResponse>>();
      const oldMetrics = deferred<InterviewMetrics>();
      vi.mocked(api.listStudyInterviews)
        .mockReturnValueOnce(oldList.promise)
        .mockResolvedValue(listResponse([{ ...interview, persona_name: 'New Persona' }]));
      vi.mocked(api.getStudyInterviewMetrics)
        .mockReturnValueOnce(oldMetrics.promise)
        .mockResolvedValue(metrics);

      const view = render(<InterviewsView {...props} />);
      if (change === 'study') {
        view.rerender(<InterviewsView {...props} studyId="study-new" />);
      } else if (change === 'search') {
        const input = screen.getByPlaceholderText('Search by persona name, objective, or topic...');
        fireEvent.change(input, { target: { value: 'New' } });
        fireEvent.submit(input.closest('form')!);
      } else {
        fireEvent.change(screen.getAllByRole('combobox')[change === 'status' ? 0 : 1], {
          target: { value: change === 'status' ? 'completed' : 'pricing_wtp' },
        });
      }

      expect(await screen.findByText('New Persona')).toBeInTheDocument();
      await act(async () => {
        oldList.resolve(listResponse([interview]));
        oldMetrics.resolve({ ...metrics, total_interviews: 99 });
      });

      expect(screen.getByText('New Persona')).toBeInTheDocument();
      expect(screen.getByText('23')).toBeInTheDocument();
      expect(screen.queryByText('Current Persona')).not.toBeInTheDocument();
      expect(screen.queryByText('99')).not.toBeInTheDocument();
    },
  );

  it('ignores stale failures and finalizers while the new study is still loading', async () => {
    const oldList = deferred<ReturnType<typeof listResponse>>();
    const oldMetrics = deferred<InterviewMetrics>();
    const newList = deferred<ReturnType<typeof listResponse>>();
    const newMetrics = deferred<InterviewMetrics>();
    vi.mocked(api.listStudyInterviews).mockReturnValueOnce(oldList.promise).mockReturnValueOnce(newList.promise);
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValueOnce(oldMetrics.promise).mockReturnValueOnce(newMetrics.promise);

    const view = render(<InterviewsView {...props} />);
    view.rerender(<InterviewsView {...props} studyId="study-new" />);
    await act(async () => {
      oldList.reject(new Error('Stale list failure'));
      oldMetrics.reject(new Error('Stale metrics failure'));
    });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('Loading study interviews...')).toBeInTheDocument();
    await act(async () => {
      newList.resolve(listResponse([]));
      newMetrics.resolve(metrics);
    });
    expect(screen.getByText('No Interviews Found')).toBeInTheDocument();
  });

  it('refreshes while metrics are pending and ignores the superseded metrics response', async () => {
    const oldMetrics = deferred<InterviewMetrics>();
    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValueOnce(oldMetrics.promise).mockResolvedValue(metrics);

    render(<InterviewsView {...props} />);
    await screen.findByText('Current Persona');
    const refresh = screen.getByRole('button', { name: 'Refresh interviews' });
    expect(refresh).toBeEnabled();
    fireEvent.click(refresh);
    expect(await screen.findByText('23')).toBeInTheDocument();
    await act(async () => oldMetrics.resolve({ ...metrics, total_interviews: 99 }));
    expect(screen.queryByText('99')).not.toBeInTheDocument();
    expect(screen.getByText('Current Persona')).toBeInTheDocument();
  });

  it('clears previous study metrics when the next study is pending', async () => {
    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics)
      .mockResolvedValueOnce(metrics)
      .mockReturnValueOnce(deferred<InterviewMetrics>().promise);

    const view = render(<InterviewsView {...props} />);
    await screen.findByText('23');
    await act(async () => view.rerender(<InterviewsView {...props} studyId="study-new" />));

    expect(screen.queryByText('23')).not.toBeInTheDocument();
    expect(screen.getByText('Loading interview metrics...')).toBeInTheDocument();
  });

  it.each(['interview', 'personas'] as const)('invalidates pending metrics immediately on %s navigation', async (destination) => {
    const pendingMetrics = deferred<InterviewMetrics>();
    vi.mocked(api.listStudyInterviews).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValue(pendingMetrics.promise);

    render(<InterviewsView {...props} />);
    await screen.findByText('Current Persona');
    fireEvent.click(destination === 'interview'
      ? screen.getByText('Current Persona')
      : screen.getByRole('button', { name: 'New Persona Interview' }));
    expect(destination === 'interview' ? props.onOpenInterview : props.onNavigateToPersonas).toHaveBeenCalled();
    await act(async () => pendingMetrics.reject(new Error('Late metrics failure')));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('ignores requests from an unmounted view after another view mounts', async () => {
    const oldList = deferred<ReturnType<typeof listResponse>>();
    const oldMetrics = deferred<InterviewMetrics>();
    vi.mocked(api.listStudyInterviews).mockReturnValueOnce(oldList.promise).mockResolvedValue(listResponse([interview]));
    vi.mocked(api.getStudyInterviewMetrics).mockReturnValueOnce(oldMetrics.promise).mockResolvedValue(metrics);

    const previous = render(<InterviewsView {...props} />);
    previous.unmount();
    render(<InterviewsView {...props} studyId="study-new" />);
    await screen.findByText('Current Persona');
    await act(async () => {
      oldList.reject(new Error('Unmounted list failure'));
      oldMetrics.reject(new Error('Unmounted metrics failure'));
    });

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByText('23')).toBeInTheDocument();
  });
});
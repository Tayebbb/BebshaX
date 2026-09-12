import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BehavioralTestDetailView } from '../src/components/dashboard/views/BehavioralTestDetailView';
import { api } from '../src/services/api';
import { BehavioralTestingView } from '../src/components/dashboard/views/BehavioralTestingView';
import { BehavioralComparisonView } from '../src/components/dashboard/views/BehavioralComparisonView';
import { EvidenceLaboratoryView } from '../src/components/dashboard/views/EvidenceLaboratoryView';
import { BehavioralTestRun } from '../src/types';

const fixture = (id: string) => ({ id, study_id: id, name: `Test ${id}`, test_type: 'purchase_decision', configuration: {}, status: 'draft', scenarios: [], run_count: 0 });

const runFixture = (id: string): BehavioralTestRun => ({
  id, behavioral_test_id: id, study_id: id,
  scenario_snapshot: { title: `Scenario ${id}`, scenario_text: `Offer ${id}`, structured_parameters: {} },
  target_population_type: 'selected_personas', target_persona_ids: [`persona-${id}`],
  status: 'completed', persona_count: 1, completed_count: 1, failed_count: 0,
  aggregate_metrics: { total_personas: 1, positive_count: 1, neutral_count: 0, negative_count: 0, positive_percentage: 100, neutral_percentage: 0, negative_percentage: 0, average_likelihood: 0.8, average_likelihood_percentage: 80, confidence_breakdown: { high: 1 } },
  segment_analysis: [], cross_persona_patterns: { top_motivators: [], top_objections: [], top_decision_factors: [] }, risks: [], opportunities: [],
});

describe('Frontend asynchronous view ownership', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); api.setMockMode(true); });

  it('keeps behavioral test B when the previous test A detail resolves late', async () => {
    let finishPrevious!: (value: ReturnType<typeof fixture>) => void;
    vi.spyOn(api, 'getBehavioralTestDetail').mockReturnValueOnce(new Promise((resolve) => { finishPrevious = resolve; }))
      .mockResolvedValueOnce(fixture('B'));
    vi.spyOn(api, 'getBehavioralTestRuns').mockResolvedValue([]);
    const view = render(<BehavioralTestDetailView studyId="A" testId="A" onBack={vi.fn()} />);
    const signal = vi.mocked(api.getBehavioralTestDetail).mock.calls[0][2];
    view.rerender(<BehavioralTestDetailView studyId="B" testId="B" onBack={vi.fn()} />);
    expect(await screen.findByText('Test B')).toBeInTheDocument();
    expect(signal?.aborted).toBe(true);
    await act(async () => { finishPrevious(fixture('A')); });
    expect(screen.getByText('Test B')).toBeInTheDocument();
    expect(screen.queryByText('Test A')).not.toBeInTheDocument();
  });

  it('renders behavioral tests while independent metrics are still pending', async () => {
    vi.spyOn(api, 'getBehavioralTests').mockResolvedValue([fixture('ready')]);
    vi.spyOn(api, 'getBehavioralMetrics').mockReturnValue(new Promise(() => {}));
    render(<BehavioralTestingView studyId="ready" onOpenTest={vi.fn()} />);
    expect(await screen.findByText('Test ready')).toBeInTheDocument();
  });

  it('keeps the last selected run when an earlier selection resolves late', async () => {
    let finishPrevious!: (run: BehavioralTestRun) => void;
    vi.spyOn(api, 'getBehavioralTestDetail').mockResolvedValue(fixture('test'));
    vi.spyOn(api, 'getBehavioralTestRuns').mockResolvedValue([runFixture('A'), runFixture('B'), runFixture('C')]);
    vi.spyOn(api, 'getBehavioralRunResults').mockResolvedValueOnce(runFixture('A'))
      .mockReturnValueOnce(new Promise((resolve) => { finishPrevious = resolve; }))
      .mockResolvedValueOnce(runFixture('C'));
    vi.spyOn(api, 'triggerBehavioralTestRun').mockReturnValue(new Promise(() => {}));
    render(<BehavioralTestDetailView studyId="study" testId="test" onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Run #2/ }));
    fireEvent.click(screen.getByRole('button', { name: /Run #1/ }));
    await act(async () => { finishPrevious(runFixture('B')); });
    expect(screen.getByRole('button', { name: /Run #1/ })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Re-Run Simulation' }));
    expect(api.triggerBehavioralTestRun).toHaveBeenCalledWith('study', 'test', expect.objectContaining({ scenario_text: 'Offer C', target_persona_ids: ['persona-C'] }), expect.any(AbortSignal));
  });

  it('does not select a late rerun or refetch the previous test after changing tests', async () => {
    let finishPrevious!: (run: BehavioralTestRun) => void;
    vi.spyOn(api, 'getBehavioralTestDetail').mockResolvedValueOnce(fixture('A')).mockResolvedValueOnce(fixture('B'));
    vi.spyOn(api, 'getBehavioralTestRuns').mockResolvedValueOnce([runFixture('A')]).mockResolvedValueOnce([runFixture('B')]);
    vi.spyOn(api, 'getBehavioralRunResults').mockResolvedValueOnce(runFixture('A')).mockResolvedValueOnce(runFixture('B'));
    vi.spyOn(api, 'triggerBehavioralTestRun').mockReturnValueOnce(new Promise((resolve) => { finishPrevious = resolve; }));
    const view = render(<BehavioralTestDetailView studyId="A" testId="A" onBack={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Re-Run Simulation' }));
    view.rerender(<BehavioralTestDetailView studyId="B" testId="B" onBack={vi.fn()} />);
    expect(await screen.findByText('Test B')).toBeInTheDocument();
    await act(async () => { finishPrevious(runFixture('late-A')); });
    expect(screen.getByText('Test B')).toBeInTheDocument();
    expect(screen.queryByText('Test A')).not.toBeInTheDocument();
    expect(api.getBehavioralTestDetail).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: 'Re-Run Simulation' })).toBeEnabled();
  });

  it('does not restart comparison when equivalent selected IDs are rerendered in a new array', async () => {
    vi.spyOn(api, 'compareBehavioralRuns').mockResolvedValue({ study_id: 'study', compared_run_count: 1, runs: [runFixture('A')] });
    const onBack = vi.fn();
    const view = render(<BehavioralComparisonView studyId="study" runIds={['A']} onBack={onBack} />);
    await screen.findByText('Scenario A');
    view.rerender(<BehavioralComparisonView studyId="study" runIds={['A']} onBack={onBack} />);
    await act(async () => {});
    expect(api.compareBehavioralRuns).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Scenario A')).toBeInTheDocument();
  });

  it('keeps the current comparison when the previous selected runs resolve late', async () => {
    let finishPrevious!: (value: Awaited<ReturnType<typeof api.compareBehavioralRuns>>) => void;
    vi.spyOn(api, 'compareBehavioralRuns').mockReturnValueOnce(new Promise((resolve) => { finishPrevious = resolve; }))
      .mockResolvedValueOnce({ study_id: 'study', compared_run_count: 1, runs: [runFixture('B')] });
    const view = render(<BehavioralComparisonView studyId="study" runIds={['A']} onBack={vi.fn()} />);
    view.rerender(<BehavioralComparisonView studyId="study" runIds={['B']} onBack={vi.fn()} />);
    await screen.findByText('Scenario B');
    await act(async () => { finishPrevious({ study_id: 'study', compared_run_count: 1, runs: [runFixture('A')] }); });
    expect(screen.getByText('Scenario B')).toBeInTheDocument();
    expect(screen.queryByText('Scenario A')).not.toBeInTheDocument();
  });

  it('ignores research completion after leaving the original study', async () => {
    api.setMockMode(true);
    let finish!: (value: Awaited<ReturnType<typeof api.startResearch>>) => void;
    vi.spyOn(api, 'startResearch').mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    vi.spyOn(api, 'getEvidenceClaims').mockResolvedValue([]);
    vi.spyOn(api, 'getEvidenceSources').mockResolvedValue([]);
    vi.spyOn(api, 'getResearchRuns').mockResolvedValue([]);
    const summary = vi.spyOn(api, 'getEvidenceSummary').mockRejectedValue(new Error('No coverage measurement'));
    const view = render(<EvidenceLaboratoryView studyId="previous-study" />);
    fireEvent.click(screen.getByRole('button', { name: 'Run Research' }));
    view.rerender(<EvidenceLaboratoryView studyId="current-study" />);
    await screen.findAllByText('Unknown');
    const calls = summary.mock.calls.length;
    await act(async () => { finish({ id: 'finished', study_id: 'previous-study', status: 'completed', query_count: 0, source_count: 0, claim_count: 0, queries: [], started_at: '2026-09-09', created_at: '2026-09-09' }); });
    expect(summary).toHaveBeenCalledTimes(calls);
    expect(screen.queryByText(/Research complete/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Research' })).toBeEnabled();
  });

  it('aborts evidence transport on departure and applies a bounded read deadline', async () => {
    api.setMockMode(false);
    const timeout = vi.spyOn(AbortSignal, 'timeout');
    const signals: AbortSignal[] = [];
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockImplementation(async (_input, init) => {
      const signal = init?.signal;
      if (signal) signals.push(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener('abort', () => reject(signal.reason), { once: true });
      });
    }));
    const view = render(<EvidenceLaboratoryView studyId="transport-owner" />);
    expect(signals).toHaveLength(4);
    view.unmount();

    expect(signals.every((signal) => signal.aborted)).toBe(true);
    expect(timeout).toHaveBeenCalledWith(30000);
  });
});
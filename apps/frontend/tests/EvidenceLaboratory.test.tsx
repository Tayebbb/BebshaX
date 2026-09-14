import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { EvidenceLaboratoryView } from '../src/components/dashboard/views/EvidenceLaboratoryView';
import { api } from '../src/services/api';
import type { ResearchRun } from '../src/types';

describe('EvidenceLaboratoryView Component', () => {
  beforeEach(async () => {
    api.setMockMode(true);
    await api.resetMockStore();
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it('renders coverage metrics and claims tab by default', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    expect(screen.getByText('Evidence Laboratory')).toBeInTheDocument();
    expect(screen.getByText('Evidence Coverage')).toBeInTheDocument();
    expect(screen.getByText('Run Research')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Key Claims (5)')).toBeInTheDocument();
      expect(screen.getByText('Sources & Chunks (4)')).toBeInTheDocument();
    });
  });

  it('filters claims when clicking status filter pills', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Students experience significant fragmentation/i)).toBeInTheDocument();
    });

    // Click "Unsupported (Red)" filter pill
    const unsupportedPill = screen.getByRole('button', { name: /Unsupported \(Red\)/i });
    fireEvent.click(unsupportedPill);

    await waitFor(() => {
      expect(screen.getByText(/Students will pay ৳1,000\+\/month/i)).toBeInTheDocument();
      expect(screen.queryByText(/Students experience significant fragmentation/i)).not.toBeInTheDocument();
    });
  });

  it('filters claims using the live search input', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Students experience significant fragmentation/i)).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search claims & evidence.../i);
    fireEvent.change(searchInput, { target: { value: 'mobile payment' } });

    await waitFor(() => {
      expect(screen.getByText(/Target users show strong willingness to pay/i)).toBeInTheDocument();
      expect(screen.queryByText(/Students experience significant fragmentation/i)).not.toBeInTheDocument();
    });
  });

  it('opens and closes the claim provenance inspection modal', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getAllByText(/Inspect Provenance/i).length).toBeGreaterThan(0);
    });

    const inspectButtons = screen.getAllByText(/Inspect Provenance/i);
    fireEvent.click(inspectButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/Claim Provenance Inspection/i)).toBeInTheDocument();
      expect(screen.getByText(/Why does BebshaX evaluate this as/i)).toBeInTheDocument();
    });

    const closeBtn = screen.getByRole('button', { name: /Close Inspection/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText(/Claim Provenance Inspection/i)).not.toBeInTheDocument();
    });
  });

  it('switches to Sources tab and renders source repository', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    await waitFor(() => {
      expect(screen.getByText(/Sources & Chunks/i)).toBeInTheDocument();
    });

    const sourcesTabBtn = screen.getByText(/Sources & Chunks/i);
    fireEvent.click(sourcesTabBtn);

    await waitFor(() => {
      expect(screen.getByText(/Reddit r\/bangladesh/i)).toBeInTheDocument();
      expect(screen.getByText(/The Daily Star Tech/i)).toBeInTheDocument();
      expect(screen.getByText(/Survey Report: Tech spending/i)).toBeInTheDocument();
    });
  });

  it.each(['pending', 'failed'] as const)('renders loaded claims when optional coverage is %s and sources are still pending', async (state) => {
    vi.spyOn(api, 'getEvidenceSummary').mockImplementation(() => state === 'pending'
      ? new Promise(() => {}) : Promise.reject(new Error('Coverage unavailable')));
    vi.spyOn(api, 'getEvidenceSources').mockReturnValue(new Promise(() => {}));
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    expect(await screen.findByText(/Students experience significant fragmentation/i)).toBeInTheDocument();
    expect(screen.queryByText('0 supported claims')).not.toBeInTheDocument();
  });

  it('shows a failed source read instead of an empty source repository', async () => {
    vi.spyOn(api, 'getEvidenceSources').mockRejectedValue(new Error('Source storage unavailable'));
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    await screen.findByText(/Students experience significant fragmentation/i);

    fireEvent.click(screen.getByText(/Sources & Chunks/i));

    expect(await screen.findByRole('alert')).toHaveTextContent('Source storage unavailable');
    expect(screen.queryByText(/No sources|No evidence sources/i)).not.toBeInTheDocument();
  });

  it('supports arrow-key selection and linked panels for evidence tabs', async () => {
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    const claimsTab = await screen.findByRole('tab', { name: /Key Claims/i });
    claimsTab.focus();
    fireEvent.keyDown(claimsTab, { key: 'ArrowRight' });

    const sourcesTab = screen.getByRole('tab', { name: /Sources & Chunks/i });
    expect(sourcesTab).toHaveFocus();
    expect(sourcesTab).toHaveAttribute('aria-selected', 'true');
    expect(claimsTab).toHaveAttribute('tabindex', '-1');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', sourcesTab.id);
  });

  const acceptedRun = (overrides: Partial<ResearchRun> = {}): ResearchRun => ({
    id: 'run_accepted', study_id: 'study_test_1', status: 'pending', current_step: 'queued',
    query_count: 0, source_count: 0, claim_count: 0, queries: [], error_message: null,
    started_at: '2026-09-12T20:29:02Z', created_at: '2026-09-12T20:29:02Z', ...overrides,
  });

  it('polls an accepted research run to completion instead of declaring it done on acceptance', async () => {
    vi.spyOn(api, 'startResearch').mockResolvedValue(acceptedRun());
    const getRun = vi.spyOn(api, 'getResearchRun')
      .mockResolvedValueOnce(acceptedRun({ current_step: 'searching_evidence', query_count: 4 }))
      .mockResolvedValueOnce(acceptedRun({ status: 'completed', current_step: 'completed', query_count: 4, source_count: 3, claim_count: 6 }));
    // Collapse only the 2.5s poll interval; RTL's own waitFor timers must keep real timing.
    const realSetTimeout = globalThis.setTimeout;
    vi.spyOn(globalThis, 'setTimeout').mockImplementation(((handler: TimerHandler, ms?: number, ...args: unknown[]) => {
      if (ms === 2500 && typeof handler === 'function') {
        queueMicrotask(() => handler(...args));
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }
      return realSetTimeout(handler as () => void, ms, ...args);
    }) as typeof setTimeout);
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    await screen.findByText(/Students experience significant fragmentation/i);

    fireEvent.click(screen.getByRole('button', { name: /Run Research/i }));

    expect(await screen.findByText(/Research complete — 6 claims extracted from 3 sources/)).toBeInTheDocument();
    expect(getRun).toHaveBeenCalledTimes(2);
    expect(getRun).toHaveBeenCalledWith('study_test_1', 'run_accepted', expect.any(AbortSignal));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces the recorded failure reason when a polled research run fails', async () => {
    vi.spyOn(api, 'startResearch').mockResolvedValue(acceptedRun());
    vi.spyOn(api, 'getResearchRun').mockResolvedValue(acceptedRun({
      status: 'failed', current_step: 'failed', error_message: 'No model route could plan the research',
    }));
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    await screen.findByText(/Students experience significant fragmentation/i);

    fireEvent.click(screen.getByRole('button', { name: /Run Research/i }));

    await waitFor(() => expect(api.startResearch).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getResearchRun).toHaveBeenCalledTimes(1));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Research run failed: No model route could plan the research. Nothing was added — you can retry.');
    expect(screen.queryByText(/Research complete/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run Research/i })).toBeEnabled();
  });

  it('shows the failure reason and live step for runs in the research history', async () => {
    vi.spyOn(api, 'getResearchRuns').mockResolvedValue([
      acceptedRun({ id: 'run_live', status: 'searching_evidence', current_step: 'searching_evidence', query_count: 5 }),
      acceptedRun({ id: 'run_dead', status: 'failed', current_step: 'failed', error_message: 'Provider quota exhausted' }),
    ]);
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    fireEvent.click(await screen.findByRole('tab', { name: /Research History/i }));

    expect(await screen.findByText('Searching public sources for evidence… (5 queries)')).toBeInTheDocument();
    expect(screen.getByText('Provider quota exhausted')).toBeInTheDocument();
  });

  const summaryWithRun = async (run: Partial<ResearchRun>) => {
    const real = await api.getEvidenceSummary('study_test_1');
    return { ...real, latest_run: { ...acceptedRun(run) } as never };
  };

  it('follows a run that was already in flight when the page loaded instead of offering a second one', async () => {
    // Live 2026-09-14: after a reload mid-run the button re-enabled and nothing
    // showed the run executing; three parallel runs were started for one study.
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(await summaryWithRun({ id: 'run_live', status: 'searching_evidence', current_step: 'searching_evidence', query_count: 2 }));
    const getRun = vi.spyOn(api, 'getResearchRun')
      .mockResolvedValueOnce(acceptedRun({ id: 'run_live', status: 'completed', current_step: 'completed', query_count: 2, source_count: 1, claim_count: 2 }));
    const start = vi.spyOn(api, 'startResearch');
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    expect(await screen.findByText(/Research complete — 2 claims extracted from 1 sources/)).toBeInTheDocument();
    expect(getRun).toHaveBeenCalledWith('study_test_1', 'run_live', expect.any(AbortSignal));
    expect(start).not.toHaveBeenCalled();
  });

  it('announces a latest run that failed on the page, not only in the history tab', async () => {
    vi.spyOn(api, 'getEvidenceSummary').mockResolvedValue(await summaryWithRun({ id: 'run_dead', status: 'failed', current_step: 'failed', error_message: 'AllCandidatesFailed' }));
    render(<EvidenceLaboratoryView studyId="study_test_1" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Research run failed: AllCandidatesFailed');
    expect(screen.getByRole('button', { name: /Run Research/i })).toBeEnabled();
  });

  it('reports the server refusing a concurrent run instead of a generic failure', async () => {
    vi.spyOn(api, 'startResearch').mockRejectedValue(Object.assign(new Error('An evidence research run is already in progress for this study. Wait for it to finish or cancel it first.'), { status: 409 }));
    render(<EvidenceLaboratoryView studyId="study_test_1" />);
    await screen.findByText(/Students experience significant fragmentation/i);

    fireEvent.click(screen.getByRole('button', { name: /Run Research/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('already in progress');
  });
});

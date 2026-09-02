import { EvidenceSummary, ResearchStatus } from '../../../../types';

/** What Step 1 knows about the supporting-evidence attempt for this study.
 * Every state is something the app actually observed — there is no state that
 * claims evidence exists without a claim count behind it, and a run that blew
 * up is never reported as "nothing found". */
export type EvidenceProbe =
  | { state: 'checking' }
  | { state: 'searching' }
  | { state: 'found'; claims: number; sources: number }
  | { state: 'empty' }
  | { state: 'failed'; message?: string }
  | { state: 'timeout' }
  | { state: 'not_run' }
  | { state: 'unavailable' };

/** Terminal research statuses. Anything else the backend writes to
 * ResearchRuns.status means the run is still working. */
export const RESEARCH_TERMINAL: ResearchStatus[] = ['completed', 'failed'];

/** `idle` is the summary endpoint's stand-in for "no run exists", so it is not
 * in flight either. An unrecognised status counts as in flight: guessing
 * "finished" is what produces a false "no evidence found". */
export const isResearchInFlight = (status?: string | null): boolean =>
  !!status && status !== 'idle' && !RESEARCH_TERMINAL.includes(status as ResearchStatus);

/** The whole decision, given what the summary endpoint returned and how many
 * polls are left. Kept pure so every branch — especially "the run failed" vs
 * "the run found nothing" — is provable without timers. */
export const nextEvidenceProbe = (
  summary: EvidenceSummary | null | undefined,
  attemptsLeft: number,
): EvidenceProbe => {
  if (!summary) return { state: 'unavailable' };

  const run = summary.latest_run;
  if ((summary.total_claims ?? 0) > 0) {
    return { state: 'found', claims: summary.total_claims, sources: summary.total_sources ?? 0 };
  }
  if (run?.status === 'failed') {
    return { state: 'failed', message: run.error_message || undefined };
  }
  if (isResearchInFlight(run?.status ?? summary.research_status)) {
    // Polling is bounded, so the last attempt must resolve to something true
    // instead of leaving the line on "Looking for…" forever.
    return attemptsLeft > 0 ? { state: 'searching' } : { state: 'timeout' };
  }
  return { state: run ? 'empty' : 'not_run' };
};

import type { ResearchRun } from '../types';

/** Research runs are accepted (202) and progress through these steps in the background. */
export const RESEARCH_TERMINAL_STATES: ReadonlySet<string> = new Set([
  'completed', 'failed', 'cancelled', 'interrupted', 'timed_out',
]);

const RESEARCH_STEP_LABELS: Record<string, string> = {
  queued: 'Queued — waiting for a worker…',
  understanding_idea: 'Understanding the idea…',
  building_research_plan: 'Building the research plan…',
  searching_evidence: 'Searching public sources for evidence…',
  discovering_datasets: 'Discovering related datasets…',
  evaluating_datasets: 'Evaluating dataset candidates…',
  importing_datasets: 'Importing datasets…',
  extracting_evidence: 'Extracting and grading claims…',
};

export const isResearchRunSettled = (run: Pick<ResearchRun, 'status'>): boolean =>
  RESEARCH_TERMINAL_STATES.has(run.status);

export const researchProgressText = (
  run: Pick<ResearchRun, 'status' | 'current_step' | 'query_count' | 'source_count' | 'claim_count'>,
): string => {
  const step = run.current_step || run.status;
  const label = RESEARCH_STEP_LABELS[step] ?? `${step.replace(/_/g, ' ')}…`;
  const counts = [
    run.query_count ? `${run.query_count} queries` : null,
    run.source_count ? `${run.source_count} sources` : null,
    run.claim_count ? `${run.claim_count} claims` : null,
  ].filter(Boolean);
  return counts.length ? `${label} (${counts.join(', ')})` : label;
};

export const researchFailureText = (run: Pick<ResearchRun, 'status' | 'error_message'>): string => {
  const outcome = run.status === 'failed' ? 'failed' : run.status.replace(/_/g, ' ');
  const reason = run.error_message?.trim() || 'the run stopped before any evidence was saved';
  return `Research run ${outcome}: ${reason}. Nothing was added — you can retry.`;
};

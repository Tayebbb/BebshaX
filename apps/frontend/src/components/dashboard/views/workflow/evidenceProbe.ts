import { ResearchStatus } from '../../../../types';

/** What Step 1 knows about the supporting-evidence attempt for this study.
 * Every state is something the app actually observed — there is no state that
 * claims evidence exists without a claim count behind it. */
export type EvidenceProbe =
  | { state: 'checking' }
  | { state: 'searching' }
  | { state: 'found'; claims: number; sources: number }
  | { state: 'empty' }
  | { state: 'not_run' }
  | { state: 'unavailable' };

/** Research statuses that mean a run is still working. */
export const RESEARCH_IN_FLIGHT: ResearchStatus[] = [
  'pending',
  'planning',
  'discovering_datasets',
  'generating_queries',
  'collecting_sources',
  'processing_chunks',
  'extracting_evidence',
];

/**
 * Shared prop-level types for the extracted StudyWorkflowView step components.
 * State and handlers all live in StudyWorkflowView (the parent) — these types
 * only describe what flows down as props.
 */

/** Tooltip shown on every mutating CTA that is disabled because the study is
 * a read-only example (is_demo). */
export const READ_ONLY_TITLE =
  'Example study — read-only. Create your own study to run this step.';

export interface CopilotMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  isGoalCard?: boolean;
  goalCardData?: {
    title: string;
    summary: string;
    target_audience: string;
    core_hypothesis: string;
  };
  isRetryPrompt?: boolean;
  retryContent?: string;
}

/**
 * Shared prop-level types for the extracted StudyWorkflowView step components.
 * State and handlers all live in StudyWorkflowView (the parent) — these types
 * only describe what flows down as props.
 */
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
}

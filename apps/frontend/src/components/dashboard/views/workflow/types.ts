/**
 * Shared prop-level types for the extracted StudyWorkflowView step components.
 * State and handlers all live in StudyWorkflowView (the parent) — these types
 * only describe what flows down as props.
 */

/** Tooltip shown on every mutating CTA that is disabled because the study is
 * a read-only example (is_demo). */
export const READ_ONLY_TITLE =
  'Example study — read-only. Create your own study to run this step.';

/** Fallback persona count when no interview roles carry a count — shared by
 * StudyWorkflowView (generation request) and Step2Personas (skeleton grid). */
export const DEFAULT_PERSONA_COUNT = 6;

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
  /** Route that produced an assistant reply (`provider/model` or the template engine). */
  servedBy?: string;
  /** Backend reason the LLM path was bypassed — present only on template replies. */
  fallbackReason?: string | null;
  /** True when the reply is a keyword template, not model output (see isTemplateReply). */
  isTemplate?: boolean;
  /** Failure copy + request id for error bubbles so a judge can trace the request. */
  errorDetail?: string;
  requestId?: string | null;
}

/** The backend's keyword-template copilot engine — a reply served by it is NOT AI output. */
export const TEMPLATE_COPILOT_ROUTE = 'bebshax/copilot-engine';

export const isTemplateReply = (r: { served_by?: string; fallback_reason?: string | null }): boolean =>
  r.served_by === TEMPLATE_COPILOT_ROUTE || (typeof r.fallback_reason === 'string' && r.fallback_reason.length > 0);

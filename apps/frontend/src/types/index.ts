// Core TypeScript types matching docs/API_CONTRACT.md

import type { BigFivePersonality, DetailedAttributes } from './persona';

// Mirrors bebshax/llm/types.py::TaskType exactly (18 values).
export type TaskType =
  | "PERSONA_GENERATION"
  | "PERSONA_REFINEMENT"
  | "PERSONA_VALIDATION"
  | "PERSONA_INTERVIEW"
  | "PERSONA_RESPONSE"
  | "EVIDENCE_EXTRACTION"
  | "EVIDENCE_CLASSIFICATION"
  | "MEMORY_RETRIEVAL"
  | "MEMORY_SUMMARIZATION"
  | "CONTRADICTION_CHECK"
  | "CRITIC"
  | "REPORT_GENERATION"
  | "STRUCTURED_OUTPUT"
  | "BROWSER_AGENT"
  | "TOOL_CALLING"
  | "PERSONA_NARRATIVE"
  | "BEHAVIORAL_SIMULATION"
  | "EMERGENCY_FALLBACK";

// Mirrors bebshax/llm/failures.py::FailureKind exactly (13 kinds, closed taxonomy — R6).
export type FailureKind =
  | "TIMEOUT"
  | "CONNECTION"
  | "RATE_LIMITED"
  | "QUOTA_EXHAUSTED"
  | "SERVER_ERROR"
  | "PROVIDER_UNAVAILABLE"
  | "AUTH_INVALID"
  | "MODEL_UNAVAILABLE"
  | "CONTEXT_WINDOW_EXCEEDED"
  | "CAPABILITY_UNSUPPORTED"
  | "MALFORMED_RESPONSE"
  | "CONTENT_REFUSAL"
  | "INTERNAL_ERROR";

export const FAILURE_KINDS: readonly FailureKind[] = [
  "TIMEOUT",
  "CONNECTION",
  "RATE_LIMITED",
  "QUOTA_EXHAUSTED",
  "SERVER_ERROR",
  "PROVIDER_UNAVAILABLE",
  "AUTH_INVALID",
  "MODEL_UNAVAILABLE",
  "CONTEXT_WINDOW_EXCEEDED",
  "CAPABILITY_UNSUPPORTED",
  "MALFORMED_RESPONSE",
  "CONTENT_REFUSAL",
  "INTERNAL_ERROR",
];

/** Machine-readable error codes the backend envelope carries. */
export type ApiErrorCode =
  | "all_candidates_failed"
  | "context_window_exceeded"
  | "llm_error"
  | "validation_error"
  | "rate_limited"
  | "not_found"
  | "forbidden"
  | "unauthorized"
  | "conflict"
  | "payload_too_large"
  | "internal_error"
  | "database_unavailable";

/** One FastAPI/pydantic validation item (422 `detail` is an array of these). */
export interface ValidationItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

export interface ApiErrorAttempt {
  provider: string;
  model: string;
  failure_kind: FailureKind | string | null;
  fallback_reason: string | null;
}

/** Every backend error response body (see backend error handler contract). */
export interface ApiErrorBody {
  detail: string | ValidationItem[];
  error_code: ApiErrorCode | string;
  request_id: string;
  message?: string;
  llm_request_id?: string;
  attempts?: ApiErrorAttempt[];
  routing_path?: string[];
  estimated_tokens?: number;
  largest_window?: number | null;
}

export type ProvenanceClass = "OBSERVED" | "INFERRED" | "SYNTHETIC";

export type MemoryKind = "semantic" | "episodic" | "reflection";

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  demo_mode: boolean;
}

export interface AttemptRecord {
  attempt_number: number;
  provider: string;
  model: string;
  started_at: string;
  latency_ms: number | null;
  success: boolean;
  failure_kind: FailureKind | null;
  failure_detail: string | null;
  fallback_reason: string | null;
  notes: string[];
}

export interface ProvenanceRecord {
  request_id: string;
  task: TaskType;
  pool: string | null;
  persona_id: string | null;
  conversation_id: string | null;
  created_at: string;
  routing_path: string[];
  attempts: AttemptRecord[];
  served_by_provider: string | null;
  served_by_model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_latency_ms: number | null;
  success: boolean;
}

export interface ProviderStatus {
  name: string;
  type: "keyless" | "free_tier_key" | "local_fallback";
  status: "healthy" | "degraded" | "down";
  available_models: number;
  /** Null when the backend has not measured it — render as "—", never 0. */
  active_cooldowns: number | null;
}

export interface PoolStatus {
  name: string;
  max_concurrency: number;
  /** Null when the backend has not measured it — render as "—", never 0. */
  active_requests: number | null;
  candidates_count: number;
}

export interface RoutesStatusResponse {
  providers: ProviderStatus[];
  pools: PoolStatus[];
}

export interface Business {
  id: string;
  name: string;
  description: string;
  industry: string;
  target_market: string;
  persona_count: number;
  created_at: string;
}

export interface Evidence {
  source: string;
  quote: string;
  confidence: number;
}

export interface PersonaAttribute {
  category: "Goals" | "Pain Points" | "Needs" | "Motivations" | "Behaviors" | "Constraints";
  title: string;
  description: string;
  provenance_class: ProvenanceClass;
  evidence: Evidence | null;
}

export interface PersonaDemographics {
  age: number;
  gender: string;
  occupation: string;
  income_bracket: string;
  location: string;
  education: string;
}

export interface PersonaBadge {
  label: string;
  value: string;
}

export * from './persona';

export interface Persona {
  id: string;
  business_id: string;
  name: string;
  status: "active" | "draft" | "archived";
  version: number;
  data_source?: "live" | "cached";
  archetype: string;
  tagline: string;
  quote?: string;
  personality?: BigFivePersonality;
  detailed_attributes?: DetailedAttributes;
  demographics: PersonaDemographics;
  attributes: PersonaAttribute[];
  consistency_score: number;
  grounding_ratio: number;
  critic_notes: string;
  generation_model: string;
  created_at: string;
  initials?: string;
  country_code?: string;
  country_name?: string;
  origin_country?: string;
  role_id?: string;
  role_title?: string;
  description?: string;
  badges?: PersonaBadge[];
}

export interface MemoryItem {
  id: string;
  persona_id: string;
  kind: MemoryKind;
  text: string;
  /** Null when the backend did not report it — never a fabricated constant. */
  importance: number | null;
  recency_weight: number | null;
  relevance_score: number | null;
  /** Who authored the text: only `persona` items are recollections; `interviewer`
   * rows are researcher questions kept as context (listed only on request). */
  source?: 'persona' | 'interviewer' | 'system';
  conversation_id?: string | null;
  created_at: string;
}

/** A memory the interview engine recalled for one turn. The backend emits plain
 * strings today; richer entries stay renderable without a contract change. */
export type RetrievedMemory = string | { text: string; kind?: string; score?: number | null };

export interface ConversationTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  latency_ms?: number;
  served_by?: string;
  retrieved_memories?: string[];
}

export interface Conversation {
  id: string;
  persona_id: string;
  objective: string;
  status: "active" | "completed";
  turns: ConversationTurn[];
  created_at: string;
}

export interface PoolPerformance {
  pool: string;
  requests: number;
  success_rate: number;
  avg_latency_ms: number | null;
  fallback_rate: number;
  local_serve_rate: number;
}

export interface QualityGateArm {
  tag: string | null;
  model: string | null;
  weighted_score: number | null;
  avg_latency_ms: number | null;
  dims: Record<string, number> | null;
}

export interface QualityGate {
  generated_at: string | null;
  bar: number | null;
  rubric_weights: Record<string, number> | null;
  arms: QualityGateArm[];
  judge_route: string | null;
  judge_notes: string | null;
  source_file: string;
}

export interface EvaluationMetrics {
  overall_health: {
    total_personas_generated: number;
    schema_validity_rate: number | null;
    consistency_pass_rate: number | null;
    avg_grounding_ratio: number | null;
    avg_latency_ms: number | null;
  };
  pools: PoolPerformance[];
  quality_gate: QualityGate | null;
}

// ---------------------------------------------------------------------------
// Judge Lab (demo-lab) — scripted adapters exercising the REAL routing code.
// ---------------------------------------------------------------------------

export type DemoLabScenarioName =
  | "provider_429_fallback"
  | "provider_5xx_fallback"
  | "all_providers_down"
  | "context_overflow"
  | "prompt_injection"
  | "evidence_conflict"
  | "insufficient_evidence";

export interface DemoLabScenario {
  name: DemoLabScenarioName | string;
  title: string;
  description: string;
  expected_outcome: string;
}

export interface DemoLabScenariosResponse {
  enabled: boolean;
  simulated: boolean;
  scenarios: DemoLabScenario[];
}

export type DemoLabOutcome =
  | "served"
  | "served_after_fallback"
  | "explicit_failure"
  | "claims_downgraded"
  | "low_grounding";

export interface DemoLabTimelineStep {
  step: string;
  provider: string | null;
  model: string | null;
  result: "failed" | "served" | "skipped";
  failure_kind: FailureKind | string | null;
  fallback_reason: string | null;
  latency_ms: number | null;
}

export interface DemoLabRunResult {
  scenario: string;
  title: string;
  simulated: boolean;
  outcome: DemoLabOutcome;
  error_code: null | "all_candidates_failed" | "context_window_exceeded" | string;
  explanation: string;
  provenance: ProvenanceRecord | null;
  timeline: DemoLabTimelineStep[];
  extra: Record<string, unknown>;
}

export * from './study';
export * from './evidence';
export * from './segmentation';
export * from './interview';
export * from './behavioral';
export * from './payment';


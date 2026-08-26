// Core TypeScript types matching docs/API_CONTRACT.md

import type { BigFivePersonality, DetailedAttributes } from './persona';

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
  | "EMERGENCY_FALLBACK";

export type FailureKind =
  | "RATE_LIMIT"
  | "QUOTA_EXHAUSTED"
  | "TIMEOUT"
  | "CONNECTION"
  | "SERVER_ERROR"
  | "MODEL_UNAVAILABLE"
  | "CAPABILITY_UNSUPPORTED"
  | "CONTEXT_OVERFLOW"
  | "MALFORMED_RESPONSE"
  | "INTERNAL_ERROR";

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
  active_cooldowns: number;
}

export interface PoolStatus {
  name: string;
  max_concurrency: number;
  active_requests: number;
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
  importance: number;
  recency_weight: number;
  relevance_score: number;
  created_at: string;
}

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

export * from './study';
export * from './evidence';
export * from './segmentation';
export * from './persona';
export * from './interview';
export * from './behavioral';


export type InterviewLengthTier = "short" | "standard" | "deep";
export type InterviewStatus = "active" | "completed" | "failed" | "paused";

export type InterviewInsightType =
  | "pain_point"
  | "pricing"
  | "feature_validation"
  | "objection"
  | "behavior"
  | "quote";

export interface InterviewTurn {
  id: string;
  turn_number: number;
  role: "interviewer" | "persona" | "system" | "researcher" | "user" | "assistant";
  content: string;
  topic?: string;
  latency_ms?: number;
  served_by?: string;
  retrieved_memories?: string[];
  created_at: string;
}

export interface InterviewInsight {
  id: string;
  interview_id?: string;
  study_id?: string;
  persona_id?: string;
  type: InterviewInsightType;
  title: string;
  description: string;
  supporting_turn_numbers: number[];
  confidence: number;
  is_synthetic: boolean;
  metadata_payload?: Record<string, any>;
  created_at: string;
}

export interface Interview {
  id: string;
  study_id: string;
  user_id?: string;
  persona_id: string;
  persona_version: number;
  generation_run_id?: string;
  objective: string;
  custom_objective?: string;
  interview_type: string;
  length_tier: InterviewLengthTier;
  max_turns: number;
  status: InterviewStatus;
  topics_explored: Record<string, string>;
  question_count: number;
  turn_count: number;
  summary?: string;
  key_findings?: string[];
  structured_insights?: InterviewInsight[];
  configuration?: Record<string, any>;
  persona_name?: string;
  persona_avatar?: string;
  persona_occupation?: string;
  created_at: string;
  updated_at?: string;
}

export interface InterviewDetailResponse {
  interview: Interview;
  turns: InterviewTurn[];
  insights: InterviewInsight[];
  suggested_questions: string[];
  topics: {
    id: string;
    label: string;
    status: "explored" | "not_explored";
  }[];
}

export interface InterviewListResponse {
  interviews: Interview[];
  total: number;
}

export interface InterviewMetrics {
  total_interviews: number;
  active_interviews: number;
  completed_interviews: number;
  total_insights_generated: number;
}

export interface StartInterviewPayload {
  objective: string;
  custom_objective?: string;
  length_tier?: InterviewLengthTier;
  generation_run_id?: string;
}

export interface SendInterviewMessagePayload {
  content: string;
}

export interface SendInterviewMessageResponse {
  reply: string;
  turn_number: number;
  total_turns: number;
  max_turns: number;
  is_finished: boolean;
  topic: string;
  topics_explored: Record<string, string>;
  suggested_questions: string[];
  served_by?: string;
  latency_ms: number;
}

export interface CompleteInterviewResponse {
  id: string;
  status: "completed";
  summary: string;
  key_findings: string[];
  structured_insights: InterviewInsight[];
}

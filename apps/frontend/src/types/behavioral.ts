/**
 * TypeScript definitions for Part 7: Behavioral Testing & Simulation
 */

export type BehavioralTestType =
  | 'purchase_decision'
  | 'pricing_test'
  | 'feature_test'
  | 'concept_test'
  | 'message_test'
  | 'offer_test'
  | 'switching_test'
  | 'objection_test';

export interface DecisionFactor {
  name: string;
  impact: 'high' | 'medium' | 'low';
  direction: 'positive' | 'negative' | 'neutral';
  description: string;
}

export interface SimulationContextSources {
  persona_profile?: boolean;
  segment_characteristics?: boolean;
  interview_insights?: boolean;
  research_evidence?: boolean;
  dataset_characteristics?: boolean;
}

export interface BehavioralTestResult {
  id: string;
  persona_id: string;
  persona_name: string;
  persona_version: number;
  segment_id?: string | null;
  segment_name?: string | null;
  decision: string;
  decision_label: string;
  probability: number;
  confidence: 'low' | 'medium' | 'high';
  confidence_score: number;
  key_factors: DecisionFactor[];
  motivators: string[];
  objections: string[];
  reasoning_summary: string;
  simulation_context_sources: SimulationContextSources;
  interview_signals_used: string[];
  status: 'completed' | 'failed';
  error_message?: string | null;
  created_at?: string | null;
}

export interface BehavioralInsight {
  id: string;
  type:
    | 'demand_signal'
    | 'adoption_barrier'
    | 'price_sensitivity'
    | 'feature_appeal'
    | 'messaging_signal'
    | 'switching_trigger'
    | 'objection'
    | 'segment_difference'
    | 'risk'
    | 'opportunity';
  title: string;
  description: string;
  supporting_persona_ids: string[];
  confidence: number;
  is_synthetic: boolean;
  created_at?: string | null;
}

export interface SegmentAnalysisItem {
  segment_id: string;
  segment_name: string;
  persona_count: number;
  positive_percentage: number;
  negative_percentage: number;
  average_likelihood: number;
  top_objection: string;
}

export interface CrossPersonaPatterns {
  top_motivators: string[];
  top_objections: string[];
  top_decision_factors: Array<{ name: string; frequency: number }>;
}

export interface BehavioralRiskItem {
  type: 'risk';
  title: string;
  description: string;
  severity: 'high' | 'medium' | 'low';
}

export interface BehavioralOpportunityItem {
  type: 'opportunity';
  title: string;
  description: string;
  appeal: 'high' | 'medium' | 'low';
}

export interface AggregateSimulationMetrics {
  total_personas: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  positive_percentage: number;
  neutral_percentage: number;
  negative_percentage: number;
  average_likelihood: number;
  average_likelihood_percentage: number;
  confidence_breakdown: {
    low?: number;
    medium?: number;
    high?: number;
  };
}

export interface BehavioralTestScenario {
  id: string;
  title: string;
  scenario_text: string;
  structured_parameters: Record<string, any>;
  created_at?: string | null;
}

export interface BehavioralTestRun {
  id: string;
  behavioral_test_id: string;
  study_id: string;
  scenario_id?: string | null;
  scenario_snapshot: {
    title?: string;
    scenario_text?: string;
    structured_parameters?: Record<string, any>;
  };
  target_population_type: 'all' | 'segment' | 'selected_personas';
  target_segment_id?: string | null;
  target_persona_ids: string[];
  status: 'pending' | 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled';
  persona_count: number;
  completed_count: number;
  failed_count: number;
  aggregate_metrics: AggregateSimulationMetrics;
  segment_analysis: SegmentAnalysisItem[];
  cross_persona_patterns: CrossPersonaPatterns;
  risks: BehavioralRiskItem[];
  opportunities: BehavioralOpportunityItem[];
  summary?: string | null;
  error_message?: string | null;
  results?: BehavioralTestResult[];
  insights?: BehavioralInsight[];
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
}

export interface BehavioralTest {
  id: string;
  study_id: string;
  name: string;
  description?: string | null;
  test_type: BehavioralTestType;
  configuration: Record<string, any>;
  status: 'draft' | 'ready' | 'running' | 'completed' | 'archived';
  scenarios: BehavioralTestScenario[];
  run_count: number;
  latest_run?: {
    id: string;
    status: string;
    persona_count: number;
    completed_count: number;
    average_likelihood: number;
    created_at?: string | null;
  } | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface BehavioralMetricsResponse {
  study_id: string;
  total_tests: number;
  total_runs: number;
  completed_runs: number;
  total_personas_simulated: number;
  average_buy_likelihood: number;
  average_buy_likelihood_percentage: number;
}

export interface CreateBehavioralTestPayload {
  name: string;
  description?: string;
  test_type: BehavioralTestType;
  configuration?: Record<string, any>;
  scenario_title?: string;
  scenario_text?: string;
}

export interface RunBehavioralTestPayload {
  scenario_id?: string;
  scenario_title?: string;
  scenario_text?: string;
  parameters?: Record<string, any>;
  target_population_type: 'all' | 'segment' | 'selected_personas';
  target_segment_id?: string;
  target_persona_ids?: string[];
}

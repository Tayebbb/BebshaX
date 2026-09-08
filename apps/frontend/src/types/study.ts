export type StudyType =
  | 'interviews'
  | 'landing_page_test'
  | 'message_testing'
  | 'ab_test';

export type StudyStatus = 'draft' | 'in_progress' | 'completed';

export type ResearchGoal =
  | 'demand_validation'
  | 'messaging_positioning'
  | 'feature_concept_exploration'
  | 'discover_personas';

export interface QuoteHighlight {
  quote: string;
  persona_name: string;
  persona_archetype: string;
  tag: string;
  sentiment: 'positive' | 'neutral' | 'negative';
}

export interface EvidenceFinding {
  title: string;
  claim: string;
  confidence: number;
  source: string;
}

export interface DatasetFinding {
  name: string;
  insight: string;
  variables: string[];
}

export interface MarketSegmentSummary {
  name: string;
  percentage: number;
  description: string;
}

export interface PersonaOverviewItem {
  name: string;
  archetype: string;
  segment: string;
  key_takeaway: string;
  grounding_score?: number;
}

export interface InterviewFinding {
  topic: string;
  finding: string;
  supporting_personas: string[];
  turn_citations: string[];
}

export interface PainPointItem {
  pain_point: string;
  severity: string;
  frequency: string;
}

export interface CustomerNeedItem {
  need: string;
  priority: string;
  context: string;
}

export interface BehavioralResultItem {
  test_type: string;
  scenario: string;
  decision: string;
  average_likelihood: number;
  key_objection: string;
  key_motivator: string;
}

export interface PricingSignalItem {
  price_point: string;
  sentiment: string;
  acceptable_range: string;
}

export interface StudyReport {
  id?: string;
  study_id?: string;
  user_id?: string;
  version?: number;
  title?: string;
  executive_summary: string;
  key_findings: string[];
  target_market_summary?: string;
  market_context_summary?: string;
  evidence_findings?: EvidenceFinding[];
  dataset_findings?: DatasetFinding[];
  market_segments_summary?: MarketSegmentSummary[];
  persona_overview?: PersonaOverviewItem[];
  interview_findings?: InterviewFinding[];
  major_pain_points?: PainPointItem[];
  customer_needs?: CustomerNeedItem[];
  behavioral_results?: BehavioralResultItem[];
  pricing_signals?: PricingSignalItem[];
  major_risks?: string[];
  opportunities?: string[];
  strongest_segments?: string[];
  recommendations: string[];
  validation_summary?: string;
  limitations?: string;
  metrics?: {
    total_interviews?: number;
    total_personas?: number;
    total_claims?: number;
    confidence_score?: number;
    demand_score?: number;
    /** Always "llm" — a report is model-written or does not exist. */
    synthesis_source?: string;
    /** `provider/model` that synthesised this report version. */
    served_by?: string | null;
    llm_request_id?: string | null;
    attempts?: number;
    [key: string]: any;
  };
  sentiment_score?: number;
  demand_signal?: 'High' | 'Moderate' | 'Low';
  quote_highlights?: QuoteHighlight[];
  completed_personas_count?: number;
  avg_interview_turns?: number;
  is_synthetic?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface StudyInterview {
  id: string;
  persona_id: string;
  persona_name: string;
  persona_archetype: string;
  status: 'completed' | 'in_progress' | 'pending';
  objective?: string;
  turns_count: number;
  duration_minutes: number;
  key_takeaway: string;
  sentiment: 'positive' | 'neutral' | 'critical';
}

export interface Study {
  id: string;
  user_id?: string;
  title: string;
  type: StudyType;
  goal?: ResearchGoal;
  prompt?: string;
  status: StudyStatus;
  persona_count: number;
  persona_ids: string[];
  created_at: string;
  updated_at: string;
  completed_at?: string;
  duration_text?: string;
  is_demo?: boolean;
  step?: number; // 1: Context, 2: Personas, 3: Script, 4: Interviews, 5: Report
  interviews?: StudyInterview[];
  report?: StudyReport;
  copilot_messages?: Array<{
    id?: string;
    role: 'user' | 'assistant';
    content?: string;
    text?: string;
    timestamp?: string;
    isGoalCard?: boolean;
    goalCardData?: any;
    options?: string[];
  }>;
  suggested_roles?: PersonaRoleSuggestion[];
  script_questions?: string[];
  personas_data?: any[];
}

export interface PersonaRoleSuggestion {
  id: string;
  role: string;
  description: string;
  count: number;
  selected: boolean;
}

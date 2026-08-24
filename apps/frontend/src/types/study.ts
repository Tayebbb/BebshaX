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

export interface StudyReport {
  executive_summary: string;
  key_findings: string[];
  sentiment_score: number; // e.g. 84 (%)
  demand_signal: 'High' | 'Moderate' | 'Low';
  quote_highlights: QuoteHighlight[];
  recommendations: string[];
  completed_personas_count: number;
  avg_interview_turns: number;
}

export interface StudyInterview {
  id: string;
  persona_id: string;
  persona_name: string;
  persona_archetype: string;
  status: 'completed' | 'in_progress' | 'pending';
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

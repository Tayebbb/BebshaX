// Synthetic Persona types matching BebshaX API Contract

export type PersonaStatus = 'ready' | 'needs_review' | 'generating' | 'draft' | 'active' | 'archived';

export interface BigFivePersonality {
  openness: number;
  conscientiousness: number;
  extroversion: number;
  agreeableness: number;
  neuroticism: number;
}

export interface DetailedAttributes {
  hobbies?: string;
  origin_country?: string;
  commute_mode?: string;
  food_source?: string;
  meal_timing?: string;
  payment_method?: string;
  work_schedule?: string;
  workplace_setting?: string;
  activity_level?: string;
  adaptability_level?: string;
  anxiety_level?: string;
  attention_focus?: string;
  belief_system?: string;
  communication_style?: string;
  community_engagement?: string;
  coping_strategies?: string;
  core_motivators?: string;
  cultural_affiliations?: string;
  cultural_traditions?: string;
  daily_activities?: string;
  decision_style?: string;
  family_dynamics?: string;
  financial_attitude?: string;
  financial_profile?: string;
  general_risk?: string;
  growth_mindset?: string;
  household_structure?: string;
  introversion_level?: string;
  language_preferences?: string;
  learning_style?: string;
  life_priorities?: string;
  motivation_goals?: string;
  personal_independence?: string;
  personal_values?: string;
  planning_horizon?: string;
  religious_practices?: string;
  schedule_flexibility?: string;
  self_discipline?: string;
  sleep_schedule?: string;
  social_identity?: string;
  social_values?: string;
  spiritual_outlook?: string;
  tech_interest?: string;
  technology_usage?: string;
  time_management?: string;
  urban_living?: string;
  value_risk?: string;
  work_ethic?: string;
  [key: string]: any;
}

export interface PersonaDemographicsProfile {
  age?: number;
  gender?: string;
  occupation?: string;
  location?: string;
  education?: string;
  income_or_budget?: string;
}

export interface PersonaCommercialProfile {
  monthly_budget_bdt?: number;
  budget_bdt?: number;
  budget_range?: string;
  price_sensitivity?: 'High' | 'Moderate' | 'Low' | string;
  payment_preference?: string;
  willingness_to_pay?: string;
}

export interface PersonaTechnologyProfile {
  primary_devices?: string[];
  platforms?: string[];
  familiarity?: 'High' | 'Medium' | 'Low' | string;
}

export interface PersonaEvidenceCitation {
  claim_id?: string;
  claim_text: string;
  category?: string;
  confidence?: number;
}

export interface PersonaDatasetRef {
  dataset_id?: string;
  content_hash?: string;
  variable: string;
  value: any;
  source?: string;
}

export interface SyntheticPersona {
  id: string;
  study_id?: string;
  user_id?: string;
  segment_id?: string;
  segment_name?: string;
  generation_run_id?: string;
  name: string;
  avatar_url?: string;
  status: PersonaStatus;
  version: number;
  data_source?: 'live' | 'cached';
  generation_model?: string;
  archetype?: string;
  tagline?: string;
  country_code?: string;
  origin_country?: string;
  personality?: BigFivePersonality;
  detailed_attributes?: DetailedAttributes;
  demographics: PersonaDemographicsProfile;
  bio?: string;
  quote?: string;
  goals: string[];
  needs: string[];
  pain_points: string[];
  behaviors: string[];
  preferences: string[];
  motivations: string[];
  objections: string[];
  commercial_profile: PersonaCommercialProfile;
  technology_profile: PersonaTechnologyProfile;
  evidence_citations: PersonaEvidenceCitation[];
  dataset_refs: PersonaDatasetRef[];
  grounding_score: number;
  confidence: number;
  validation_warnings: string[];
  is_synthetic: boolean;
  created_at: string;
  updated_at?: string;
}

export interface PersonaGenerationRun {
  id: string;
  study_id: string;
  user_id?: string;
  segmentation_run_id?: string;
  status:
    | 'pending'
    | 'loading_segments'
    | 'preparing_context'
    | 'generating_personas'
    | 'validating_personas'
    | 'saving_personas'
    | 'completed'
    | 'failed';
  configuration: {
    personas_per_segment?: number;
    target_count?: number;
    distribution_strategy?: 'population_weighted' | 'equal';
  };
  target_count: number;
  generated_count: number;
  valid_count: number;
  warning_count: number;
  dataset_versions: Array<{ dataset_id: string; name?: string; content_hash?: string; row_count?: number; is_sample?: boolean }>;
  evidence_snapshot: { claim_count?: number; top_claims?: Array<{ id: string; claim_text: string }> };
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
}

export interface StudyPersonasResponse {
  personas: SyntheticPersona[];
  total: number;
  represented_segments: number;
  average_grounding_score: number;
}

export interface GeneratePersonasPayload {
  segmentation_run_id?: string;
  personas_per_segment?: number;
  target_count?: number;
  distribution_strategy?: 'population_weighted' | 'equal';
}

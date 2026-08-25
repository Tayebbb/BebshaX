// Synthetic Persona types matching BebshaX API Contract

export type PersonaStatus = 'ready' | 'needs_review' | 'generating' | 'draft' | 'active' | 'archived';

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
  status: PersonaStatus;
  version: number;
  generation_model?: string;
  archetype?: string;
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
  dataset_versions: Array<{ dataset_id: string; name?: string; content_hash?: string; row_count?: number }>;
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

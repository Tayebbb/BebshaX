export interface UsableVariableSummary {
  name: string;
  type: string;
  source_dataset_name: string;
  source_dataset_id: string;
  coverage_percentage: number;
  missing_percentage: number;
  usefulness: 'high' | 'medium' | 'low';
}

export interface SegmentationReadiness {
  status: 'ready' | 'limited_data' | 'no_data';
  can_run: boolean;
  dataset_count: number;
  total_records: number;
  usable_variables_count: number;
  usable_variables: UsableVariableSummary[];
  evidence_claim_count: number;
  supported_claims_count: number;
  guidance_message: string;
  study_id: string;
}

export interface EvidenceCitation {
  claim_id: string;
  claim_text: string;
  category: string;
  status: string;
  confidence: number;
  rationale?: string;
}

export interface MarketSegment {
  id: string;
  study_id: string;
  user_id?: string;
  segmentation_run_id: string;
  name: string;
  cluster_label: string;
  description: string;
  population_count: number;
  population_percentage: number;
  confidence_score: number;
  status?: 'data_backed' | 'inference_assisted' | 'insufficient_evidence' | string;
  characteristics: {
    name_hint?: string;
    demographics?: {
      age_range?: [number, number] | number[];
      median_age?: number;
      dominant_occupation?: string;
      [key: string]: any;
    };
    economics?: {
      monthly_budget?: {
        min?: number;
        median?: number;
        max?: number;
        currency?: string;
        [key: string]: any;
      };
      [key: string]: any;
    };
    behavior?: {
      study_hours_per_day?: number;
      technology_familiarity?: string;
      [key: string]: any;
    };
    needs?: string[];
    rule_description?: string;
    [key: string]: any;
  };
  variable_distributions: Record<string, any>;
  evidence_citations: EvidenceCitation[];
  differentiation_summary?: string;
  created_at: string;
  updated_at?: string;
}

export interface DatasetVersionItem {
  dataset_id: string;
  name: string;
  content_hash: string;
  row_count: number;
  file_type: string;
}

export interface SegmentationRun {
  id: string;
  study_id: string;
  user_id?: string;
  status:
    | 'pending'
    | 'analyzing_data'
    | 'selecting_variables'
    | 'clustering'
    | 'evaluating_groups'
    | 'interpreting_segments'
    | 'completed'
    | 'failed';
  method: string;
  configuration: Record<string, any>;
  dataset_versions: DatasetVersionItem[];
  evidence_snapshot: Record<string, any>;
  segment_count: number;
  error_message?: string;
  started_at: string;
  completed_at?: string;
  created_at: string;
}

export interface ComparedSegmentMatrixItem {
  segment_id: string;
  name: string;
  cluster_label: string;
  population_count: number;
  population_percentage: number;
  confidence_score: number;
  status: string;
  median_budget: string;
  budget_range: string;
  age_range: string;
  tech_familiarity: string;
  evidence_citations_count: number;
  differentiation: string;
}

export interface SegmentComparisonResult {
  study_id: string;
  compared_count: number;
  comparison_matrix: ComparedSegmentMatrixItem[];
}

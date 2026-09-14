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
  /** `ready` only with >=20 observed records and a usable variable; otherwise
   * segmentation cannot run — the platform never invents segments. */
  status: 'ready' | 'insufficient_records' | 'no_data' | string;
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
  relevance?: number;
  rationale?: string;
}

/** Numeric summary or categorical frequencies computed from the cluster's rows. */
export interface ObservedDistribution {
  count?: number;
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  p25?: number;
  p75?: number;
  std?: number;
  unique_categories?: number;
  top_categories?: Array<{ category: string; count: number; percentage: number }>;
  percentages?: Record<string, number>;
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
  /** Observed-only characteristics. `partition_method` is `quantile_bands`
   * (numeric bands over the real rows) or `categorical_grouping` (a grouping
   * column in the dataset). `observed` holds per-variable distributions
   * computed inside this cluster; nothing here is assumed. */
  characteristics: {
    name_hint?: string;
    partition_method?: 'quantile_bands' | 'categorical_grouping' | string;
    partition_variable?: string;
    band?: { lower: number; upper: number };
    observed?: Record<string, ObservedDistribution>;
    observed_constraints?: Record<string, any>;
    rule_description?: string;
    interpretation_source?: string;
    served_by?: string;
    [key: string]: any;
  };
  variable_distributions: Record<string, ObservedDistribution | any>;
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
  /** True when the dataset came from the illustrative sample catalog. */
  is_sample?: boolean;
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
  /** Datasets the run clustered that no longer exist (server-computed). */
  missing_datasets?: { dataset_id?: string; name?: string }[];
  /** The study, datasets or claims changed since this run (server-computed). */
  inputs_changed?: boolean;
}

export interface ComparedSegmentMatrixItem {
  segment_id: string;
  name: string;
  cluster_label: string;
  population_count: number;
  population_percentage: number;
  confidence_score: number;
  status: string;
  /** The numeric variable the clusters were partitioned on (null for categorical groups). */
  partition_variable: string | null;
  /** `min–max` of the partition variable inside this segment, when measured. */
  headline_range: string | null;
  headline_median: number | null;
  /** Dominant category per observed categorical variable. */
  top_categories: Record<string, string>;
  observed_variables: string[];
  evidence_citations_count: number;
  differentiation: string;
}

export interface SegmentComparisonResult {
  study_id: string;
  compared_count: number;
  comparison_matrix: ComparedSegmentMatrixItem[];
}

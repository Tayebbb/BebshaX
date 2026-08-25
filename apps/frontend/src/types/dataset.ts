export interface DatasetColumnSchema {
  name: string;
  type: 'numeric' | 'categorical' | 'boolean' | 'text';
  missing_count: number;
  missing_percentage: number;
  unique_count: number;
  sample_values: any[];
}

export interface NumericColumnStats {
  count: number;
  min: number;
  max: number;
  mean: number;
  median: number;
  std: number;
  p25: number;
  p75: number;
  iqr: number;
}

export interface CategoricalColumnStats {
  count: number;
  unique_categories: number;
  top_categories: Array<{ category: string; count: number; percentage: number }>;
  percentages: Record<string, number>;
}

export interface DatasetSegment {
  id: string;
  name: string;
  population_count: number;
  population_share: number;
  population_percentage: number;
  is_dataset_supported: boolean;
  segmentation_feature: string;
  constraints: {
    age_range?: [number, number];
    median_age?: number;
    monthly_budget?: { min?: number; median?: number; max?: number; p75?: number; currency?: string };
    technology_familiarity?: string;
    observed_needs?: string[];
    rule_description?: string;
  };
  sample_records?: any[];
}

export interface DatasetSource {
  id: string;
  user_id?: string | null;
  study_id?: string | null;
  name: string;
  source_type: 'url' | 'upload';
  source_url?: string | null;
  original_file_name?: string | null;
  file_type: string;
  description?: string | null;
  status: 'idle' | 'fetching' | 'parsing' | 'profiling' | 'analyzing' | 'ready' | 'error';
  row_count: number;
  column_count: number;
  schema_metadata: {
    columns: DatasetColumnSchema[];
    row_count: number;
    column_count: number;
  };
  statistics: {
    numeric: Record<string, NumericColumnStats>;
    categorical: Record<string, CategoricalColumnStats>;
    overview: Record<string, any>;
  };
  segments: DatasetSegment[];
  persona_count_generated: number;
  processing_error?: string | null;
  created_at: string;
  updated_at: string;
  last_processed_at?: string | null;
}

export interface PersonaGenerationRun {
  run_id: string;
  dataset_id: string;
  dataset_name: string;
  model_used: string;
  requested_count: number;
  generated_count: number;
  valid_count: number;
  warning_count: number;
  contradiction_count: number;
  distribution: Record<string, number>;
  personas: any[];
  validation_summary: Array<{
    persona_name: string;
    segment: string;
    status: 'VALID' | 'WARNING' | 'CONTRADICTION' | 'INVALID';
    violations: string[];
    warnings: string[];
  }>;
}

export interface OpenRouterHealth {
  configured: boolean;
  authenticated: boolean;
  model: string;
  status: string;
  latency_ms?: number;
  error_code?: string;
  message: string;
  verified_response?: string;
}

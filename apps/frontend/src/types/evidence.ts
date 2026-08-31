export type EvidenceStatus = 'supported' | 'inference' | 'unsupported';

export type EvidenceCategory =
  | 'problem'
  | 'competition'
  | 'pricing'
  | 'behavior'
  | 'complaints'
  | 'general';

export type ResearchStatus =
  | 'idle'
  | 'pending'
  | 'planning'
  | 'discovering_datasets'
  | 'generating_queries'
  | 'collecting_sources'
  | 'processing_chunks'
  | 'extracting_evidence'
  | 'completed'
  | 'failed';

export interface ResearchRun {
  id: string;
  study_id: string;
  user_id?: string | null;
  status: ResearchStatus;
  current_step?: string | null;
  query_count: number;
  source_count: number;
  claim_count: number;
  dataset_candidate_count?: number;
  dataset_imported_count?: number;
  step_progress?: Record<string, string | number | boolean>;
  research_plan?: Record<string, any> | null;
  queries: string[];
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
}

// ── Autonomous Research Plan ──────────────────────────────────────────────────

export interface ResearchArea {
  area: string;
  focus: string;
  data_types: string[];
  priority: 'high' | 'medium' | 'low';
}

export interface ResearchPlan {
  study_id: string;
  idea_summary: string;
  domain: string;
  target_region: string;
  research_areas: ResearchArea[];
  dataset_search_terms: string[];
  evidence_query_topics: string[];
  created_at?: string;
}

// ── Discovered Dataset Candidate ─────────────────────────────────────────────

export type CandidateStatus =
  | 'discovered'
  | 'auto_imported'
  | 'imported_by_user'
  | 'rejected_by_user'
  | 'import_failed';

export interface DatasetCandidate {
  id: string;
  study_id: string;
  run_id?: string | null;
  name: string;
  description?: string | null;
  source_url?: string | null;
  source_name?: string | null;
  file_type?: string | null;
  estimated_rows?: number | null;
  quality_score: number;
  relevance_score: number;
  diversity_tag?: string | null;
  status: CandidateStatus;
  /** True when the candidate came from the illustrative sample catalog. */
  is_sample?: boolean;
  imported_dataset_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface EvidenceSource {
  id: string;
  study_id: string;
  user_id?: string | null;
  run_id?: string | null;
  source_type: 'web' | 'reddit' | 'review' | 'report' | 'upload';
  title: string;
  url?: string | null;
  publisher: string;
  content: string;
  content_hash?: string;
  relevance_score: number;
  status: string;
  claims_count?: number;
  metadata_payload?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface EvidenceChunk {
  id: string;
  source_id: string;
  study_id: string;
  chunk_index: number;
  content: string;
  embedding_space?: string;
  metadata_payload?: Record<string, any>;
  created_at?: string;
}

export interface EvidenceClaim {
  id: string;
  study_id: string;
  user_id?: string | null;
  run_id?: string | null;
  claim_text: string;
  status: EvidenceStatus;
  category: EvidenceCategory;
  confidence: number;
  supporting_source_ids: string[];
  supporting_chunk_ids: string[];
  contradicting_source_ids: string[];
  rationale?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface EvidenceSummary {
  study_id: string;
  research_status: ResearchStatus;
  evidence_coverage: number;
  supported_pct: number;
  inferred_pct: number;
  unsupported_pct: number;
  supported_count: number;
  inferred_count: number;
  unsupported_count: number;
  total_claims: number;
  total_sources: number;
  latest_run?: {
    id: string;
    status: ResearchStatus;
    query_count: number;
    source_count: number;
    claim_count: number;
    started_at?: string | null;
    completed_at?: string | null;
    error_message?: string | null;
  } | null;
}

export interface SupportingChunkDetail {
  id: string;
  source_id: string;
  chunk_index: number;
  content: string;
}

export interface ClaimDetail extends EvidenceClaim {
  supporting_sources: EvidenceSource[];
  supporting_chunks: SupportingChunkDetail[];
  contradicting_sources: EvidenceSource[];
}

export interface SourceDetail extends EvidenceSource {
  chunks: {
    id: string;
    chunk_index: number;
    content: string;
    created_at: string;
  }[];
}

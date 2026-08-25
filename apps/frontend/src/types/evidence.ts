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
  query_count: number;
  source_count: number;
  claim_count: number;
  queries: string[];
  error_message?: string | null;
  started_at: string;
  completed_at?: string | null;
  created_at: string;
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

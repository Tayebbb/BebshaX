/**
 * Research & Evidence domain slice of the API client.
 *
 * Extracted from services/api.ts (which was a single ~4.2k-line object) with
 * zero behavior change: `createResearchApi` receives the shared helpers the
 * methods used to reach via `this`/module scope, and the returned object is
 * spread back into the exported `api` object so every existing call site
 * (`api.startResearch(...)` etc.) works unchanged.
 */
import {
  ClaimDetail,
  DatasetCandidate,
  EvidenceClaim,
  EvidenceSource,
  EvidenceSummary,
  ResearchPlan,
  ResearchRun,
  SourceDetail,
} from '../types';
import { mockStore } from './mockStore';

export interface ResearchApiDeps {
  /** Base URL of the backend API (module-scope `API_BASE` in api.ts). */
  apiBase: string;
  /** TIMEOUT_MS.LLM — research runs transit the LLM path. */
  llmTimeoutMs: number;
  /** Mock gate — delegates to api.isMockMode() so setMockMode() stays authoritative. */
  isMockMode: () => boolean;
  /** Auth-header builder — delegates to api.getAuthHeaders(). */
  getAuthHeaders: (customHeaders?: Record<string, string>) => Record<string, string>;
  /** Setter for api.ts's module-scope `lastKnownLive` liveness flag. */
  setLastKnownLive: (live: boolean) => void;
}

export function createResearchApi(deps: ResearchApiDeps) {
  const { apiBase, llmTimeoutMs, isMockMode, getAuthHeaders, setLastKnownLive } = deps;

  const research = {
    async startResearch(studyId: string): Promise<ResearchRun> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/research`, {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          const err = await res.json().catch(() => ({ detail: 'Research run failed' }));
          throw new Error(err.detail || `Research run failed (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      const mockRun: ResearchRun = {
        id: `run_${Date.now()}`,
        study_id: studyId,
        status: 'completed',
        query_count: 5,
        source_count: mockStore.sources.length,
        claim_count: mockStore.claims.length,
        queries: [
          'student study planner pain points Bangladesh',
          'monthly subscription affordability Dhaka students',
          'AI study tools competitor retention complaints',
          'exam preparation coaching habits bKash payments',
        ],
        started_at: new Date(Date.now() - 4000).toISOString(),
        completed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
      mockStore.researchRuns.unshift(mockRun);
      return mockRun;
    },

    async getResearchRuns(studyId: string): Promise<ResearchRun[]> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/research`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch research runs (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }
      return mockStore.researchRuns.filter((r) => r.study_id === studyId || r.study_id === 'study_default');
    },

    async getResearchRun(studyId: string, runId: string): Promise<ResearchRun> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/research/${runId}`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch research run (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }
      const found = mockStore.researchRuns.find((r) => r.id === runId);
      if (found) return found;
      return {
        id: runId,
        study_id: studyId,
        status: 'completed',
        query_count: 5,
        source_count: 4,
        claim_count: 5,
        queries: ['student study planner pain points', 'bKash payment willingess'],
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
    },

    async getEvidenceSummary(studyId: string): Promise<EvidenceSummary> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/summary`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch evidence summary (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      const claims = mockStore.claims;
      const supported = claims.filter((c) => c.status === 'supported').length;
      const inferred = claims.filter((c) => c.status === 'inference').length;
      const unsupported = claims.filter((c) => c.status === 'unsupported').length;
      const total = claims.length || 1;

      return {
        study_id: studyId,
        research_status: 'completed',
        evidence_coverage: Math.round((supported / total) * 100),
        supported_pct: Math.round((supported / total) * 100),
        inferred_pct: Math.round((inferred / total) * 100),
        unsupported_pct: Math.round((unsupported / total) * 100),
        supported_count: supported,
        inferred_count: inferred,
        unsupported_count: unsupported,
        total_claims: claims.length,
        total_sources: mockStore.sources.length,
        latest_run: {
          id: 'run_latest',
          status: 'completed',
          query_count: 5,
          source_count: mockStore.sources.length,
          claim_count: claims.length,
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
        },
      };
    },

    async getEvidenceSources(
      studyId: string,
      params?: { source_type?: string; search?: string }
    ): Promise<EvidenceSource[]> {
      if (!isMockMode()) {
        try {
          const queryParams = new URLSearchParams();
          if (params?.source_type) queryParams.set('source_type', params.source_type);
          if (params?.search) queryParams.set('search', params.search);
          const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/sources${qs}`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch evidence sources (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      let results = [...mockStore.sources];
      if (params?.source_type && params.source_type !== 'all') {
        results = results.filter((s) => s.source_type === params.source_type);
      }
      if (params?.search) {
        const q = params.search.toLowerCase();
        results = results.filter(
          (s) => s.title.toLowerCase().includes(q) || s.content.toLowerCase().includes(q) || s.publisher.toLowerCase().includes(q)
        );
      }
      return results;
    },

    async getEvidenceSourceDetail(studyId: string, sourceId: string): Promise<SourceDetail> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/sources/${sourceId}`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch source detail (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      const source = mockStore.sources.find((s) => s.id === sourceId) || mockStore.sources[0];
      return {
        ...source,
        chunks: [
          {
            id: `chk_${source.id}_0`,
            chunk_index: 0,
            content: source.content,
            created_at: new Date().toISOString(),
          },
        ],
      };
    },

    async getEvidenceClaims(
      studyId: string,
      params?: { status?: string; category?: string; search?: string }
    ): Promise<EvidenceClaim[]> {
      if (!isMockMode()) {
        try {
          const queryParams = new URLSearchParams();
          if (params?.status) queryParams.set('status', params.status);
          if (params?.category) queryParams.set('category', params.category);
          if (params?.search) queryParams.set('search', params.search);
          const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/claims${qs}`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch evidence claims (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      let results = [...mockStore.claims];
      if (params?.status && params.status !== 'all') {
        results = results.filter((c) => c.status === params.status);
      }
      if (params?.category && params.category !== 'all') {
        results = results.filter((c) => c.category === params.category);
      }
      if (params?.search) {
        const q = params.search.toLowerCase();
        results = results.filter(
          (c) => c.claim_text.toLowerCase().includes(q) || (c.rationale && c.rationale.toLowerCase().includes(q))
        );
      }
      return results;
    },

    async getEvidenceClaimDetail(studyId: string, claimId: string): Promise<ClaimDetail> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/claims/${claimId}`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to fetch claim detail (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      const claim = mockStore.claims.find((c) => c.id === claimId) || mockStore.claims[0];
      const supporting = mockStore.sources.filter((s) => claim.supporting_source_ids.includes(s.id));
      const contradicting = mockStore.sources.filter((s) => claim.contradicting_source_ids.includes(s.id));
      const chunks = supporting.map((s, idx) => ({
        id: `chk_${s.id}_${idx}`,
        source_id: s.id,
        chunk_index: idx,
        content: s.content.slice(0, 300) + '...',
      }));

      return {
        ...claim,
        supporting_sources: supporting,
        supporting_chunks: chunks,
        contradicting_sources: contradicting,
      };
    },

    async semanticSearchEvidence(
      studyId: string,
      query: string,
      topK: number = 6
    ): Promise<{ chunk_id: string; source_id: string; content: string; similarity_score: number; metadata: any }[]> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/evidence/search`, {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ query, top_k: topK }),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Evidence search failed (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }

      return mockStore.sources.slice(0, topK).map((s, idx) => ({
        chunk_id: `chk_${s.id}_${idx}`,
        source_id: s.id,
        content: s.content,
        similarity_score: 0.88 - idx * 0.05,
        metadata: { publisher: s.publisher, title: s.title },
      }));
    },

    // ==========================================================================
    // Autonomous Research — Plan & Dataset Candidates
    // ==========================================================================

    async getResearchPlan(studyId: string): Promise<ResearchPlan | null> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/research/plan`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          if (res.status === 404) return null;
          setLastKnownLive(false);
        } catch {
          setLastKnownLive(false);
        }
      }
      return null;
    },

    async listDatasetCandidates(studyId: string): Promise<DatasetCandidate[]> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/datasets/candidates`, {
            headers: getAuthHeaders(),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
        } catch {
          setLastKnownLive(false);
        }
      }
      // No mock fabrication per product requirement — return empty list
      return [];
    },

    async getDatasetCandidates(studyId: string): Promise<DatasetCandidate[]> {
      return research.listDatasetCandidates(studyId);
    },

    async importDatasetCandidate(
      studyId: string,
      candidateId: string
    ): Promise<{ success: boolean; imported_dataset_id: string; dataset_name: string; row_count: number | null }> {
      if (!isMockMode()) {
        try {
          const res = await fetch(
            `${apiBase}/studies/${studyId}/datasets/candidates/${candidateId}/import`,
            {
              method: 'POST',
              headers: getAuthHeaders(),
            }
          );
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          const err = await res.json().catch(() => ({}));
          throw new Error((err as any).detail || 'Import failed');
        } catch (e) {
          setLastKnownLive(false);
          throw e;
        }
      }
      throw new Error('Not available in mock mode');
    },

    async rejectDatasetCandidate(
      studyId: string,
      candidateId: string
    ): Promise<{ success: boolean }> {
      if (!isMockMode()) {
        try {
          const res = await fetch(
            `${apiBase}/studies/${studyId}/datasets/candidates/${candidateId}/reject`,
            {
              method: 'POST',
              headers: getAuthHeaders(),
            }
          );
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          throw new Error(`Failed to reject candidate (HTTP ${res.status})`);
        } catch (err) {
          setLastKnownLive(false);
          throw err;
        }
      }
      return { success: true };
    },

    async triggerStudyResearch(studyId: string): Promise<any> {
      if (!isMockMode()) {
        try {
          const res = await fetch(`${apiBase}/studies/${studyId}/research/run`, {
            method: 'POST',
            headers: getAuthHeaders(),
            signal: AbortSignal.timeout(llmTimeoutMs),
          });
          if (res.ok) {
            setLastKnownLive(true);
            return await res.json();
          }
          setLastKnownLive(false);
          const err = await res.json().catch(() => ({ detail: 'Research trigger failed' }));
          throw new Error(err.detail || `Research trigger failed (HTTP ${res.status})`);
        } catch (err) {
          // A fake 'completed' status would hide that research never ran.
          setLastKnownLive(false);
          throw err;
        }
      }
      return { study_id: studyId, status: 'completed' };
    },
  };

  return research;
}

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
import { sessionFetch as fetch, sessionSignal } from './session';
import { parseApiError, toApiErrorInstance } from '../utils/apiError';

/** Lazily-loaded mock layer — mirrors api.ts. Static imports of mockStore
 * shipped the fixture tree in the production bundle; the memoized dynamic
 * import shares the same lazy chunk as api.ts's loader. */
type MockModule = typeof import('./mockStore');
let _mocks: Promise<MockModule> | null = null;
const loadMocks = (): Promise<MockModule> => (_mocks ??= import('./mockStore'));

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

  /**
   * Shared network path for every method below: fetch → `res.ok` gate →
   * `lastKnownLive` bookkeeping → parsed JSON. Behavior-identical to the
   * per-method copies it replaced: `error` supplies the per-method message
   * (a string template gaining ` (HTTP n)`, or a builder that may read the
   * body's `detail`), and `nullStatuses` lets an optional read (the 404
   * plan) resolve `null` BEFORE the liveness flag flips — a 404 there is a
   * healthy backend saying "none yet", not downtime.
   */
  const fetchJson = async <T>(
    url: string,
    init: RequestInit,
    error: string | ((res: Response) => Promise<Error>),
    opts?: { timeoutMs?: number; nullStatuses?: number[] },
  ): Promise<T> => {
    try {
      const res = await fetch(
        url,
        { ...init, signal: sessionSignal(init.signal ?? undefined, opts?.timeoutMs ?? (init.method === 'POST' ? llmTimeoutMs : 30000)) },
      );
      if (res.ok) {
        setLastKnownLive(true);
        return (await res.json()) as T;
      }
      if (opts?.nullStatuses?.includes(res.status)) {
        return null as unknown as T;
      }
      setLastKnownLive(false);
      throw typeof error === 'string'
        ? toApiErrorInstance(parseApiError(await res.json().catch(() => ({})), res.status, `${error} (HTTP ${res.status})`))
        : await error(res);
    } catch (err) {
      setLastKnownLive(false);
      throw err;
    }
  };

  const research = {
    async startResearch(studyId: string, signal?: AbortSignal): Promise<ResearchRun> {
      if (!isMockMode()) {
        return fetchJson<ResearchRun>(
          `${apiBase}/studies/${studyId}/research`,
          { method: 'POST', headers: getAuthHeaders({ 'Content-Type': 'application/json' }), signal },
          async (res) => {
            const err = await res.json().catch(() => ({ detail: 'Research run failed' }));
            return new Error(err.detail || `Research run failed (HTTP ${res.status})`);
          },
        );
      }

      const { mockStore } = await loadMocks();
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

    async getResearchRuns(studyId: string, signal?: AbortSignal): Promise<ResearchRun[]> {
      if (!isMockMode()) {
        return fetchJson<ResearchRun[]>(
          `${apiBase}/studies/${studyId}/research`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch research runs',
        );
      }
      const { mockStore } = await loadMocks();
      return mockStore.researchRuns.filter((r) => r.study_id === studyId || r.study_id === 'study_default');
    },

    async getResearchRun(studyId: string, runId: string, signal?: AbortSignal): Promise<ResearchRun> {
      if (!isMockMode()) {
        return fetchJson<ResearchRun>(
          `${apiBase}/studies/${studyId}/research/${runId}`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch research run',
        );
      }
      const { mockStore } = await loadMocks();
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

    async getEvidenceSummary(studyId: string, signal?: AbortSignal): Promise<EvidenceSummary> {
      if (!isMockMode()) {
        return fetchJson<EvidenceSummary>(
          `${apiBase}/studies/${studyId}/evidence/summary`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch evidence summary',
        );
      }

      const { mockStore } = await loadMocks();
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
      params?: { source_type?: string; search?: string },
      signal?: AbortSignal,
    ): Promise<EvidenceSource[]> {
      if (!isMockMode()) {
        const queryParams = new URLSearchParams();
        if (params?.source_type) queryParams.set('source_type', params.source_type);
        if (params?.search) queryParams.set('search', params.search);
        const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

        return fetchJson<EvidenceSource[]>(
          `${apiBase}/studies/${studyId}/evidence/sources${qs}`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch evidence sources',
        );
      }

      const { mockStore } = await loadMocks();
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
        return fetchJson<SourceDetail>(
          `${apiBase}/studies/${studyId}/evidence/sources/${sourceId}`,
          { headers: getAuthHeaders() },
          'Failed to fetch source detail',
        );
      }

      const { mockStore } = await loadMocks();
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
      params?: { status?: string; category?: string; search?: string },
      signal?: AbortSignal,
    ): Promise<EvidenceClaim[]> {
      if (!isMockMode()) {
        const queryParams = new URLSearchParams();
        if (params?.status) queryParams.set('status', params.status);
        if (params?.category) queryParams.set('category', params.category);
        if (params?.search) queryParams.set('search', params.search);
        const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

        return fetchJson<EvidenceClaim[]>(
          `${apiBase}/studies/${studyId}/evidence/claims${qs}`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch evidence claims',
        );
      }

      const { mockStore } = await loadMocks();
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

    async getEvidenceClaimDetail(studyId: string, claimId: string, signal?: AbortSignal): Promise<ClaimDetail> {
      if (!isMockMode()) {
        return fetchJson<ClaimDetail>(
          `${apiBase}/studies/${studyId}/evidence/claims/${claimId}`,
          { headers: getAuthHeaders(), signal },
          'Failed to fetch claim detail',
        );
      }

      const { mockStore } = await loadMocks();
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
        return fetchJson(
          `${apiBase}/studies/${studyId}/evidence/search`,
          {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ query, top_k: topK }),
          },
          'Evidence search failed',
        );
      }

      const { mockStore } = await loadMocks();
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
          return await fetchJson<ResearchPlan | null>(
            `${apiBase}/studies/${studyId}/research/plan`,
            { headers: getAuthHeaders() },
            'Failed to fetch research plan',
            { nullStatuses: [404] },
          );
      }
      return null;
    },

    async listDatasetCandidates(studyId: string): Promise<DatasetCandidate[]> {
      if (!isMockMode()) {
          return await fetchJson<DatasetCandidate[]>(
            `${apiBase}/studies/${studyId}/datasets/candidates`,
            { headers: getAuthHeaders() },
            'Failed to fetch dataset candidates',
          );
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
        return fetchJson(
          `${apiBase}/studies/${studyId}/datasets/candidates/${candidateId}/import`,
          { method: 'POST', headers: getAuthHeaders() },
          async (res) => {
            const err = await res.json().catch(() => ({}));
            return new Error((err as any).detail || 'Import failed');
          },
        );
      }
      throw new Error('Not available in mock mode');
    },

    async rejectDatasetCandidate(
      studyId: string,
      candidateId: string
    ): Promise<{ success: boolean }> {
      if (!isMockMode()) {
        return fetchJson(
          `${apiBase}/studies/${studyId}/datasets/candidates/${candidateId}/reject`,
          { method: 'POST', headers: getAuthHeaders() },
          'Failed to reject candidate',
        );
      }
      return { success: true };
    },

    async triggerStudyResearch(studyId: string): Promise<any> {
      if (!isMockMode()) {
        // A fake 'completed' status would hide that research never ran —
        // failures propagate to the caller.
        return fetchJson<any>(
          `${apiBase}/studies/${studyId}/research/run`,
          { method: 'POST', headers: getAuthHeaders() },
          async (res) => {
            const err = await res.json().catch(() => ({ detail: 'Research trigger failed' }));
            return new Error(err.detail || `Research trigger failed (HTTP ${res.status})`);
          },
          { timeoutMs: llmTimeoutMs },
        );
      }
      return { study_id: studyId, status: 'completed' };
    },
  };

  return research;
}

import {
  Business,
  Conversation,
  ConversationTurn,
  DemoLabRunResult,
  DemoLabScenariosResponse,
  EvaluationMetrics,
  HealthResponse,
  MemoryItem,
  Persona,
  PersonaRoleSuggestion,
  ProvenanceRecord,
  RoutesStatusResponse,
  Study,
  StudyType,
  StudyReport,
  SyntheticPersona,
  StudyPersonasResponse,
  GeneratePersonasPayload,
  PersonaGenerationRun,
  SegmentationReadiness,
  SegmentationRun,
  MarketSegment,
  SegmentComparisonResult,
} from '../types';
import {
  AuthResponse,
  GoogleAuthData,
  SignInData,
  SignUpData,
  User,
} from '../types/auth';
import {
  DatasetSource,
  DatasetPreviewResponse,
  DatasetPersonaRun,
  OpenRouterHealth,
} from '../types/dataset';
import { createResearchApi } from './researchApi';
import { parseApiError, summariseDetail, toApiErrorInstance, ApiErrorLike } from '../utils/apiError';
import type { SendInterviewMessageResponse } from '../types/interview';
import { decodeInterviewDelta, decodeInterviewDetail, decodeInterviewFrame, decodeInterviewReply, decodeInterviewSynthesis, decodeStudyReport, isRecord, MAX_INTERVIEW_FRAME_LENGTH } from './interviewProtocol';
import type { InterviewDetailResponse, CompleteInterviewResponse } from '../types/interview';
import { beginOperationTiming } from '../performance/routeTiming';
import { advanceSession, assertSession, csrfHeaders, getRefreshCredential, getSessionEpoch, hasCookieSession, purgePrivateSnapshots, resetSessionSecrets, sessionFetch as fetch, sessionSignal, setCookieSession, setRefreshCredential, setUnauthorizedRecovery } from './session';
import { adoptStudyRevision, discardStudyDraft, knownStudyRevision, pendingStudyDraft, queueStudyWrite, rememberStudyRevision, waitForStudyWrites } from './studyPersistence';
import { pollSerial } from './polling';
import { BoundedReadCache } from './readCache';

const API_BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8000/api';

function decodeUserProfile(value: unknown): User {
  if (!isRecord(value) || typeof value.id !== 'string' || !value.id ||
      typeof value.email !== 'string' || typeof value.full_name !== 'string' ||
      value.is_active !== true || value.is_verified !== true ||
      typeof value.auth_provider !== 'string' || typeof value.created_at !== 'string') {
    throw new Error('Invalid server profile');
  }
  return value as unknown as User;
}

/** One role the backend could not turn into a persona (explicit, never faked). */
export interface FailedPersonaRole {
  role_id: string;
  role: string;
  error_code: string;
  detail: string;
}

/** `POST /study/generate-personas` envelope. */
export interface GeneratePersonasResult {
  personas: Persona[];
  failed_roles: FailedPersonaRole[];
  served_by: string[];
  /** Study revision after the server saved the cohort (study-scoped runs only). */
  study_revision?: number | null;
}

/** One finding of the independent AI review. */
export interface AiReviewIssue {
  severity: 'high' | 'medium' | 'low' | string;
  artifact: string;
  detail: string;
}

/** `POST /studies/{id}/ai-review` — rubric-scored verdict written by a separate
 * CRITIC model pass; `served_by` names the route that reviewed. */
export interface AiReviewVerdict {
  study_id: string;
  persona_id?: string;
  overall_score: number;
  dimension_scores: Record<string, number>;
  strengths: string[];
  issues: AiReviewIssue[];
  verdict: string;
  scope: 'study' | 'persona' | string;
  reviewed_artifacts: Record<string, number>;
  served_by: string | null;
  llm_request_id: string | null;
  attempts: number;
  reviewed_at: string;
}

/** Timeout budgets (ms). Endpoints that transit the LLM path regularly measure
 * 30-120s+ on free-tier providers — aborting earlier silently killed real
 * replies. Pure CRUD stays snappy so failures surface fast. */
const TIMEOUT_MS = {
  /** Liveness probe — keeps the backendDown banner responsive. */
  HEALTH: 3000,
  /** DB-backed reads and writes with no LLM in the path. */
  CRUD: 15000,
  /** Heavy CRUD: whole-workflow restores or large JSON payloads on a busy backend. */
  CRUD_HEAVY: 30000,
  /** A single poll of an async job. */
  POLL: 15000,
  /** Anything that triggers LLM work: persona generation, copilot turns,
   * interview chat, report synthesis, research runs, provider test calls. */
  LLM: 300000,
} as const;

let forceMockMode: boolean | null = null;
let lastKnownLive = false;
let sessionBootstrap: { epoch: number; promise: Promise<User | null> } | null = null;
let sessionRefresh: { epoch: number; promise: Promise<AuthResponse | null> } | null = null;
/** Rotates the access credential shortly before it expires so a long session
 * never trips over the 15-minute access lifetime mid-task. */
let proactiveRefresh: ReturnType<typeof setTimeout> | null = null;
const PROACTIVE_REFRESH_LEAD_MS = 60_000;
const PROACTIVE_REFRESH_MIN_DELAY_MS = 15_000;

const jwtExpiresInSeconds = (token: string): number | null => {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload?.exp === 'number' ? payload.exp - Math.floor(Date.now() / 1000) : null;
  } catch {
    return null;
  }
};

const cancelProactiveRefresh = () => {
  if (proactiveRefresh !== null) {
    clearTimeout(proactiveRefresh);
    proactiveRefresh = null;
  }
};

/** Study-list read coalescing.
 *
 * Three independent consumers (dashboard sidebar, studies view, persona library)
 * call `getStudies()` on the same mount, and the sidebar re-runs on every tab
 * switch. Without this, one navigation costs 3 identical round trips and each
 * tab click costs another. The cache is deliberately short-lived and is dropped
 * outright by any study mutation, so freshness after create/update/delete is
 * unchanged. */
const STUDIES_CACHE_TTL_MS = 2000;
// Carries its own key so a caller can never be joined onto a request that was
// issued for a different account.
let studiesInFlight: { key: string; promise: Promise<Study[]> } | null = null;
let studiesCache: { at: number; key: string; value: Study[] } | null = null;
/** Bumped by every mutation so a read that was already in flight when the
 * mutation landed can never install its stale result into the cache. */
let studiesGeneration = 0;
const studyDetailCache = new BoundedReadCache<Study | null>();
let studyDetailEpoch = -1;

const invalidateStudiesCache = () => {
  studyDetailCache.invalidate();
  studiesGeneration += 1;
  studiesCache = null;
  // Dropping the shared promise too: a caller arriving after a delete must not
  // be handed the pre-delete read and render the study that just went away.
  studiesInFlight = null;
};

/** Fired on window after every create/update/delete of the caller's studies
 * (detail: the owner's study list as now known locally). Shells that only
 * re-read on navigation subscribe to stay in step with the views. */
export const STUDIES_CHANGED = 'bebshax:studies-changed';
/** localStorage key written on a deliberate sign-out; other tabs end their own sessions on it. */
export const SIGNOUT_BROADCAST_KEY = 'bebshax_signout_broadcast';
const notifyStudiesChanged = (studies: Study[]) => {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(STUDIES_CHANGED, { detail: { studies } }));
  } catch {
    // notification is best-effort
  }
};

/** Auth failures the caller must surface verbatim. The `code` marks the error
 * as "the server answered" so the Neon fallback (for an unreachable backend)
 * is skipped instead of masking a real 4xx/5xx. */
const authError = (message: string, code: string = 'AUTH_SERVER_ERROR'): Error & { code: string } => {
  const err = new Error(message) as Error & { code: string };
  err.code = code;
  return err;
};

/** Read a failed response's error envelope (`detail`/`error_code`/`request_id`/
 * `attempts`…) and build the Error callers receive. A 422 array `detail` is
 * summarised — never "[object Object]" — and the request id falls back to the
 * `X-Request-ID` header so every banner can quote it. */
const apiErrorFrom = async (res: Response, fallback: string): Promise<ApiErrorLike> => {
  const body = await res.json().catch(() => ({}));
  const parsed = parseApiError(body, res.status, `${fallback} (HTTP ${res.status})`);
  if (!parsed.requestId && typeof res.headers?.get === 'function') {
    parsed.requestId = res.headers.get('X-Request-ID');
  }
  return toApiErrorInstance(parsed);
};

/** Lazily-loaded mock layer (MockStore + fixtures, ~1.8k lines). A static
 * import shipped it all in the production bundle; the dynamic import keeps it
 * in a separate chunk only mock-mode paths ever request. `_mocksSync` mirrors
 * the resolved module for the two synchronous readers — every async mock
 * branch awaits loadMocks() first, so it is populated before any mock-mode
 * sync read. */
type MockModule = typeof import('./mockStore');
let _mocks: Promise<MockModule> | null = null;
let _mocksSync: MockModule | null = null;
const loadMocks = (): Promise<MockModule> =>
  (_mocks ??= import('./mockStore').then((m) => {
    _mocksSync = m;
    return m;
  }));

/** Research/evidence domain slice — lives in researchApi.ts, merged into `api`
 * below via spread. Deps are lazy closures over `api` and module state, so
 * setMockMode()/auth headers/liveness all stay authoritative here. */
const researchApi = createResearchApi({
  apiBase: API_BASE,
  llmTimeoutMs: TIMEOUT_MS.LLM,
  isMockMode: () => api.isMockMode(),
  getAuthHeaders: (customHeaders?: Record<string, string>) => api.getAuthHeaders(customHeaders),
  setLastKnownLive: (live: boolean) => {
    lastKnownLive = live;
  },
});

export const api = {
  resetMockStore() {
    // The store lives in the lazy mock chunk; the reset lands before any
    // subsequent api call touches it (continuations run in registration
    // order). Returns the promise so tests can await deterministic state.
    const reset = loadMocks().then(({ mockStore }) => {
      mockStore.reset();
    });
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.clear();
      }
    } catch {
      // ignore
    }
    return reset;
  },

  setMockMode(enabled: boolean) {
    forceMockMode = enabled;
  },

  isMockMode(): boolean {
    if (forceMockMode !== null) return forceMockMode;
    return import.meta.env?.VITE_MOCK === '1' || import.meta.env?.MODE === 'test';
  },

  isLive(): boolean {
    return lastKnownLive;
  },

  // 1. Health check (attempts live call first)
  async getHealth(): Promise<HealthResponse> {
    if (this.isMockMode()) {
      lastKnownLive = false;
      const { mockHealth } = await loadMocks();
      return mockHealth;
    }
    try {
      // Liveness is not tenant data: it must survive the sign-in/out session
      // boundary that aborts every session-scoped request during boot.
      const res = await globalThis.fetch(`${API_BASE}/health`, {
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(TIMEOUT_MS.HEALTH),
      });
      if (res.ok) {
        lastKnownLive = true;
        return await res.json();
      }
      lastKnownLive = false;
      throw new Error(`Backend health check failed (HTTP ${res.status})`);
    } catch (err) {
      lastKnownLive = false;
      throw err;
    }
  },

  // 2. Routes & Provider Status
  async getRoutesStatus(): Promise<RoutesStatusResponse> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/routes/status`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        // Any HTTP answer proves the backend is up; a 403 is a permission answer, not an outage.
        lastKnownLive = true;
        if (res.ok) return await res.json();
        throw await apiErrorFrom(res, 'Failed to fetch routes status');
      } catch (err) {
        if (err instanceof TypeError) lastKnownLive = false;
        throw err;
      }
    }
    const { mockRoutesStatus } = await loadMocks();
    return mockRoutesStatus;
  },

  // 3. Provenance Records
  async getProvenance(limit = 50): Promise<{ items: ProvenanceRecord[]; total: number }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/provenance?limit=${limit}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.items)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch provenance (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return {
      items: mockStore.provenance.slice(0, limit),
      total: mockStore.provenance.length,
    };
  },

  // 4. Businesses
  async getBusinesses(): Promise<Business[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/businesses`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch businesses (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return mockStore.businesses;
  },

  async createBusiness(data: Omit<Business, 'id' | 'persona_count' | 'created_at'>): Promise<Business> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/businesses`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          const created = await res.json();
          const { mockStore } = await loadMocks();
          mockStore.businesses.unshift(created);
          return created;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to create business');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    const newBiz: Business = {
      id: `biz_${Date.now().toString(36)}`,
      name: data.name,
      description: data.description,
      industry: data.industry,
      target_market: data.target_market,
      persona_count: 0,
      created_at: new Date().toISOString(),
    };
    const { mockStore } = await loadMocks();
    mockStore.businesses.unshift(newBiz);
    return newBiz;
  },

  // 5. Personas
  async getPersonas(): Promise<Persona[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch personas (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return Object.values(mockStore.personas);
  },

  async getPersona(id: string): Promise<Persona | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas/${id}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch persona (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return mockStore.personas[id] || null;
  },

  // 6. Memories
  async getMemories(personaId: string): Promise<MemoryItem[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas/${personaId}/memories`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            return data.map((d: any) => ({
              id: d.id,
              persona_id: d.persona_id,
              kind: d.kind,
              text: d.text,
              // The backend reports importance only; recency/relevance are
              // retrieval-time scores it does not expose here — stay null.
              importance: typeof d.importance === 'number' ? d.importance : null,
              recency_weight: null,
              relevance_score: null,
              created_at: d.created_at,
            }));
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch memories (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return mockStore.memories[personaId] || [];
  },

  // 7. Conversations
  async getConversation(id: string): Promise<Conversation | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations/${id}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          const data = await res.json();
          lastKnownLive = true;
          return {
            id: data.id,
            persona_id: data.persona_id,
            objective: data.objective,
            status: data.status,
            created_at: data.created_at || new Date().toISOString(),
            turns: (data.turns || []).map((t: any) => ({
              id: t.id || `turn_${t.turn_number}`,
              role: t.role === 'interviewer' || t.role === 'user' ? 'user' : 'assistant',
              content: t.content,
              timestamp: t.created_at || new Date().toISOString(),
            })),
          };
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch conversation (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return mockStore.conversations[id] || null;
  },

  async startConversation(personaId: string, objective: string): Promise<Conversation> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ persona_id: personaId, objective }),
          // DB-only create — the first LLM call happens on message send.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          const data = await res.json();
          lastKnownLive = true;
          const conv: Conversation = {
            id: data.id,
            persona_id: data.persona_id,
            objective: data.objective,
            status: data.status || 'active',
            turns: [],
            created_at: data.created_at || new Date().toISOString(),
          };
          const { mockStore } = await loadMocks();
          mockStore.conversations[conv.id] = conv;
          return conv;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to start conversation');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const id = `conv_${Date.now().toString(36)}`;
    const conv: Conversation = {
      id,
      persona_id: personaId,
      objective,
      status: 'active',
      turns: [],
      created_at: new Date().toISOString(),
    };
    const { mockStore } = await loadMocks();
    mockStore.conversations[id] = conv;
    return conv;
  },

  async sendMessage(
    conversationId: string,
    message: string
  ): Promise<{ userTurn: ConversationTurn; assistantTurn: ConversationTurn }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ content: message, message }),
          // Free-tier LLM turns regularly take 60-190s; shorter timeouts aborted real replies.
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          const data = await res.json();
          const userTurn: ConversationTurn = {
            id: `t_${Date.now()}`,
            role: 'user',
            content: data.user_message?.content || message,
            timestamp: data.user_message?.timestamp || new Date().toISOString(),
          };
          const assistantTurn: ConversationTurn = {
            id: `t_${Date.now() + 1}`,
            role: 'assistant',
            content: data.persona_reply?.content || data.reply || '',
            timestamp: data.persona_reply?.timestamp || new Date().toISOString(),
            // Honest pass-through: absent metadata stays absent (audit M4 hand-off) —
            // the backend's null must never become a fabricated 750/route/memory.
            latency_ms: data.persona_reply?.latency_ms ?? undefined,
            served_by: data.persona_reply?.served_by ?? data.served_by ?? undefined,
            retrieved_memories: data.persona_reply?.retrieved_memories ?? [],
          };
          const { mockStore } = await loadMocks();
          const conv = mockStore.conversations[conversationId];
          if (conv) {
            conv.turns.push(userTurn, assistantTurn);
          }
          return { userTurn, assistantTurn };
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Interview message failed');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const { mockStore } = await loadMocks();
    const conv = mockStore.conversations[conversationId];
    const persona = conv ? mockStore.personas[conv.persona_id] : null;

    const userTurn: ConversationTurn = {
      id: `turn_${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };

    const assistantTurn: ConversationTurn = {
      id: `turn_${Date.now() + 1}`,
      role: 'assistant',
      content: persona
        ? `Speaking as ${persona.name}: Given that I'm working as a ${persona.demographics.occupation}, I need solutions that respect my tight schedule. "${message}" sounds promising, provided it integrates seamlessly into my daily routine without adding hidden overhead.`
        : `That sounds interesting, but I'd need to see how it performs under real conditions first.`,
      timestamp: new Date().toISOString(),
      latency_ms: 780,
      served_by: 'pollinations/deepseek-r1',
      retrieved_memories: [
        `Occupation: ${persona?.demographics.occupation || 'Professional'}`,
        'Values immediate emergency liquidity and transparency',
      ],
    };

    if (conv) {
      conv.turns.push(userTurn, assistantTurn);
    }

    return { userTurn, assistantTurn };
  },

  // 8. Evaluation & Metrics
  async getEvaluationMetrics(): Promise<EvaluationMetrics> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/evaluation/metrics`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        lastKnownLive = true;
        if (res.ok) return await res.json();
        throw await apiErrorFrom(res, 'Failed to fetch evaluation metrics');
      } catch (err) {
        if (err instanceof TypeError) lastKnownLive = false;
        throw err;
      }
    }
    const { mockEvaluationMetrics } = await loadMocks();
    return mockEvaluationMetrics;
  },

  // 8b. Judge Lab (demo-lab): scripted adapters driving the REAL routing code.
  /** Resolves to null when the lab is disabled (404) so callers hide the panel;
   * other failures rethrow. */
  async getDemoLabScenarios(): Promise<DemoLabScenariosResponse | null> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/demo-lab/scenarios`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (res.status === 404) return null;
      if (!res.ok) throw await apiErrorFrom(res, 'Failed to load judge lab scenarios');
      return await res.json();
    }
    const { mockDemoLabScenarios } = await loadMocks();
    return mockDemoLabScenarios;
  },

  async runDemoLabScenario(name: string): Promise<DemoLabRunResult> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/demo-lab/scenarios/${encodeURIComponent(name)}/run`, {
        method: 'POST',
        headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
        // Scripted adapters answer fast, but the real router still runs.
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
      });
      if (!res.ok) throw await apiErrorFrom(res, 'Judge lab scenario failed');
      return await res.json();
    }
    const { mockDemoLabRun } = await loadMocks();
    return mockDemoLabRun(name);
  },

  // 9. Authentication & User Management (JWT + Neon DB)
  hasSession(): boolean {
    return hasCookieSession() || Boolean(this.getAuthToken());
  },

  authRequestHeaders(): Record<string, string> {
    const origin = new URL(API_BASE, window.location.origin);
    return { 'Content-Type': 'application/json', 'X-Auth-Transport': origin.protocol === 'https:' ? 'cookie' : 'bearer' };
  },

  acceptAuthResponse(value: AuthResponse): AuthResponse {
    if (!value || !isRecord(value.user) || typeof value.user.id !== 'string' || !value.user.id ||
        typeof value.user.email !== 'string' || typeof value.user.full_name !== 'string' ||
        typeof value.user.is_active !== 'boolean' || typeof value.access_token !== 'string') {
      throw new Error('Invalid authentication response');
    }
    if (value.verification_required) return value;
    if (!value.access_token && (!value.csrf_token || !/^[a-f0-9]{64}$/i.test(value.csrf_token))) {
      throw new Error('Authentication response contains no session');
    }
    // Same account, fresh credentials: in-flight requests and other tabs keep
    // working. Only an identity change (sign-in, switch) resets the session.
    const rotation = this.getStoredUser()?.id === value.user.id
      && (this.hasSession() || getRefreshCredential() !== null);
    setCookieSession(value.access_token ? null : value.csrf_token ?? null);
    setRefreshCredential(value.refresh_token ?? null);
    this.setAuthToken(value.access_token || null);
    this.setStoredUser(value.user);
    if (!rotation) {
      localStorage.setItem('bebshax_session_generation', crypto.randomUUID());
      advanceSession();
    }
    this.scheduleProactiveRefresh(value);
    return value;
  },

  scheduleProactiveRefresh(value: Pick<AuthResponse, 'access_token' | 'expires_in'>): void {
    cancelProactiveRefresh();
    if (this.isMockMode()) return;
    const seconds = value.expires_in && value.expires_in > 0
      ? value.expires_in
      : value.access_token ? jwtExpiresInSeconds(value.access_token) : null;
    if (seconds === null || (!getRefreshCredential() && !hasCookieSession())) return;
    const delay = Math.max(PROACTIVE_REFRESH_MIN_DELAY_MS, seconds * 1000 - PROACTIVE_REFRESH_LEAD_MS);
    proactiveRefresh = setTimeout(() => {
      proactiveRefresh = null;
      void this.refreshToken().catch(() => undefined);
    }, delay);
  },

  clearSession(): void {
    cancelProactiveRefresh();
    localStorage.removeItem('bebshax_session_generation');
    setCookieSession(null);
    setRefreshCredential(null);
    this.setAuthToken(null);
    this.setStoredUser(null);
    purgePrivateSnapshots();
    advanceSession();
  },

  invalidateTabSession(): void {
    sessionStorage.removeItem('bebshax_auth_token');
    resetSessionSecrets();
    invalidateStudiesCache();
    purgePrivateSnapshots();
    advanceSession(false);
  },

  async getBrowserSession(): Promise<User | null> {
    const expected = getSessionEpoch();
    if (sessionBootstrap?.epoch === expected) return sessionBootstrap.promise;
    const load = async (): Promise<User | null> => {
      assertSession(expected);
      const response = await fetch(`${API_BASE}/auth/session`, {
        headers: { 'X-Auth-Transport': 'cookie' }, signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (response.status === 401) { this.clearSession(); return null; }
      if (!response.ok) throw await apiErrorFrom(response, 'Session verification unavailable');
      const result = await response.json();
      if (!isRecord(result) || !isRecord(result.user) || typeof result.user.id !== 'string' ||
          typeof result.csrf_token !== 'string' || !/^[a-f0-9]{64}$/i.test(result.csrf_token) ||
          typeof result.needs_refresh !== 'boolean') throw new Error('Invalid session response');
        const user = decodeUserProfile(result.user);
      setCookieSession(result.csrf_token);
      if (result.needs_refresh) return (await this.refreshToken())?.user ?? null;
      this.setStoredUser(user);
      return user;
    };
    const promise: Promise<User | null> = Promise.resolve(navigator.locks ? navigator.locks.request('bebshax-browser-session', load) : load());
    sessionBootstrap = { epoch: expected, promise };
    try { return await promise; }
    finally { if (sessionBootstrap?.promise === promise) sessionBootstrap = null; }
  },

  async completeOAuthReturn(): Promise<void> {
    const parameters = new URLSearchParams(window.location.search);
    const state = parameters.get('oauth_state');
    if (!state) return;
    const expected = sessionStorage.getItem('bebshax_oauth_state');
    sessionStorage.removeItem('bebshax_oauth_state');
    parameters.delete('oauth_state');
    const search = parameters.toString();
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${search ? `?${search}` : ''}`);
    if (state !== expected || this.hasSession()) throw new Error('Invalid or already used sign-in return');
    const { neonAuth } = await import('./neonAuth');
    const session = await neonAuth.getSession(null);
    if (!session?.token || !await this.syncUser({ neon_token: session.token })) throw new Error('Google sign-in could not establish an app session');
  },

  _isTokenExpired(token: string): boolean {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return false;
      const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      if (payload && typeof payload.exp === 'number') {
        const nowSeconds = Math.floor(Date.now() / 1000);
        return payload.exp < nowSeconds;
      }
    } catch {
      // not standard JWT or parsing error
    }
    return false;
  },

  getAuthToken(): string | null {
    try {
      const token = sessionStorage.getItem('bebshax_auth_token') || localStorage.getItem('bebshax_auth_token');
      if (token && this._isTokenExpired(token)) {
        // Keep the session: the refresh credential rotates it (getMe() directly,
        // other calls via the 401 replay in sessionFetch) instead of signing out mid-task.
        if (!this.isMockMode() && getRefreshCredential()) return null;
        this.setAuthToken(null);
        this.setStoredUser(null);
        return null;
      }
      return token;
    } catch {
      return null;
    }
  },

  setAuthToken(token: string | null) {
    try {
      const previous = sessionStorage.getItem('bebshax_auth_token') || localStorage.getItem('bebshax_auth_token');
      sessionStorage.removeItem('bebshax_auth_token');
      localStorage.removeItem('bebshax_auth_token');
      if (token) {
        (this.isMockMode() ? localStorage : sessionStorage).setItem('bebshax_auth_token', token);
      }
      // Rotating a live token is not a session boundary; gaining or losing one is.
      if ((previous === null) !== (token === null)) {
        invalidateStudiesCache();
        advanceSession();
      }
    } catch {
      // ignore
    }
  },

  getStoredUser(): User | null {
    try {
      const raw = localStorage.getItem('bebshax_auth_user');
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  setStoredUser(user: User | null) {
    // The identity behind the studies cache key just changed (sign in, sign out,
    // account switch) — anything still held is another account's data.
    invalidateStudiesCache();
    try {
      const previousId = this.getStoredUser()?.id;
      if (user) {
        localStorage.setItem('bebshax_auth_user', JSON.stringify(user));
      } else {
        localStorage.removeItem('bebshax_auth_user');
      }
      if (previousId !== user?.id) {
        purgePrivateSnapshots();
        advanceSession();
      }
    } catch {
      // ignore
    }
  },

  getAuthHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
    const token = this.getAuthToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...customHeaders,
      ...csrfHeaders(),
    };
    if (this.isMockMode()) {
      headers['X-BebshaX-Mock'] = '1';
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  },

  /** Auth headers for a `FormData` body: the browser must write the multipart
   * Content-Type (with its boundary) itself, so none is set here. */
  getMultipartAuthHeaders(): Record<string, string> {
    const { 'Content-Type': _json, ...headers } = this.getAuthHeaders();
    return headers;
  },

  async refreshToken(): Promise<AuthResponse | null> {
    const token = this.getAuthToken();
    if (!token && !hasCookieSession() && !getRefreshCredential()) return null;
    if (this.isMockMode()) return null;
    const expected = getSessionEpoch();
    if (sessionRefresh?.epoch === expected) return sessionRefresh.promise;
    const rotate = async (): Promise<AuthResponse | null> => {
      const presented = getRefreshCredential();
      try {
        // Not sessionFetch: a session-epoch abort mid-rotation would discard a
        // response the server already committed, and the next attempt would
        // replay a rotated token — which revokes the whole family.
        const res = await globalThis.fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          credentials: 'include',
          ...(presented ? { body: JSON.stringify({ refresh_token: presented }) } : {}),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          lastKnownLive = true;
          if (getSessionEpoch() !== expected) {
            // The user signed out (or switched accounts) while this rotation was in
            // flight: never resurrect the session; retire the fresh generation instead.
            if (result.refresh_token) {
              void globalThis.fetch(`${API_BASE}/auth/logout`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include',
                body: JSON.stringify({ refresh_token: result.refresh_token }), keepalive: true,
              }).catch(() => undefined);
            }
            return null;
          }
          this.acceptAuthResponse(result);
          return result;
        }
        if (res.status === 401 || res.status === 403) {
          if (getSessionEpoch() === expected) this.clearSession();
          return null;
        }
        throw await apiErrorFrom(res, 'Session refresh unavailable');
      } catch (error) {
        if (error instanceof TypeError) lastKnownLive = false;
        throw error;
      }
    };
    const promise = rotate();
    sessionRefresh = { epoch: expected, promise };
    try { return await promise; }
    finally { if (sessionRefresh?.promise === promise) sessionRefresh = null; }
  },

  async syncUser(data: {
    neon_token: string;
    auth_provider?: string;
  }): Promise<AuthResponse | null> {
    if (this.isMockMode()) return null;
    try {
      const res = await fetch(`${API_BASE}/auth/sync`, {
        method: 'POST',
        headers: this.authRequestHeaders(),
        body: JSON.stringify({
          neon_token: data.neon_token,
          auth_provider: data.auth_provider || 'neon',
        }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (res.ok) {
        const result: AuthResponse = await res.json();
        this.acceptAuthResponse(result);
        lastKnownLive = true;
        return result;
      }
      // Surfaced (not thrown): callers treat null as "no session", but a
      // silent null after an OAuth return looks like a mystery logout.
      console.warn(`Auth sync failed: HTTP ${res.status}`);
    } catch (err) {
      console.warn('Auth sync failed:', err);
    }
    return null;
  },

  async signup(data: SignUpData): Promise<AuthResponse> {
    advanceSession(false);
    if (this.isMockMode()) {
      // Mock/test builds only — a fabricated session must never be reachable
      // from a live backend response.
      const mockUser: User = {
        id: `usr_${Date.now()}`,
        email: data.email,
        full_name: data.full_name,
        avatar_url: null,
        is_active: true,
        is_verified: false,
        auth_provider: 'email',
        created_at: new Date().toISOString(),
      };
      return {
        access_token: `mock_jwt_${Date.now()}`,
        token_type: 'bearer',
        expires_in_days: 7,
        user: mockUser,
      };
    }

    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: 'POST',
      headers: this.authRequestHeaders(),
      body: JSON.stringify(data),
      signal: AbortSignal.timeout(30000),
    });
    if (res.ok) {
      const result: AuthResponse = await res.json();
      lastKnownLive = true;
      return result;
    }
    lastKnownLive = true;
    const errorData = await res.json().catch(() => ({}));
    if (res.status === 409) {
      throw authError(summariseDetail(errorData.detail, 'An account with this email address already exists.'));
    }
    if (res.status === 422) {
      // Validation envelopes carry a `message`; the `detail` array is per-field.
      throw authError(
        (typeof errorData.message === 'string' && errorData.message) || summariseDetail(errorData.detail, 'Please check the sign-up details and try again.'),
        'VALIDATION_ERROR',
      );
    }
    throw authError(
      summariseDetail(errorData.detail, `Registration failed (server error ${res.status}). Please try again.`)
    );
  },

  async signin(data: SignInData): Promise<AuthResponse> {
    advanceSession(false);
    if (this.isMockMode()) {
      // Mock/test builds only — never reachable from a live backend response.
      const mockUser: User = {
        id: 'usr_sarah_founder',
        email: data.email,
        full_name: data.email.split('@')[0] || 'BebshaX User',
        avatar_url: null,
        is_active: true,
        is_verified: true,
        auth_provider: 'email',
        created_at: new Date().toISOString(),
      };
      const mockRes: AuthResponse = {
        access_token: `mock_jwt_${Date.now()}`,
        token_type: 'bearer',
        expires_in_days: 7,
        user: mockUser,
      };
      this.setAuthToken(mockRes.access_token);
      this.setStoredUser(mockUser);
      return mockRes;
    }

    // 1. Primary: Direct Backend API authentication (verifies against PostgreSQL users table)
    try {
      const res = await fetch(`${API_BASE}/auth/signin`, {
        method: 'POST',
        headers: this.authRequestHeaders(),
        body: JSON.stringify(data),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (res.ok) {
        const result: AuthResponse = await res.json();
        this.acceptAuthResponse(result);
        lastKnownLive = true;
        return result;
      }
      // The server answered, so it is reachable — every non-ok status is a
      // real failure and must surface. Falling through here once minted a
      // fabricated session on a 500.
      lastKnownLive = true;
      const errorData = await res.json().catch(() => ({}));
      if (res.status === 401 || res.status === 403) {
        const detail: string = summariseDetail(errorData.detail, 'Invalid email or password.');
        if (detail.includes('EMAIL_NOT_VERIFIED')) {
          throw authError(
            'Your email address is not verified yet. Enter the 6-digit code we send you to finish signing in.',
            'EMAIL_NOT_VERIFIED'
          );
        }
        throw authError(detail);
      }
      if (res.status === 429) {
        throw authError(
          (typeof errorData.message === 'string' && errorData.message) || summariseDetail(errorData.detail, 'Too many sign-in attempts. Try again in a moment.'),
          'RATE_LIMITED',
        );
      }
      throw authError(
        (typeof errorData.message === 'string' && errorData.message) || summariseDetail(errorData.detail, `Sign-in failed (server error ${res.status}). Please try again.`)
      );
    } catch (backendErr: unknown) {
      throw backendErr;
    }
  },

  async googleAuth(data: GoogleAuthData): Promise<AuthResponse> {
    if (!this.isMockMode()) {
      // No POST /api/auth/google exists, and a session is never fabricated
      // client-side. The real federated path is neonAuth.signInWithGoogle()
      // → Neon-hosted OAuth → server-verified /api/auth/sync.
      throw new Error(
        'Google sign-in requires the Neon Auth flow — no local fallback session exists. Use "Continue with Google" (Neon OAuth) or email sign-in.'
      );
    }

    // Mock/test builds only: mint a clearly-mock local session (mirrors how
    // email signin is mocked under the same gate).
    const email = data.email || 'user@bebshax.io';
    const name =
      data.name ||
      email
        .split('@')[0]
        .replace(/[._]/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());

    const mockUser: User = {
      id: `usr_g_${Date.now().toString(36)}`,
      email,
      full_name: name,
      avatar_url: data.avatar_url || undefined,
      is_active: true,
      is_verified: true,
      auth_provider: 'google',
      created_at: new Date().toISOString(),
    };
    const mockRes: AuthResponse = {
      access_token: `mock_jwt_g_${Date.now()}`,
      token_type: 'bearer',
      expires_in_days: 7,
      user: mockUser,
    };
    this.setAuthToken(mockRes.access_token);
    this.setStoredUser(mockUser);
    return mockRes;
  },

  async getMe(): Promise<User | null> {
    if (!this.isMockMode() && hasCookieSession()) return this.getBrowserSession();
    const token = this.getAuthToken();
    const expected = getSessionEpoch();
    if (!token) {
      return !this.isMockMode() && getRefreshCredential() ? (await this.refreshToken())?.user ?? null : null;
    }

    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          const user = decodeUserProfile(await res.json());
          assertSession(expected);
          this.setStoredUser(user);
          // A reload restores the session without acceptAuthResponse; re-arm the rotation timer.
          this.scheduleProactiveRefresh({ access_token: token });
          return user;
        } else if (res.status === 401 || res.status === 403) {
          // The access token is rejected (expired while the tab slept, rotated
          // elsewhere). The refresh credential is the session; use it exactly
          // as the in-app 401 replay path does before giving up.
          lastKnownLive = true;
          if (res.status === 401 && getRefreshCredential()) {
            try {
              const refreshed = await this.refreshToken();
              if (refreshed?.user) {
                assertSession(expected);
                return refreshed.user;
              }
            } catch {
              // fall through: the refresh itself was refused
            }
          }
          this.clearSession();
          return null;
        }
        throw await apiErrorFrom(res, 'Session verification unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }

    return this.getStoredUser();
  },

  async resendVerificationEmail(email: string): Promise<boolean> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/auth/resend-verification`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        return res.ok;
      } catch {
        return false;
      }
    }
    return true;
  },

  async sendOtp(
    email: string,
    type: 'email-verification' | 'forget-password' | 'sign-in' = 'email-verification'
  ): Promise<boolean> {
    if (type === 'sign-in') throw new Error('Passwordless sign-in is not available');
    if (type === 'forget-password') {
      if (this.isMockMode()) return true;
      const response = await fetch(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), purpose: type }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!response.ok) throw await apiErrorFrom(response, 'Password recovery unavailable');
      return true;
    }
    return await this.resendVerificationEmail(email);
  },

  async verifyEmailOtp(
    email: string,
    otp: string
  ): Promise<{ user: User; token?: string | null }> {
    if (!this.isMockMode()) {
      if (!email.trim()) throw new Error('Email is required to verify this code');
      const response = await fetch(`${API_BASE}/auth/verify-email`, {
        method: 'POST', headers: this.authRequestHeaders(),
        body: JSON.stringify({ token: otp.trim(), email: email.trim() }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!response.ok) throw await apiErrorFrom(response, 'Email verification failed');
      const result: AuthResponse = await response.json();
      if (!result?.user?.id || typeof result.access_token !== 'string') throw new Error('Invalid verification response');
      this.acceptAuthResponse(result);
      return { user: result.user, token: result.access_token || null };
    }
    const user: User = {
      id: `usr_${Date.now().toString(36)}`,
      email,
      full_name: email.split('@')[0],
      avatar_url: null,
      is_active: true,
      is_verified: true,
      auth_provider: 'neon',
      created_at: new Date().toISOString(),
    };
    this.setAuthToken(`mock_jwt_${Date.now()}`);
    this.setStoredUser(user);
    return { user, token: this.getAuthToken() };
  },

  async resetPasswordWithOtp(
    email: string,
    otp: string,
    password: string
  ): Promise<boolean> {
    if (!this.isMockMode()) {
      const response = await fetch(`${API_BASE}/auth/reset-password`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), otp: otp.trim(), password, purpose: 'forget-password' }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!response.ok) throw await apiErrorFrom(response, 'Password reset failed');
    }
    this.clearSession();
    return true;
  },

  async signout(): Promise<void> {
    const headers = this.getAuthHeaders();
    const refresh = getRefreshCredential();
    advanceSession(false);
    const expected = getSessionEpoch();
    // Deliberate sign-out: other tabs of this browser end their sessions too.
    try {
      localStorage.setItem(SIGNOUT_BROADCAST_KEY, String(Date.now()));
    } catch {
      // best-effort broadcast
    }
    try {
      if (!this.isMockMode()) {
        const response = await fetch(`${API_BASE}/auth/logout`, {
          method: 'POST', headers, signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
          ...(refresh ? { body: JSON.stringify({ refresh_token: refresh }) } : {}),
        });
        if (!response.ok && response.status !== 401) throw await apiErrorFrom(response, 'Server logout was not confirmed');
      }
    } finally {
      if (getSessionEpoch() === expected) {
        this.clearSession();
      }
    }
  },

  // 10. Research Studies Management (New Study, Dashboard, Workflows)
  // 10. Research Studies Management (User-Scoped 5-Step Workflow Persistence)
  getUserStudiesStorageKey(): string {
    const user = this.getStoredUser();
    return `bebshax_studies_${this.isMockMode() ? 'mock' : 'live'}_${user?.id || 'default_user'}`;
  },

  getStoredUserStudies(): Study[] {
    const mockMode = this.isMockMode();
    const userId = this.getStoredUser()?.id;
    if (!mockMode && !userId) return [];
    try {
      const key = this.getUserStudiesStorageKey();
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return mockMode ? parsed : parsed.filter((study) => study?.user_id === userId);
        }
      }
    } catch {
      // ignore
    }
    // Sync mock callers await loadMocks(); live reads must never use its seeds.
    return mockMode && _mocksSync ? [..._mocksSync.mockStore.studies] : [];
  },

  /** Write-through used by reads. Deliberately does NOT invalidate: a read
   * persisting what it just fetched is not a mutation, and treating it as one
   * made the cache below unfillable.
   *
   * `expectedKey` is the storage key the caller resolved *before* the fetch. A
   * read started as user A can resolve after a sign-out/sign-in as user B, and
   * without this guard it would write A's studies into B's bucket — which B's
   * next create/update/delete then persists back as B's own. */
  persistStoredUserStudies(studies: Study[], expectedKey?: string) {
    try {
      const mockMode = this.isMockMode();
      const userId = this.getStoredUser()?.id;
      if (!mockMode && !userId) return;
      const key = this.getUserStudiesStorageKey();
      if (expectedKey !== undefined && expectedKey !== key) return;
      const ownedStudies = mockMode ? studies : studies.filter((study) => study?.user_id === userId);
      localStorage.setItem(key, JSON.stringify(ownedStudies));
    } catch {
      // ignore
    }
  },

  saveStoredUserStudies(studies: Study[]) {
    // Every create/update/delete path funnels through here, so this is the one
    // place the coalescing cache has to be dropped.
    invalidateStudiesCache();
    this.persistStoredUserStudies(studies);
    notifyStudiesChanged(studies);
  },

  async getStudies(): Promise<Study[]> {
    // Keyed by user: signing out and back in as someone else must never be
    // served the previous account's studies out of a process-global cache.
    const storageKey = this.getUserStudiesStorageKey();
    const key = `${this.isMockMode() ? 'mock' : 'live'}:${storageKey}`;
    if (studiesCache && studiesCache.key === key && Date.now() - studiesCache.at < STUDIES_CACHE_TTL_MS) {
      // Copy: the three dashboard consumers share this entry for the TTL
      // window, and one in-place sort would corrupt the other two views.
      return structuredClone(studiesCache.value);
    }
    if (studiesInFlight && studiesInFlight.key === key) {
      return studiesInFlight.promise.then((value) => structuredClone(value));
    }
    const generation = studiesGeneration;
    const promise = this.fetchStudies(storageKey)
      .then((value) => {
        if (generation === studiesGeneration) {
          studiesCache = { at: Date.now(), key, value };
        }
        return value;
      })
      .finally(() => {
        // Only clear our own entry: an invalidation mid-flight may already have
        // started a newer request, and clearing unconditionally would drop it.
        if (studiesInFlight?.promise === promise) studiesInFlight = null;
      });
    studiesInFlight = { key, promise };
    return promise.then((value) => structuredClone(value));
  },

  async fetchStudies(expectedKey?: string): Promise<Study[]> {
    if (!this.isMockMode()) {
      try {
        const user = this.getStoredUser();
        const url = user?.id ? `${API_BASE}/studies?user_id=${encodeURIComponent(user.id)}` : `${API_BASE}/studies`;
        const res = await fetch(url, {
          headers: this.getAuthHeaders(),
          // DB read, but a busy backend (LLM calls in flight) can exceed 5s —
          // aborting here silently empties the dashboard.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            this.persistStoredUserStudies(data, expectedKey);
            return data;
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch studies (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    // Populate the sync cache before the localStorage-fallback read below.
    await loadMocks();
    return this.getStoredUserStudies();
  },

  async getStudyById(id: string): Promise<Study | null> {
    if (!this.isMockMode()) {
      if (studyDetailEpoch !== getSessionEpoch()) {
        studyDetailCache.invalidate();
        studyDetailEpoch = getSessionEpoch();
      }
      return studyDetailCache.read(`${studyDetailEpoch}:${id}:${knownStudyRevision(id) ?? 'unknown'}`, async () => {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          headers: this.getAuthHeaders(),
          // Restores the whole workflow state — aborting early loses chat/personas in the UI.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          const study: Study = await res.json();
          if (!study || study.id !== id) throw new Error('Invalid study response');
          rememberStudyRevision(study);
          return study;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to fetch study');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
      });
    }
    await loadMocks();
    const studies = this.getStoredUserStudies();
    const study = studies.find((s) => s.id === id);
    return study ? { ...study } : null;
  },

  async getStudy(id: string): Promise<Study | null> {
    return this.getStudyById(id);
  },

  /** A server-side job this tab started (evidence research, report
   * projection) advanced the study revision. Re-read the row so the next
   * queued save targets it instead of bouncing off a 412 first. Safe with a
   * pending draft: `rememberStudyRevision` refuses to move the base then. */
  async syncStudyRevision(id: string): Promise<void> {
    if (this.isMockMode()) return;
    invalidateStudiesCache();
    studyDetailCache.invalidate();
    await this.getStudyById(id).catch(() => null);
  },

  async createStudy(studyData: Partial<Study>): Promise<Study> {
    const user = this.getStoredUser();
    const payload = {
      ...studyData,
      user_id: user?.id || 'usr_default',
    };

    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          // Deterministic title generation — no LLM in this path.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          const created = await res.json();
          rememberStudyRevision(created);
          const current = this.getStoredUserStudies();
          const next = [created, ...current.filter((s) => s.id !== created.id)];
          this.saveStoredUserStudies(next);
          return created;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to create study');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const newStudy: Study = {
      id: studyData.id || `study_${Date.now()}`,
      user_id: user?.id || 'usr_default',
      title: studyData.title || 'Untitled Study',
      type: studyData.type || 'interviews',
      goal: studyData.goal || 'demand_validation',
      prompt: studyData.prompt || '',
      status: studyData.status || 'draft',
      persona_count: studyData.persona_count || 0,
      persona_ids: studyData.persona_ids || [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      duration_text: 'Just created • No personas yet',
      is_demo: false,
      step: studyData.step || 1,
      ...studyData,
    };
    await loadMocks();
    const current = this.getStoredUserStudies();
    const next = [newStudy, ...current.filter((s) => s.id !== newStudy.id)];
    this.saveStoredUserStudies(next);
    return newStudy;
  },

  getPendingStudyDraft(id: string): Partial<Study> | undefined {
    return pendingStudyDraft(this.getStoredUser()?.id ?? 'anonymous', id);
  },

  discardStudyDraft(id: string): void {
    discardStudyDraft(this.getStoredUser()?.id ?? 'anonymous', id);
  },

  async updateStudy(id: string, updates: Partial<Study>): Promise<Study> {
    if (!this.isMockMode()) {
      invalidateStudiesCache();
      // The loader must see the server's current revision (a cached detail read
      // is keyed by the revision we already know, i.e. the stale one).
      const loadFresh = () => {
        studyDetailCache.invalidate();
        return this.getStudy(id);
      };
      return queueStudyWrite(id, this.getStoredUser()?.id ?? 'anonymous', updates, loadFresh, async (draft, revision) => {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          method: 'PATCH',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json', 'If-Match': `"${revision}"` }),
          body: JSON.stringify({ ...draft, expected_revision: revision }),
          // Large JSON payloads (personas_data, chat history) but pure DB write.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          const updated: Study = await res.json();
          if (!updated || updated.id !== id || !Number.isInteger(updated.revision) || !updated.revision || updated.revision <= revision) {
            throw new Error('The server did not acknowledge a newer study revision');
          }
          const current = this.getStoredUserStudies();
          const index = current.findIndex((s) => s.id === id);
          if (index !== -1) {
            current[index] = updated;
          } else {
            current.unshift(updated);
          }
          this.saveStoredUserStudies(current);
          return updated;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to update study');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
      });
    }

    await loadMocks();
    const current = this.getStoredUserStudies();
    const index = current.findIndex((s) => s.id === id);
    if (index === -1) {
      const created = await this.createStudy({ id, ...updates });
      return created;
    }
    const updated: Study = {
      ...current[index],
      ...updates,
      updated_at: new Date().toISOString(),
    };
    current[index] = updated;
    this.saveStoredUserStudies(current);
    return updated;
  },

  async deleteStudy(id: string): Promise<boolean> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          method: 'DELETE',
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (!res.ok && res.status !== 404) {
          lastKnownLive = false;
          throw new Error(`Failed to delete study (HTTP ${res.status})`);
        }
        lastKnownLive = true;
      } catch (err) {
        // A locally-hidden study that still exists server-side is a lie.
        lastKnownLive = false;
        throw err;
      }
    }
    // Shared tail: mock mode needs the seed studies behind the sync fallback.
    if (this.isMockMode()) await loadMocks();
    const current = this.getStoredUserStudies();
    const next = current.filter((s) => s.id !== id);
    this.saveStoredUserStudies(next);
    return true;
  },

  async saveAudience(data: {
    name: string;
    study_id?: string;
    description?: string;
    persona_ids: string[];
    personas_payload?: any[];
    role_distribution?: Record<string, number>;
  }): Promise<{ id: string; name: string }> {
    const user = this.getStoredUser();
    const payload = {
      ...data,
      user_id: user?.id || 'usr_default',
    };
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/audiences`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Failed to save audience');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return { id: `aud_${Date.now()}`, name: data.name };
  },

  async getSavedAudiences(): Promise<any[]> {
    if (!this.isMockMode()) {
      try {
        const user = this.getStoredUser();
        const url = user?.id ? `${API_BASE}/audiences?user_id=${encodeURIComponent(user.id)}` : `${API_BASE}/audiences`;
        const res = await fetch(url, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch audiences (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return [];
  },

  // 11. Study Design Copilot (Conversational LLM Workflow Initiation)
  async sendStudyCopilotMessage(
    messages: { role: 'user' | 'assistant'; content: string }[],
    studyType?: StudyType,
    studyId?: string
  ): Promise<{
    reply: string;
    suggested_study_type: StudyType;
    is_ready_for_approval: boolean;
    research_goal_card?: {
      title: string;
      summary: string;
      target_audience: string;
      core_hypothesis: string;
    } | null;
    suggested_roles?: PersonaRoleSuggestion[];
    served_by: string;
    /** Set by the backend when the reply came from its keyword-template engine
     * instead of an LLM (e.g. `llm_error:TimeoutError`, `llm_router_unavailable`). */
    fallback_reason?: string | null;
  }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/study/copilot`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            messages,
            study_type: studyType,
            study_id: studyId,
          }),
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Copilot turn failed');
      } catch (err) {
        // Live mode never falls back to the local canned engine — a fabricated
        // "LLM reply" is worse than a visible failure.
        lastKnownLive = false;
        throw err;
      }
    }

    const { mockCopilotReply } = await loadMocks();
    return mockCopilotReply(messages);
  },

  async getSuggestedPersonaRoles(studyPrompt: string): Promise<PersonaRoleSuggestion[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/study/suggest-roles`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ study_prompt: studyPrompt }),
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Role suggestion failed');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    // Context-aware fallback: derive roles from the study prompt
    const { mockSuggestedRoles } = await loadMocks();
    return mockSuggestedRoles(studyPrompt);
  },

  async generateStudyPersonas(
    studyId?: string,
    prompt?: string,
    roles?: PersonaRoleSuggestion[],
    title?: string
  ): Promise<Persona[]> {
    const result = await this.generateStudyPersonasDetailed(studyId, prompt, roles, title);
    return result.personas;
  },

  /** Full envelope: personas written by the model for THIS study, plus the
   * roles whose generation failed (each with its error code) and the routes
   * that served the batch. Nothing is generated locally in live mode. */
  async generateStudyPersonasDetailed(
    studyId?: string,
    prompt?: string,
    roles?: PersonaRoleSuggestion[],
    title?: string
  ): Promise<GeneratePersonasResult> {
    if (!this.isMockMode()) {
      // Live mode: no silent mock substitution. A generation failure must be
      // visible to the user — fabricated personas would poison their research.
      // The server updates the study row (revision counter) while it saves the
      // cohort; a queued step/draft PATCH landing mid-flight made that a 409/500.
      if (studyId) await waitForStudyWrites(studyId);
      const res = await fetch(`${API_BASE}/study/generate-personas`, {
        method: 'POST',
        headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          study_id: studyId,
          study_prompt: prompt,
          study_title: title,
          roles: roles || [],
        }),
        signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
      });
      if (!res.ok) {
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Persona generation failed');
      }
      lastKnownLive = true;
      const data = (await res.json()) as GeneratePersonasResult | Persona[];
      // Backend envelope {personas, failed_roles, served_by}; a bare array is
      // tolerated for older servers.
      const envelope: GeneratePersonasResult = Array.isArray(data)
        ? { personas: data, failed_roles: [], served_by: [] }
        : { personas: data.personas ?? [], failed_roles: data.failed_roles ?? [], served_by: data.served_by ?? [], study_revision: data.study_revision ?? null };
      if (envelope.personas.length === 0) {
        const reasons = envelope.failed_roles.map((f) => `${f.role}: ${f.detail}`).join('; ');
        throw new Error(reasons ? `No persona could be generated — ${reasons}` : 'Persona generation returned no personas');
      }
      invalidateStudiesCache();
      if (studyId) adoptStudyRevision(studyId, envelope.study_revision);
      return envelope;
    }

    const { mockGeneratedPersonas } = await loadMocks();
    return { personas: await mockGeneratedPersonas(prompt, title), failed_roles: [], served_by: ['mock/local'] };
  },

  // =========================================================================
  // Independent AI review (CRITIC pass over the study's own artefacts)
  // =========================================================================

  /** Live only: a review is a fresh model judgement, never a mock. In mock mode
   * the caller receives an explicit error instead of a canned verdict. */
  async requestStudyAiReview(studyId: string, personaId?: string): Promise<AiReviewVerdict> {
    if (this.isMockMode()) {
      throw new Error('AI review needs the live backend — it is a fresh model judgement and is never mocked.');
    }
    const path = personaId
      ? `${API_BASE}/studies/${studyId}/personas/${personaId}/ai-review`
      : `${API_BASE}/studies/${studyId}/ai-review`;
    const res = await fetch(path, {
      method: 'POST',
      headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
      signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
    });
    if (!res.ok) {
      lastKnownLive = false;
      throw await apiErrorFrom(res, 'AI review failed');
    }
    lastKnownLive = true;
    return (await res.json()) as AiReviewVerdict;
  },

  // =========================================================================
  // OpenRouter Diagnostics API
  // =========================================================================

  async getOpenRouterHealth(): Promise<OpenRouterHealth> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/health/openrouter`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`OpenRouter health check failed (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      configured: true,
      authenticated: true,
      model: 'meta-llama/llama-3.3-70b-instruct:free',
      status: 'healthy',
      latency_ms: 320.5,
      message: 'OpenRouter diagnostic check (Mock / Local Mode).',
      verified_response: 'BebshaX OpenRouter connection verified.',
    };
  },

  async testOpenRouterConnection(model?: string): Promise<OpenRouterHealth> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/health/openrouter/test`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ model }),
          // Sends a real test completion — free-tier latency applies.
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const errData = await res.json().catch(() => ({}));
        return {
          configured: errData.configured ?? true,
          authenticated: false,
          model: model || 'default',
          status: 'error',
          error_code: errData.error_code || 'OPENROUTER_AUTH_FAILED',
          message: errData.message || 'OpenRouter test request failed.',
        };
      } catch (err: any) {
        lastKnownLive = false;
        return {
          configured: true,
          authenticated: false,
          model: model || 'default',
          status: 'error',
          error_code: 'OPENROUTER_CONNECTION_ERROR',
          message: `Connection error: ${err.message || err}`,
        };
      }
    }
    return {
      configured: true,
      authenticated: true,
      model: model || 'meta-llama/llama-3.3-70b-instruct:free',
      status: 'healthy',
      latency_ms: 245.2,
      message: 'OpenRouter connection successful (Verified).',
      verified_response: 'BebshaX OpenRouter connection successful.',
    };
  },

  // -------------------------------------------------------------
  // Evidence & Research Engine API Methods — extracted to researchApi.ts
  // (startResearch … rejectDatasetCandidate, plus triggerStudyResearch)
  // -------------------------------------------------------------
  ...researchApi,

  // ============================================================================
  // Dataset Sources & Data Lab
  // ============================================================================

  async listDatasets(studyId?: string): Promise<DatasetSource[]> {
    if (!this.isMockMode()) {
      try {
        const url = studyId ? `${API_BASE}/studies/${studyId}/datasets` : `${API_BASE}/datasets`;
        const res = await fetch(url, { headers: this.getAuthHeaders() });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch datasets (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    return studyId
      ? mockStore.datasets.filter((d) => !d.study_id || d.study_id === studyId)
      : [...mockStore.datasets];
  },

  async getStudyDatasets(studyId: string): Promise<DatasetSource[]> {
    return this.listDatasets(studyId);
  },

  async addDatasetUrl(data: {
    url: string;
    name: string;
    description?: string;
    file_type?: string;
    study_id?: string;
  }): Promise<DatasetSource> {
    if (!this.isMockMode()) {
      try {
        const endpoint = data.study_id
          ? `${API_BASE}/studies/${data.study_id}/datasets/url`
          : `${API_BASE}/datasets/url`;
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(data),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to ingest dataset URL');
      } catch (e: any) {
        // Live mode: connectivity loss surfaces — no fabricated dataset rows.
        lastKnownLive = false;
        throw e;
      }
    }

    const created: DatasetSource = {
      id: `ds_${Date.now()}`,
      study_id: data.study_id || 'study_default',
      name: data.name,
      source_type: 'url',
      source_url: data.url,
      file_type: data.file_type || 'csv',
      description: data.description || null,
      status: 'ready',
      row_count: 5400,
      column_count: 8,
      schema_metadata: {
        row_count: 5400,
        column_count: 8,
        duplicate_rows: 12,
        missing_values_percentage: 1.8,
        warnings: [],
        columns: [
          { name: 'user_id', type: 'text', missing_count: 0, missing_percentage: 0, unique_count: 5400, sample_values: ['u1', 'u2'] },
          { name: 'monthly_spend', type: 'numeric', missing_count: 45, missing_percentage: 0.8, unique_count: 40, sample_values: [300, 500] },
          { name: 'category', type: 'categorical', missing_count: 0, missing_percentage: 0, unique_count: 4, sample_values: ['Student', 'Professional'] },
        ],
      },
      statistics: {
        numeric: {
          monthly_spend: { count: 5355, min: 100, max: 3000, mean: 650, median: 450, std: 280, p25: 300, p75: 750, iqr: 450 },
        },
        categorical: {
          category: { count: 5400, unique_categories: 4, top_categories: [{ category: 'Student', count: 3600, percentage: 66.67 }], percentages: { Student: 66.67 } },
        },
        overview: { row_count: 5400, column_count: 8, duplicate_rows: 12, missing_values_percentage: 1.8 },
      },
      segments: [],
      persona_count_generated: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_processed_at: new Date().toISOString(),
    };
    const { mockStore } = await loadMocks();
    mockStore.datasets.unshift(created);
    return created;
  },

  async uploadDataset(formData: FormData, studyId?: string): Promise<DatasetSource> {
    if (!this.isMockMode()) {
      try {
        const endpoint = studyId
          ? `${API_BASE}/studies/${studyId}/datasets/upload`
          : `${API_BASE}/datasets/upload`;
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: this.getMultipartAuthHeaders(),
          body: formData,
          signal: sessionSignal(undefined, TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to upload dataset');
      } catch (e: any) {
        // Live mode: connectivity loss surfaces — no fabricated dataset rows.
        lastKnownLive = false;
        throw e;
      }
    }

    const file = formData.get('file') as File | null;
    const name = (formData.get('name') as string) || file?.name || 'Uploaded Dataset';
    const desc = (formData.get('description') as string) || '';

    const created: DatasetSource = {
      id: `ds_${Date.now()}`,
      study_id: studyId || 'study_default',
      name: name,
      source_type: 'upload',
      original_file_name: file?.name || 'uploaded_data.csv',
      file_type: file?.name?.split('.').pop() || 'csv',
      description: desc || null,
      status: 'ready',
      row_count: 2800,
      column_count: 6,
      schema_metadata: {
        row_count: 2800,
        column_count: 6,
        duplicate_rows: 0,
        missing_values_percentage: 0.5,
        warnings: [],
        columns: [
          { name: 'age', type: 'numeric', missing_count: 5, missing_percentage: 0.18, unique_count: 25, sample_values: [19, 21, 24] },
          { name: 'city', type: 'categorical', missing_count: 0, missing_percentage: 0, unique_count: 5, sample_values: ['Dhaka', 'Chittagong'] },
        ],
      },
      statistics: {
        numeric: {
          age: { count: 2795, min: 18, max: 32, mean: 22.8, median: 22, std: 2.5, p25: 20, p75: 25, iqr: 5 },
        },
        categorical: {
          city: { count: 2800, unique_categories: 5, top_categories: [{ category: 'Dhaka', count: 1800, percentage: 64.29 }], percentages: { Dhaka: 64.29 } },
        },
        overview: { row_count: 2800, column_count: 6, duplicate_rows: 0, missing_values_percentage: 0.5 },
      },
      segments: [],
      persona_count_generated: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_processed_at: new Date().toISOString(),
    };
    const { mockStore } = await loadMocks();
    mockStore.datasets.unshift(created);
    return created;
  },

  async getDataset(datasetId: string, studyId?: string): Promise<DatasetSource> {
    if (!this.isMockMode()) {
      try {
        const url = studyId
          ? `${API_BASE}/studies/${studyId}/datasets/${datasetId}`
          : `${API_BASE}/datasets/${datasetId}`;
        const res = await fetch(url, { headers: this.getAuthHeaders() });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch dataset (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    const found = mockStore.datasets.find((d) => d.id === datasetId);
    if (found) return found;
    return mockStore.datasets[0];
  },

  async getDatasetPreview(
    datasetId: string,
    offset: number = 0,
    limit: number = 20,
    studyId?: string
  ): Promise<DatasetPreviewResponse> {
    if (!this.isMockMode()) {
      try {
        const url = studyId
          ? `${API_BASE}/studies/${studyId}/datasets/${datasetId}/preview?offset=${offset}&limit=${limit}`
          : `${API_BASE}/datasets/${datasetId}/preview?offset=${offset}&limit=${limit}`;
        const res = await fetch(url, { headers: this.getAuthHeaders() });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch dataset preview (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    return {
      columns: ['age', 'occupation', 'monthly_budget', 'platform'],
      rows: [
        { age: 21, occupation: 'Undergrad Student', monthly_budget: 450, platform: 'Mobile Android' },
        { age: 22, occupation: 'Undergrad Student', monthly_budget: 500, platform: 'Desktop Web' },
        { age: 19, occupation: 'HSC Candidate', monthly_budget: 350, platform: 'Mobile Android' },
        { age: 24, occupation: 'Part-time Tutor', monthly_budget: 800, platform: 'iOS' },
        { age: 20, occupation: 'Undergrad Student', monthly_budget: 400, platform: 'Mobile Android' },
      ],
      total_rows: 5,
      offset,
      limit,
    };
  },

  async refreshDataset(datasetId: string, studyId?: string): Promise<DatasetSource> {
    if (!this.isMockMode()) {
      try {
        const url = studyId
          ? `${API_BASE}/studies/${studyId}/datasets/${datasetId}/refresh`
          : `${API_BASE}/datasets/${datasetId}/refresh`;
        const res = await fetch(url, {
          method: 'POST',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to refresh dataset (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const { mockStore } = await loadMocks();
    const ds = mockStore.datasets.find((d) => d.id === datasetId) || mockStore.datasets[0];
    const updated = { ...ds, last_processed_at: new Date().toISOString() };
    mockStore.datasets = mockStore.datasets.map((d) => (d.id === datasetId ? updated : d));
    return updated;
  },

  async deleteDataset(datasetId: string, studyId?: string): Promise<void> {
    if (!this.isMockMode()) {
      try {
        const url = studyId
          ? `${API_BASE}/studies/${studyId}/datasets/${datasetId}`
          : `${API_BASE}/datasets/${datasetId}`;
        const res = await fetch(url, {
          method: 'DELETE',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          const { mockStore } = await loadMocks();
          mockStore.datasets = mockStore.datasets.filter((d) => d.id !== datasetId);
          return;
        }
        lastKnownLive = false;
        throw new Error(`Failed to delete dataset (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockStore } = await loadMocks();
    mockStore.datasets = mockStore.datasets.filter((d) => d.id !== datasetId);
  },

  async generateDatasetPersonas(
    datasetId: string,
    data: {
      requested_count: number;
      business_name: string;
      business_description: string;
      study_id?: string;
    }
  ): Promise<DatasetPersonaRun> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/datasets/${datasetId}/generate-personas`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(data),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Dataset persona generation failed');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    return {
      run_id: `gen_run_${Date.now()}`,
      dataset_id: datasetId,
      dataset_name: 'Student Survey 2026',
      model_used: 'openrouter/meta-llama/llama-3.3-70b-instruct',
      requested_count: data.requested_count,
      generated_count: data.requested_count,
      valid_count: Math.floor(data.requested_count * 0.8),
      warning_count: Math.floor(data.requested_count * 0.2),
      contradiction_count: 0,
      distribution: { 'Budget-Conscious Students': data.requested_count },
      personas: [],
      validation_summary: [],
    };
  },

  async checkOpenRouterHealth(): Promise<OpenRouterHealth> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/health/openrouter`);
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`OpenRouter health check failed (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      status: 'healthy',
      api_key_configured: true,
      api_key_preview: 'sk-or-v1-••••••••',
      active_model: 'meta-llama/llama-3.3-70b-instruct:free',
      supported_models: [
        'meta-llama/llama-3.3-70b-instruct:free',
        'deepseek/deepseek-r1:free',
        'qwen/qwen-2.5-72b-instruct:free',
      ],
      quota_status: 'Free tier / Active',
      last_checked_at: new Date().toISOString(),
    };
  },

  async testOpenRouterModel(model: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/health/openrouter/test`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model }),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`OpenRouter model test failed (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      success: true,
      model,
      latency_ms: 412,
      response_text: 'OpenRouter diagnostic test response successful.',
    };
  },
  // --- Market Segmentation API Methods ---
  async getSegmentationReadiness(studyId: string): Promise<SegmentationReadiness> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segmentation/readiness`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch segmentation readiness (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      status: 'ready',
      can_run: true,
      dataset_count: 1,
      total_records: 1200,
      usable_variables_count: 4,
      usable_variables: [
        {
          name: 'monthly_budget_bdt',
          type: 'numeric',
          source_dataset_name: 'Survey Data',
          source_dataset_id: 'ds_1',
          coverage_percentage: 98.5,
          missing_percentage: 1.5,
          usefulness: 'high',
        },
        {
          name: 'study_hours_per_day',
          type: 'numeric',
          source_dataset_name: 'Survey Data',
          source_dataset_id: 'ds_1',
          coverage_percentage: 99.0,
          missing_percentage: 1.0,
          usefulness: 'high',
        },
        {
          name: 'academic_goal',
          type: 'categorical',
          source_dataset_name: 'Survey Data',
          source_dataset_id: 'ds_1',
          coverage_percentage: 95.0,
          missing_percentage: 5.0,
          usefulness: 'medium',
        },
      ],
      evidence_claim_count: 6,
      supported_claims_count: 5,
      guidance_message: 'Ready for segmentation with 1 connected dataset (1,200 empirical records) and 6 research evidence claims.',
      study_id: studyId,
    };
  },

  async runSegmentation(
    studyId: string,
    options?: { desired_clusters?: number; configuration?: any }
  ): Promise<{ run: SegmentationRun; segments: MarketSegment[] }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segmentation`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(options || {}),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Segmentation run failed');
      } catch (err) {
        // Fabricated "data_backed" segments would poison the research — fail visibly.
        lastKnownLive = false;
        throw err;
      }
    }

    const runId = `segrun_${Date.now()}`;
    const count = options?.desired_clusters || 3;
    const mockSegments: MarketSegment[] = [
      {
        id: `seg_${Date.now()}_1`,
        study_id: studyId,
        segmentation_run_id: runId,
        name: 'Budget-Conscious Students (৳350/mo)',
        cluster_label: 'cluster_0',
        description: 'Represents 45.0% of empirical respondents with strict spending limits under ৳400/month. Highly sensitive to subscription friction.',
        population_count: 540,
        population_percentage: 45.0,
        confidence_score: 0.92,
        status: 'data_backed',
        characteristics: {
          demographics: { age_range: [18, 22], median_age: 20, dominant_occupation: 'Undergraduate Student' },
          economics: { monthly_budget: { min: 250, median: 350, max: 500, currency: 'BDT' } },
          behavior: { study_hours_per_day: 4.5, technology_familiarity: 'Medium' },
          needs: ['Affordable micro-subscriptions', 'Offline mobile revision mode'],
        },
        variable_distributions: { monthly_budget: { min: 250, median: 350, max: 500, count: 540 } },
        evidence_citations: [
          { claim_id: 'clm_1', claim_text: 'Students prefer bKash micro-payments over monthly auto-debit.', category: 'pricing', status: 'supported', confidence: 0.88 },
        ],
        differentiation_summary: 'Differs by lower monthly spending tolerance and high prioritization of free/affordable core features.',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        id: `seg_${Date.now()}_2`,
        study_id: studyId,
        segmentation_run_id: runId,
        name: 'Exam-Driven Achievers (৳750/mo)',
        cluster_label: 'cluster_1',
        description: 'Represents 35.0% of students preparing for competitive admission tests with high urgency and willingness to invest in score improvement.',
        population_count: 420,
        population_percentage: 35.0,
        confidence_score: 0.88,
        status: 'data_backed',
        characteristics: {
          demographics: { age_range: [19, 23], median_age: 21, dominant_occupation: 'Admission Candidate' },
          economics: { monthly_budget: { min: 500, median: 750, max: 1200, currency: 'BDT' } },
          behavior: { study_hours_per_day: 7.2, technology_familiarity: 'High' },
          needs: ['Mock test analytics', 'Dynamic daily revision schedules'],
        },
        variable_distributions: { monthly_budget: { min: 500, median: 750, max: 1200, count: 420 } },
        evidence_citations: [
          { claim_id: 'clm_2', claim_text: 'Candidates are willing to pay a premium during the 90 days leading to admission exams.', category: 'behavior', status: 'supported', confidence: 0.90 },
        ],
        differentiation_summary: 'Differs by high daily study intensity (7+ hours) and elevated willingness to pay for proven exam score improvements.',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      {
        id: `seg_${Date.now()}_3`,
        study_id: studyId,
        segmentation_run_id: runId,
        name: 'Casual Self-Paced Learners (৳500/mo)',
        cluster_label: 'cluster_2',
        description: 'Represents 20.0% of users seeking general productivity support with moderate study frequency.',
        population_count: 240,
        population_percentage: 20.0,
        confidence_score: 0.82,
        status: 'data_backed',
        characteristics: {
          demographics: { age_range: [20, 25], median_age: 22, dominant_occupation: 'Graduate Student' },
          economics: { monthly_budget: { min: 350, median: 500, max: 800, currency: 'BDT' } },
          behavior: { study_hours_per_day: 3.0, technology_familiarity: 'Medium' },
          needs: ['Clean distraction-free interface', 'Cross-platform web access'],
        },
        variable_distributions: { monthly_budget: { min: 350, median: 500, max: 800, count: 240 } },
        evidence_citations: [],
        differentiation_summary: 'Differs by flexible study schedules and preference for simple checklist interfaces.',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ].slice(0, count);

    const mockRun: SegmentationRun = {
      id: runId,
      study_id: studyId,
      status: 'completed',
      method: 'hybrid_quantile_clustering',
      configuration: options?.configuration || {},
      dataset_versions: [
        { dataset_id: 'ds_1', name: 'Survey Data', content_hash: 'hash_abc123', row_count: 1200, file_type: 'csv' },
      ],
      evidence_snapshot: { claim_count: 6 },
      segment_count: mockSegments.length,
      started_at: new Date(Date.now() - 3000).toISOString(),
      completed_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
    };

    return { run: mockRun, segments: mockSegments };
  },

  async listSegmentationRuns(studyId: string): Promise<SegmentationRun[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segmentation/runs`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
      }
    }
    return [];
  },

  async getSegmentationRun(studyId: string, runId: string): Promise<SegmentationRun> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segmentation/runs/${runId}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
      }
    }
    throw new Error('Segmentation run not found');
  },

  async listStudySegments(studyId: string, options?: { run_id?: string; status?: string }): Promise<MarketSegment[]> {
    if (!this.isMockMode()) {
      try {
        const params = new URLSearchParams();
        if (options?.run_id) params.append('run_id', options.run_id);
        if (options?.status) params.append('status', options.status);
        const query = params.toString() ? `?${params.toString()}` : '';
        const res = await fetch(`${API_BASE}/studies/${studyId}/segments${query}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to load market segments');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    return [];
  },

  async getMarketSegments(studyId: string, options?: { run_id?: string; status?: string }): Promise<MarketSegment[]> {
    return this.listStudySegments(studyId, options);
  },

  async getStudySegments(studyId: string, options?: { run_id?: string; status?: string }): Promise<MarketSegment[]> {
    return this.listStudySegments(studyId, options);
  },

  async getSegmentDetail(studyId: string, segmentId: string): Promise<MarketSegment> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segments/${segmentId}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
      }
    }
    throw new Error('Segment not found');
  },

  async compareSegments(studyId: string, segmentIds: string[]): Promise<SegmentComparisonResult> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segments/compare`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ segment_ids: segmentIds }),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Segment comparison failed (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      study_id: studyId,
      compared_count: segmentIds.length,
      comparison_matrix: segmentIds.map((id, idx) => ({
        segment_id: id,
        name: idx === 0 ? 'Budget-Conscious Students' : 'Exam-Driven Achievers',
        cluster_label: `cluster_${idx}`,
        population_count: idx === 0 ? 540 : 420,
        population_percentage: idx === 0 ? 45.0 : 35.0,
        confidence_score: idx === 0 ? 0.92 : 0.88,
        status: 'data_backed',
        partition_variable: 'monthly_budget',
        headline_range: idx === 0 ? '250–500' : '500–1200',
        headline_median: idx === 0 ? 350 : 750,
        top_categories: idx === 0 ? { device: 'phone' } : { device: 'laptop' },
        observed_variables: ['monthly_budget', 'age', 'device'],
        evidence_citations_count: 1,
        differentiation: idx === 0 ? 'Lower spending tolerance and micro-subscription preference' : 'High daily urgency and readiness to pay for score improvement',
      })),
    };
  },

  async deleteSegmentationRun(studyId: string, runId: string): Promise<void> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/segmentation/runs/${runId}`, {
          method: 'DELETE',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return;
        }
        lastKnownLive = false;
        throw new Error(`Failed to delete segmentation run (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
  },

  // -------------------------------------------------------------------------
  // Part 5: Synthetic Personas & Persona Library
  // -------------------------------------------------------------------------

  async getStudyPersonas(
    studyId: string,
    options?: {
      segment_id?: string;
      status?: string;
      generation_run_id?: string;
      search?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<StudyPersonasResponse> {
    if (!this.isMockMode()) {
      try {
        const params = new URLSearchParams();
        if (options?.segment_id) params.append('segment_id', options.segment_id);
        if (options?.status) params.append('status', options.status);
        if (options?.generation_run_id) params.append('generation_run_id', options.generation_run_id);
        if (options?.search) params.append('search', options.search);
        if (options?.limit) params.append('limit', String(options.limit));
        if (options?.offset) params.append('offset', String(options.offset));

        const res = await fetch(`${API_BASE}/studies/${studyId}/personas?${params.toString()}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch study personas (HTTP ${res.status})`);
      } catch (err) {
        // Never substitute fabricated personas for a failed live read.
        lastKnownLive = false;
        throw err;
      }
    }

    // Default mock response
    return {
      personas: [
        {
          id: 'per_nusrat_01',
          study_id: studyId,
          segment_id: 'seg_1',
          segment_name: 'Night Shift Healthcare Workers',
          generation_run_id: 'pgen_mock_1',
          name: 'Nusrat Jahan',
          status: 'ready',
          version: 1,
          generation_model: 'qwen3.5-grounded',
          archetype: 'Night Shift Worker',
          tagline: 'The Steady Night Caregiver',
          country_code: 'BD',
          origin_country: 'Bangladesh',
          personality: {
            openness: 44,
            conscientiousness: 86,
            extroversion: 50,
            agreeableness: 76,
            neuroticism: 58,
          },
          detailed_attributes: {
            hobbies: 'watching Bangla dramas, tending balcony plants, and listening to health podcasts',
            origin_country: 'Bangladesh',
            commute_mode: 'rickshaw for local travel and occasional staff transport after late shifts',
            food_source: 'mostly home-cooked meals; hospital canteen or nearby stalls when shifts overrun; occasional delivery if it seems reliable',
            meal_timing: 'main meal before shift, light snack around 11 pm, tea near 3 am, breakfast after returning home',
            payment_method: 'bKash for most transactions, with cash as a backup',
            work_schedule: 'rotating night shifts, usually 8 pm to 8 am, 4 nights a week',
            workplace_setting: 'private hospital ward',
            activity_level: 'moderately active because she spends long hours on her feet',
            adaptability_level: 'moderate',
            anxiety_level: 'moderately high when plans change suddenly or services fail late at night',
            attention_focus: 'task-focused with strong awareness of timing and practical details',
            belief_system: 'practical, duty-centered, and moderately religious',
            communication_style: 'polite, concise, and direct under time pressure',
            community_engagement: 'keeps light ties with neighbors and relatives but has limited time for events',
            coping_strategies: 'tea breaks, prayer, short calls home, and sticking to checklists',
            core_motivators: 'doing her job well, protecting her income, and keeping household life manageable',
            cultural_affiliations: 'urban Bangladeshi middle-class culture',
            cultural_traditions: 'values family meals on off days, Eid gatherings, and deference to elders',
            daily_activities: 'patient care, charting, commuting, family check-ins, and recovering sleep',
            decision_style: 'deliberate and pragmatic',
            family_dynamics: 'supportive but time-constrained, with shared responsibilities at home',
            financial_attitude: 'careful spender who tracks small expenses closely',
            financial_profile: 'lower-middle to middle-income salaried household with tight monthly margins',
            general_risk: 'low to moderate',
            growth_mindset: 'willing to improve through structured training and practical feedback',
            household_structure: 'multigenerational family household',
            introversion_level: 'moderately introverted',
            language_preferences: 'Bangla first; comfortable with basic English at work',
            learning_style: 'learns best through demonstration and repeated use',
            life_priorities: 'family wellbeing, steady work, and enough rest to function',
            motivation_goals: 'maintain stability, reduce daily friction, and build a slightly better routine over time',
            personal_independence: 'self-reliant in everyday matters but consults family on major decisions',
            personal_values: 'stability, responsibility, and caring for family',
            planning_horizon: 'mostly week-to-week with monthly budgeting goals',
            religious_practices: 'observes daily prayers when schedule allows and follows major Islamic holidays',
            schedule_flexibility: 'low because emergency cases and rota changes can override personal plans',
            self_discipline: 'strong',
            sleep_schedule: 'fragmented daytime sleep after night duty',
            social_identity: 'a working woman balancing professional duty and family expectations',
            social_values: 'respect, modesty, reliability, and consideration for others',
            spiritual_outlook: 'finds comfort in faith, routine, and gratitude',
            tech_interest: 'functional rather than enthusiastic',
            technology_usage: 'heavy smartphone use for messaging, mobile payments, maps, and shift coordination',
            time_management: 'structured but often disrupted by urgent work demands',
            urban_living: 'accustomed to congestion and delays, values services that save time',
            value_risk: 'prefers proven options and avoids unnecessary experimentation',
            work_ethic: 'highly dependable and methodical',
          },
          demographics: {
            age: 31,
            occupation: 'Night Shift Worker (Staff Caregiver)',
            location: 'Dhaka, Bangladesh',
            education: 'Diploma in Nursing Science',
            income_or_budget: '৳450/mo',
          },
          bio: 'She works rotating overnight shifts at a private hospital and depends on routines to get through long, demanding nights. She usually brings food from home, but when emergencies stretch her shift, she wants a late-night option that is safe, predictable, and worth the money.',
          quote: 'When emergencies stretch my shift past 3 am, I need something predictable, safe, and worth the money.',
          goals: [
            'Maintain steady patient care routine without exhaustion',
            'Protect monthly household savings and budget margin',
            'Eliminate late-night friction when shift schedules overrun',
          ],
          needs: [
            'Predictable service availability during overnight hours (11 PM – 4 AM)',
            'Instant bKash payment verification with zero failed transaction delays',
            'Reliable emergency food and transit coordination',
          ],
          pain_points: [
            'Sudden cancellation of late-night services without warning',
            'Overpriced emergency food stalls with questionable hygiene',
            'Fragmented daytime sleep disrupted by unpredictable schedule changes',
          ],
          behaviors: [
            'Brings home-cooked meals for normal shifts; needs backup on overtime',
            'Uses smartphone heavily for shift rota updates and family check-ins',
            'Takes scheduled tea breaks near 3 AM to maintain focus',
          ],
          preferences: [
            'Simple, direct mobile interface with instant confirmations',
            'Verified safety ratings and transparent pricing',
          ],
          motivations: [
            'Ensuring patient safety and clinical excellence',
            'Securing household financial stability for her family',
          ],
          objections: [
            'Rejects services with hidden surge pricing during late hours',
            'Hesitant to try unverified new apps without peer reviews',
          ],
          commercial_profile: {
            monthly_budget_bdt: 450,
            budget_range: '৳300–৳650',
            price_sensitivity: 'High',
            payment_preference: 'bKash Mobile Wallet',
            willingness_to_pay: '৳350–৳550 / month',
          },
          technology_profile: {
            primary_devices: ['Android Smartphone (Samsung Galaxy)'],
            platforms: ['WhatsApp', 'bKash', 'Google Maps'],
            familiarity: 'Medium',
          },
          evidence_citations: [
            {
              claim_id: 'clm_night_01',
              claim_text: 'Rotating shift workers prioritize reliability and transparent mobile wallet checkout over novel experimental features.',
              category: 'behavior',
              confidence: 0.94,
            },
          ],
          dataset_refs: [
            { variable: 'monthly_budget', value: 450, source: 'Empirical Healthcare Worker Survey' },
            { variable: 'age', value: 31, source: 'Empirical Healthcare Worker Survey' },
          ],
          grounding_score: 0.96,
          confidence: 0.92,
          validation_warnings: [],
          is_synthetic: true,
          created_at: new Date().toISOString(),
        },
        {
          id: 'per_mock_1',
          study_id: studyId,
          segment_id: 'seg_1',
          segment_name: 'Budget-Conscious Students',
          generation_run_id: 'pgen_mock_1',
          name: 'Nadia Rahman',
          status: 'ready',
          version: 1,
          generation_model: 'qwen3.5-grounded',
          archetype: 'Budget-Conscious Student Planner',
          tagline: 'The Focused Academic Planner',
          country_code: 'BD',
          origin_country: 'Bangladesh',
          personality: {
            openness: 72,
            conscientiousness: 82,
            extroversion: 58,
            agreeableness: 75,
            neuroticism: 52,
          },
          detailed_attributes: {
            hobbies: 'reading business case studies, bullet journaling, and coffee with friends',
            commute_mode: 'campus bus and rickshaw',
            food_source: 'home food and campus cafeteria',
            meal_timing: 'breakfast at 8 am, lunch at 1:30 pm, dinner at 9 pm',
            payment_method: 'bKash and student debit card',
            work_schedule: 'full-time undergraduate classes and exam prep',
            communication_style: 'polite, curious, and collaborative',
            work_ethic: 'highly dedicated and organized',
          },
          demographics: {
            age: 21,
            occupation: 'Undergraduate Student (BBA)',
            location: 'Dhaka, Bangladesh',
            education: "Bachelor's 3rd Year",
            income_or_budget: '৳350/mo',
          },
          bio: 'Nadia is a 21-year-old marketing undergraduate at Dhaka University who manages a tight student budget and prioritizes affordable digital study aids.',
          quote: 'I need an intelligent tool that keeps my exam milestones on track without costing more than ৳350/month.',
          goals: [
            'Maintain a 3.7+ CGPA across midterm exams',
            'Synchronize study schedules across group assignments and peer tutoring',
            'Eliminate exam crunch panic through daily micro-milestones',
          ],
          needs: [
            'Micro-billing support for bKash / Nagad mobile wallet',
            'Lightweight offline mobile checklist sync',
            'Automated revision reminders 3 days before exam dates',
          ],
          pain_points: [
            'Expensive international SaaS subscriptions requiring dual-currency credit cards',
            'Fragmented study materials scattered across Messenger groups and PDF drives',
            'Inability to gauge remaining revision time vs total syllabus volume',
          ],
          behaviors: [
            'Studies ~4.5 hours daily with peak concentration between 9 PM and midnight',
            'Checks phone for schedule notifications during transit',
            'Shares study timetables with two study partners',
          ],
          preferences: [
            'Dark mode UI with high contrast readability',
            'Visual milestone progress bars over complex text tables',
          ],
          motivations: [
            'Securing a corporate internship through strong academic standing',
            'Minimizing stress and late-night cramming',
          ],
          objections: [
            'Skeptical of auto-debit renewals that are difficult to cancel',
            'Will abandon tools that lag on mobile data connections',
          ],
          commercial_profile: {
            monthly_budget_bdt: 350,
            budget_range: '৳250–৳500',
            price_sensitivity: 'High',
            payment_preference: 'bKash / Nagad Mobile Wallet',
            willingness_to_pay: '৳250–৳400 / month',
          },
          technology_profile: {
            primary_devices: ['Android Smartphone (Samsung A15)', 'Windows Laptop'],
            platforms: ['WhatsApp', 'Messenger', 'Google Drive'],
            familiarity: 'High',
          },
          evidence_citations: [
            {
              claim_id: 'clm_1',
              claim_text: 'Student segment exhibits high willingness to pay when capped below ৳400/month with local wallet billing.',
              category: 'pricing',
              confidence: 0.92,
            },
          ],
          dataset_refs: [
            { variable: 'monthly_budget', value: 350, source: 'Empirical Segment Distribution' },
            { variable: 'age', value: 21, source: 'Empirical Segment Distribution' },
          ],
          grounding_score: 0.94,
          confidence: 0.90,
          validation_warnings: [],
          is_synthetic: true,
          created_at: new Date().toISOString(),
        },
        {
          id: 'per_mock_2',
          study_id: studyId,
          segment_id: 'seg_2',
          segment_name: 'Exam-Driven Achievers',
          generation_run_id: 'pgen_mock_1',
          name: 'Tanvir Ahmed',
          status: 'ready',
          version: 1,
          generation_model: 'qwen3.5-grounded',
          archetype: 'High-Urgency Exam Candidate',
          demographics: {
            age: 23,
            occupation: 'BCS / Job Candidate',
            location: 'Chittagong, Bangladesh',
            education: 'Master Candidate',
            income_or_budget: '৳750/mo',
          },
          bio: 'Tanvir is a 23-year-old graduate preparing for competitive exams who is willing to pay premium rates for verified question banks and adaptive diagnostic feedback.',
          quote: 'I am ready to pay if the platform gives me clear diagnostic insights on where my syllabus weaknesses are.',
          goals: [
            'Rank in top 5% of BCS preliminary candidates',
            'Master full syllabus coverage with zero gaps',
          ],
          needs: [
            'Adaptive question banks and error log analysis',
            'Mock exam simulations with rank comparisons',
          ],
          pain_points: [
            'Generic practice books lacking explanatory answer keys',
            'No feedback on which syllabus subjects require extra focus',
          ],
          behaviors: [
            'Studies 7+ hours daily in structured 90-minute blocks',
            'Tracks daily question solve velocity',
          ],
          preferences: [
            'Detailed analytics dashboard with weak-topic drilldowns',
          ],
          motivations: [
            'Career stability through civil service admission',
          ],
          objections: [
            'Requires verified past paper authenticity before subscribing',
          ],
          commercial_profile: {
            monthly_budget_bdt: 750,
            budget_range: '৳500–৳1200',
            price_sensitivity: 'Moderate',
            payment_preference: 'bKash / Credit Card',
            willingness_to_pay: '৳600–৳1000 / month',
          },
          technology_profile: {
            primary_devices: ['Android Tablet', 'Windows Laptop'],
            platforms: ['Telegram Study Channels', 'Google Drive'],
            familiarity: 'High',
          },
          evidence_citations: [
            {
              claim_id: 'clm_2',
              claim_text: 'Aspirants demonstrate 2.5x higher WTP for real-time diagnostic error tracking and mock exam percentile scoring.',
              category: 'willingness_to_pay',
              confidence: 0.89,
            },
          ],
          dataset_refs: [
            { variable: 'monthly_budget', value: 750, source: 'Empirical Segment Distribution' },
          ],
          grounding_score: 0.91,
          confidence: 0.88,
          validation_warnings: [],
          is_synthetic: true,
          created_at: new Date().toISOString(),
        },
        {
          id: 'per_mock_3',
          study_id: studyId,
          segment_id: 'seg_1',
          segment_name: 'Tech-Forward Professionals',
          generation_run_id: 'pgen_mock_1',
          name: 'Sarah Chen',
          status: 'ready',
          version: 1,
          generation_model: 'qwen3.5-grounded',
          archetype: 'Senior Product Manager & Early Adopter',
          demographics: {
            age: 29,
            occupation: 'Senior Product Manager',
            location: 'Dhaka (Gulshan), Bangladesh',
            education: 'MBA',
            income_or_budget: '৳2500/mo',
          },
          bio: 'Sarah is an experienced product leader focused on rapid user research and AI validation tools.',
          quote: 'I need high-signal behavioral evidence before investing engineering bandwidth.',
          goals: [
            'Shorten validation cycles by 60%',
            'Test pricing elasticity accurately',
          ],
          needs: [
            'Empirical citation tracking',
            'Automated interview transcripts',
          ],
          pain_points: [
            'Superficial AI hallucinated personas',
          ],
          behaviors: [
            'Daily dashboard user',
            'Relies heavily on CSV data exports',
          ],
          preferences: [
            'Clean research telemetry and visual charts',
          ],
          motivations: [
            'Building validated high-impact products',
          ],
          objections: [
            'Unverified grounding claims',
          ],
          commercial_profile: {
            monthly_budget_bdt: 2500,
            price_sensitivity: 'Low',
            payment_preference: 'Corporate Credit Card',
            willingness_to_pay: '৳2000–৳3500 / month',
          },
          technology_profile: {
            primary_devices: ['MacBook Pro', 'iPhone 15 Pro'],
            platforms: ['Slack', 'Linear', 'Notion'],
            familiarity: 'High',
          },
          evidence_citations: [
            {
              claim_id: 'clm_3',
              claim_text: 'Product leaders prioritize evidence-backed synthetic interviews over manual recruiting.',
              category: 'demand_validation',
              confidence: 0.95,
            },
          ],
          dataset_refs: [
            { variable: 'monthly_budget', value: 2500, source: 'Empirical Segment Distribution' },
          ],
          grounding_score: 0.96,
          confidence: 0.92,
          validation_warnings: [],
          is_synthetic: true,
          created_at: new Date().toISOString(),
        },
      ],
      total: 3,
      represented_segments: 2,
      average_grounding_score: 0.94,
    };
  },

  async getStudyPersonaDetail(studyId: string, personaId: string): Promise<SyntheticPersona> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/personas/${personaId}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch persona detail (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const list = await this.getStudyPersonas(studyId);
    const found = list.personas.find((p) => p.id === personaId);
    if (found) return found;
    throw new Error('Persona not found');
  },

  /** Poll an async generation job until it terminates. Returns job.result.
   * Job-level failures throw an Error with `isJobFailure = true` so callers
   * can distinguish "the backend honestly reported failure" from "the
   * network died". Transient poll errors are tolerated (the job keeps
   * running server-side); only a 404 — genuine job loss — fails fast. */
  jobStorageKey(studyId: string, kind: 'report' | 'batch' | 'personas'): string {
    return `bebshax_job_${JSON.stringify([this.getStoredUser()?.id ?? 'anonymous', kind, studyId])}`;
  },

  getPendingJobHandle(studyId: string, kind: 'report' | 'batch' | 'personas'): string | null {
    const value = localStorage.getItem(this.jobStorageKey(studyId, kind));
    return value && /^[A-Za-z0-9_-]{1,128}$/.test(value) ? value : null;
  },

  rememberJobHandle(studyId: string, kind: 'report' | 'batch' | 'personas', value: unknown): string {
    if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value)) throw new Error('Invalid accepted job handle');
    localStorage.setItem(this.jobStorageKey(studyId, kind), value);
    return value;
  },

  forgetJobHandle(studyId: string, kind: 'report' | 'batch' | 'personas'): void {
    localStorage.removeItem(this.jobStorageKey(studyId, kind));
  },

  async resumeStudyReport(studyId: string, signal?: AbortSignal): Promise<StudyReport> {
    const markTiming = beginOperationTiming();
    const jobId = this.getPendingJobHandle(studyId, 'report');
    if (!jobId) throw new Error('No pending report job');
    const report = await this.pollGenerationJob<StudyReport>(
      `${API_BASE}/studies/${studyId}/reports/generate/jobs/${jobId}`, { signal, timeoutMs: 600000, decode: decodeStudyReport },
    );
    markTiming('canonical-response');
    if (!report.id) throw new Error('Completed report has no saved identifier');
    const saved = await this.getStudyReport(studyId, report.id);
    signal?.throwIfAborted();
    if (saved.id !== report.id || saved.version !== report.version) throw new Error('Saved report version does not match completion');
    markTiming('saved-completion');
    invalidateStudiesCache();
    // Publishing the report onto the study (findings, status) advanced its
    // revision server-side; adopt it so the next queued save targets the
    // current row instead of bouncing off a 412 first (live 2026-09-14).
    if (saved.metrics?.study_projection_applied === true) {
      adoptStudyRevision(studyId, saved.metrics.published_study_revision);
    }
    if (this.getPendingJobHandle(studyId, 'report') === jobId) this.forgetJobHandle(studyId, 'report');
    return saved;
  },

  async pollGenerationJob<T>(pollUrl: string, opts?: {
    intervalMs?: number; timeoutMs?: number; idleTimeoutMs?: number; signal?: AbortSignal; decode?: (value: unknown) => T;
  }): Promise<T> {
    const base = new URL(API_BASE, window.location.origin);
    const target = new URL(pollUrl, base);
    if (target.origin !== base.origin || !target.pathname.startsWith(`${base.pathname}/`)) throw new Error('Invalid job polling destination');
    const job = await pollSerial(async (signal) => {
      const response = await fetch(pollUrl, { headers: this.getAuthHeaders(), signal });
      if (!response.ok) throw await apiErrorFrom(response, 'Job updates unavailable');
      const value: unknown = await response.json();
      if (!isRecord(value) || typeof value.status !== 'string') throw Object.assign(new Error('Invalid job status response'), { isJobFailure: true });
      return value;
    }, {
      ...opts,
      progress: (value) => JSON.stringify([value.status, value.completed_count, value.failed_count, value.progress]),
      complete: (value) => {
        if (['completed', 'succeeded', 'completed_with_warnings'].includes(value.status as string)) return true;
        if (['pending', 'queued', 'running', 'cancelling'].includes(value.status as string)) return false;
        throw Object.assign(new Error(typeof value.error === 'string' ? value.error : `Job ended with status ${value.status}`), { isJobFailure: true });
      },
    });
    if (opts?.decode) return opts.decode(job.result);
    if (!isRecord(job.result) && !Array.isArray(job.result)) throw Object.assign(new Error('Invalid completed job result'), { isJobFailure: true });
    return job.result as T;
  },

  async generateSyntheticPersonas(
    studyId: string,
    payload: GeneratePersonasPayload,
    signal?: AbortSignal
  ): Promise<{ run: PersonaGenerationRun; personas: SyntheticPersona[] }> {
    if (!this.isMockMode()) {
      const resume = async () => {
        const jobId = this.getPendingJobHandle(studyId, 'personas');
        const result = await this.pollGenerationJob<{ run: PersonaGenerationRun; personas: SyntheticPersona[] }>(
          `${API_BASE}/studies/${studyId}/personas/generate/jobs/${jobId}`, { signal, decode: (value) => {
            if (!isRecord(value) || !isRecord(value.run) || typeof value.run.id !== 'string' || !Array.isArray(value.personas)) throw new Error('Invalid persona generation result');
            return value as unknown as { run: PersonaGenerationRun; personas: SyntheticPersona[] };
          } },
        );
        this.forgetJobHandle(studyId, 'personas');
        invalidateStudiesCache();
        return result;
      };
      if (this.getPendingJobHandle(studyId, 'personas')) return resume();
      try {
        // Job endpoint first: generation runs for minutes at free-tier
        // latency — the POST returns 202 immediately and we poll.
        const jobRes = await fetch(`${API_BASE}/studies/${studyId}/personas/generate/jobs`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
          signal,
        });
        if (jobRes.status === 202) {
          const { job_id } = await jobRes.json();
          this.rememberJobHandle(studyId, 'personas', job_id);
          lastKnownLive = true;
          try {
            return await resume();
          } catch (e) {
            // An honest backend-reported failure (e.g. "run segmentation
            // first") must reach the user — never be swallowed into a
            // fabricated "completed" mock run. The backend responded fine,
            // so live status is untouched.
            if ((e as { isJobFailure?: boolean })?.isJobFailure) throw e;
            lastKnownLive = false;
            throw e;
          }
        }
        // Older backend without job endpoints — fall back to the sync call.
        if (jobRes.status === 404 || jobRes.status === 405) {
          const res = await fetch(`${API_BASE}/studies/${studyId}/personas/generate`, {
            method: 'POST',
            headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(payload),
          });
          if (res.ok) {
            lastKnownLive = true;
            return await res.json();
          }
          lastKnownLive = false;
          throw await apiErrorFrom(res, 'Persona generation failed');
        }
        lastKnownLive = false;
        throw await apiErrorFrom(jobRes, 'Persona generation failed');
      } catch (e) {
        // Live mode never degrades into a fabricated "completed" run —
        // honest job failures and connectivity loss both surface.
        if (!(e as { isJobFailure?: boolean })?.isJobFailure) lastKnownLive = false;
        throw e;
      }
    }

    const list = await this.getStudyPersonas(studyId);
    return {
      run: {
        id: `pgen_${Date.now()}`,
        study_id: studyId,
        status: 'completed',
        configuration: {
          personas_per_segment: payload.personas_per_segment || 2,
          target_count: payload.target_count || 4,
          distribution_strategy: payload.distribution_strategy || 'population_weighted',
        },
        target_count: payload.target_count || 4,
        generated_count: list.personas.length,
        valid_count: list.personas.length,
        warning_count: 0,
        dataset_versions: [{ dataset_id: 'ds_1', name: 'Empirical Study Dataset', content_hash: 'dshash_123', row_count: 1200 }],
        evidence_snapshot: { claim_count: 6, top_claims: [{ id: 'clm_1', claim_text: 'Verified market claims' }] },
        started_at: new Date().toISOString(),
        completed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      },
      personas: list.personas,
    };
  },

  async regenerateStudyPersona(studyId: string, personaId: string): Promise<SyntheticPersona> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/personas/${personaId}/regenerate`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Persona regeneration failed');
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    const persona = await this.getStudyPersonaDetail(studyId, personaId);
    return {
      ...persona,
      version: persona.version + 1,
      name: `${persona.name} (v${persona.version + 1})`,
      updated_at: new Date().toISOString(),
    };
  },

  async listStudyPersonaRuns(studyId: string): Promise<{ runs: PersonaGenerationRun[] }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/persona-runs`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch persona runs (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    return {
      runs: [
        {
          id: 'pgen_mock_1',
          study_id: studyId,
          status: 'completed',
          configuration: {
            personas_per_segment: 2,
            target_count: 4,
            distribution_strategy: 'population_weighted',
          },
          target_count: 4,
          generated_count: 4,
          valid_count: 4,
          warning_count: 0,
          dataset_versions: [{ dataset_id: 'ds_1', name: 'Empirical Study Dataset', content_hash: 'dshash_123', row_count: 1200 }],
          evidence_snapshot: { claim_count: 6, top_claims: [{ id: 'clm_1', claim_text: 'Verified market claims' }] },
          started_at: new Date().toISOString(),
          completed_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
        },
      ],
    };
  },

  /** Remove a persona from the study panel. The server archives it (its
   * interviews stay attributable) and returns the refreshed derived state plus
   * the new study revision, which callers must adopt before their next PATCH. */
  async archiveStudyPersona(
    studyId: string,
    personaId: string,
    signal?: AbortSignal,
  ): Promise<{ study_id: string; study_revision: number; persona_count: number; persona_ids: string[]; personas_data: unknown[] }> {
    if (this.isMockMode()) throw new Error('Backend connection required to remove a persona');
    await waitForStudyWrites(studyId);
    const res = await fetch(`${API_BASE}/studies/${studyId}/personas/${encodeURIComponent(personaId)}`, {
      method: 'DELETE',
      headers: this.getAuthHeaders(),
      signal,
    });
    if (!res.ok) throw await apiErrorFrom(res, 'Removing the persona failed');
    lastKnownLive = true;
    const body = await res.json();
    adoptStudyRevision(studyId, body.study_revision);
    invalidateStudiesCache();
    return body;
  },

  async deleteStudyPersonaRun(studyId: string, runId: string): Promise<void> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/persona-runs/${runId}`, {
          method: 'DELETE',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return;
        }
        lastKnownLive = false;
        throw new Error(`Failed to delete persona run (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
  },

  // -------------------------------------------------------------
  // Part 6: Adaptive Persona Interviews
  // -------------------------------------------------------------
  async startPersonaInterview(
    studyId: string,
    personaId: string,
    payload: {
      objective: string;
      custom_objective?: string;
      length_tier?: string;
      generation_run_id?: string;
    }
  ): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/personas/${personaId}/interviews`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to start interview');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    return {
      id: `int_${Date.now().toString(36)}`,
      study_id: studyId,
      persona_id: personaId,
      persona_version: 1,
      objective: payload.objective,
      custom_objective: payload.custom_objective,
      interview_type: 'adaptive_persona',
      length_tier: payload.length_tier || 'standard',
      max_turns: payload.length_tier === 'short' ? 6 : payload.length_tier === 'deep' ? 24 : 14,
      status: 'active',
      topics_explored: {},
      question_count: 0,
      turn_count: 0,
      created_at: new Date().toISOString(),
    };
  },

  async listStudyInterviews(
    studyId: string,
    params?: { status?: string; objective?: string; search?: string; limit?: number; offset?: number }
  ): Promise<{ interviews: any[]; total: number }> {
    if (!this.isMockMode()) {
      try {
        const q = new URLSearchParams();
        if (params?.status && params.status !== 'all') q.set('status', params.status);
        if (params?.objective && params.objective !== 'all') q.set('objective', params.objective);
        if (params?.search) q.set('search', params.search);
        if (params?.limit) q.set('limit', String(params.limit));
        if (params?.offset) q.set('offset', String(params.offset));

        const query = q.toString();
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews${query ? `?${query}` : ''}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to load study interviews');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    // Mock mode: surface the study fixture's pre-generated interviews.
    await loadMocks();
    const study = this.getStoredUserStudies().find((s) => s.id === studyId);
    let items = (study?.interviews || []).map((iv) => ({
      id: iv.id,
      study_id: studyId,
      persona_id: iv.persona_id,
      persona_version: 1,
      objective: iv.objective || 'problem_discovery',
      interview_type: 'adaptive',
      length_tier: 'standard' as const,
      max_turns: 12,
      status: (iv.status === 'in_progress' ? 'active' : iv.status === 'pending' ? 'paused' : 'completed') as 'active' | 'completed' | 'paused',
      topics_explored:
        iv.status === 'completed'
          ? { discovery: 'explored', pricing: 'explored', objections: 'explored' }
          : {},
      question_count: iv.turns_count,
      turn_count: iv.turns_count,
      summary: iv.key_takeaway,
      persona_name: iv.persona_name,
      persona_occupation: iv.persona_archetype,
      created_at: study?.created_at || new Date().toISOString(),
      updated_at: study?.updated_at,
    }));
    if (params?.status && params.status !== 'all') {
      items = items.filter((iv) => iv.status === params.status);
    }
    if (params?.objective && params.objective !== 'all') {
      items = items.filter((iv) => iv.objective === params.objective);
    }
    if (params?.search) {
      const q = params.search.toLowerCase();
      items = items.filter(
        (iv) =>
          iv.persona_name?.toLowerCase().includes(q) ||
          iv.summary?.toLowerCase().includes(q) ||
          iv.objective.toLowerCase().includes(q),
      );
    }
    return { interviews: items, total: items.length };
  },

  async getStudyInterviewMetrics(studyId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/metrics`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch interview metrics (HTTP ${res.status})`);
      } catch (err) {
        // Fabricated zero-metrics would misreport real work — fail visibly.
        lastKnownLive = false;
        throw err;
      }
    }
    // Mock mode: derive metrics from the study fixture's interviews.
    await loadMocks();
    const study = this.getStoredUserStudies().find((s) => s.id === studyId);
    const ivs = study?.interviews || [];
    return {
      total_interviews: ivs.length,
      active_interviews: ivs.filter((iv) => iv.status === 'in_progress').length,
      completed_interviews: ivs.filter((iv) => iv.status === 'completed').length,
      total_insights_generated: ivs.reduce((sum, iv) => sum + (iv.turns_count || 0), 0),
    };
  },

  async getStudyInterviewDetail(studyId: string, interviewId: string, signal?: AbortSignal): Promise<InterviewDetailResponse> {
    signal?.throwIfAborted();
    signal = sessionSignal(signal, TIMEOUT_MS.CRUD_HEAVY);
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/${interviewId}`, {
          headers: this.getAuthHeaders(),
          signal,
        });
        if (!res.ok) throw await apiErrorFrom(res, 'Failed to load interview');
        const detail = decodeInterviewDetail(await res.json(), studyId, interviewId);
        signal?.throwIfAborted();
        lastKnownLive = true;
        return detail;
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    throw new Error('Interview not found');
  },

  async sendInterviewMessage(
    studyId: string,
    interviewId: string,
    payload: { content: string },
    signal?: AbortSignal
  ): Promise<SendInterviewMessageResponse> {
    signal?.throwIfAborted();
    signal = sessionSignal(signal, TIMEOUT_MS.LLM);
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/interviews/${interviewId}/messages`,
          {
            method: 'POST',
            headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(payload),
            signal,
          }
        );
        if (res.ok) {
          const reply = decodeInterviewReply(await res.json());
          signal?.throwIfAborted();
          lastKnownLive = true;
          return reply;
        }
        throw await apiErrorFrom(res, 'Failed to send message');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for live persona interview');
  },

  /** SSE variant: onDelta fires per text chunk; resolves with the canonical
   * done payload (same shape as sendInterviewMessage). Throws a typed error
   * (err.kind from the backend taxonomy) on failure. */
  async sendInterviewMessageStream(
    studyId: string,
    interviewId: string,
    content: string,
    onDelta: (text: string) => void,
    signal?: AbortSignal
  ): Promise<SendInterviewMessageResponse> {
    if (this.isMockMode()) throw new Error('Backend required for live persona interview');
    signal = sessionSignal(signal, TIMEOUT_MS.LLM);
    signal?.throwIfAborted();

    const res = await fetch(
      `${API_BASE}/studies/${studyId}/interviews/${interviewId}/messages/stream`,
      {
        method: 'POST',
        headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ content }),
        signal,
      }
    );
    if (!res.ok || !res.body) {
      signal?.throwIfAborted();
      lastKnownLive = false;
      throw await apiErrorFrom(res, 'Stream failed');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let buffer = '';
    let completedReply: SendInterviewMessageResponse | null = null;
    let cancelled = false;
    const cancelReader = () => {
      if (cancelled) return;
      cancelled = true;
      void reader.cancel().catch(() => {});
    };
    signal?.addEventListener('abort', cancelReader, { once: true });

    const handleFrame = (frame: string) => {
      signal?.throwIfAborted();
      if (frame.length > MAX_INTERVIEW_FRAME_LENGTH) throw new Error('Interview frame exceeds protocol limit');
      const lines = frame.split(/\r?\n/);
      const eventLine = lines.find((l) => l.startsWith('event:'));
      // Per the SSE spec, multiple data: lines concatenate with newlines.
      const dataPayload = lines
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).replace(/^ /, ''))
        .join('\n');
      if (!eventLine || !dataPayload) return;
      const event = eventLine.slice(6).trim();
      const data = decodeInterviewFrame(dataPayload);
      if (event === 'delta') {
        const text = decodeInterviewDelta(data);
        if (text) onDelta(text);
      }
      else if (event === 'done') {
        completedReply = decodeInterviewReply(data);
      }
      else if (event === 'error') {
        // Stream errors carry the same envelope fields as HTTP errors plus the
        // backend failure `kind`; keep both so the workspace can classify.
        const e = toApiErrorInstance(parseApiError(data, 502, 'interview turn failed')) as ApiErrorLike & { kind?: string };
        e.kind = isRecord(data) && typeof data.kind === 'string' ? data.kind : undefined;
        throw e;
      }
    };

    try {
      signal?.throwIfAborted();
      lastKnownLive = true;
      for (;;) {
        const { value, done: eof } = await reader.read();
        signal?.throwIfAborted();
        buffer += eof ? decoder.decode() : decoder.decode(value, { stream: true });
        let match: RegExpExecArray | null;
        const boundary = /\r?\n\r?\n/;
        while ((match = boundary.exec(buffer)) !== null) {
          const frame = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          handleFrame(frame);
          if (completedReply) return completedReply;
        }
        if (buffer.length > MAX_INTERVIEW_FRAME_LENGTH) throw new Error('Interview frame exceeds protocol limit');
        if (eof) break;
      }
      if (buffer.trim()) handleFrame(buffer);
      if (completedReply) return completedReply;
      throw new Error('Stream ended without a final reply');
    } finally {
      signal?.removeEventListener('abort', cancelReader);
      cancelReader();
      reader.releaseLock();
    }
  },

  async completeStudyInterview(studyId: string, interviewId: string, signal?: AbortSignal): Promise<CompleteInterviewResponse> {
    signal?.throwIfAborted();
    signal = sessionSignal(signal, TIMEOUT_MS.LLM);
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/interviews/${interviewId}/complete`,
          {
            method: 'POST',
            headers: this.getAuthHeaders(),
            signal,
          }
        );
        if (res.ok) {
          const synthesis = decodeInterviewSynthesis(await res.json());
          signal?.throwIfAborted();
          lastKnownLive = true;
          return synthesis;
        }
        throw await apiErrorFrom(res, 'Failed to complete interview');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for completion synthesis');
  },

  async getStudyInterviewInsights(studyId: string, interviewId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/interviews/${interviewId}/insights`,
          {
            headers: this.getAuthHeaders(),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
      }
    }
    return { insights: [] };
  },

  // ---------------------------------------------------------------------------
  // Part 7: Behavioral Testing & Simulation
  // ---------------------------------------------------------------------------

  async createBehavioralTest(studyId: string, payload: any): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to create behavioral test');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for creating behavioral tests');
  },

  async getBehavioralTests(studyId: string, q?: string, testType?: string, statusFilter?: string): Promise<any[]> {
    if (!this.isMockMode()) {
      try {
        const params = new URLSearchParams();
        if (q) params.set('q', q);
        if (testType && testType !== 'all') params.set('test_type', testType);
        if (statusFilter && statusFilter !== 'all') params.set('status', statusFilter);

        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests?${params.toString()}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Behavioral tests unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    return [];
  },

  async getBehavioralMetrics(studyId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/metrics`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch behavioral metrics (HTTP ${res.status})`);
      } catch (err) {
        // The 52% buy-likelihood below is a mock fixture — never serve it live.
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      study_id: studyId,
      total_tests: 0,
      total_runs: 0,
      completed_runs: 0,
      total_personas_simulated: 0,
      average_buy_likelihood: 0.52,
      average_buy_likelihood_percentage: 52,
    };
  },

  async getBehavioralTestDetail(studyId: string, testId: string, signal?: AbortSignal): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}`, {
          headers: this.getAuthHeaders(),
          signal,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to fetch test detail');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for test detail');
  },

  async updateBehavioralTest(studyId: string, testId: string, payload: any): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}`, {
          method: 'PUT',
          headers: this.getAuthHeaders(),
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to update test');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for updating test');
  },

  async deleteBehavioralTest(studyId: string, testId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}`, {
          method: 'DELETE',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    return { success: true };
  },

  async triggerBehavioralTestRun(studyId: string, testId: string, payload: any, signal?: AbortSignal): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}/runs`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          body: JSON.stringify(payload),
          signal,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to start simulation run');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for running simulation');
  },

  async getBehavioralTestRuns(studyId: string, testId: string, signal?: AbortSignal): Promise<any[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}/runs`, {
          headers: this.getAuthHeaders(),
          signal,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Simulation runs unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    return [];
  },

  async getBehavioralRunStatus(studyId: string, runId: string, signal?: AbortSignal): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/runs/${runId}`, {
          headers: this.getAuthHeaders(),
          signal,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to fetch run status');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for run status');
  },

  async getBehavioralRunResults(studyId: string, runId: string, signal?: AbortSignal): Promise<any> {
    return this.getBehavioralRunStatus(studyId, runId, signal);
  },

  async retryFailedBehavioralRun(studyId: string, runId: string, signal?: AbortSignal): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/runs/${runId}/retry-failed`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          signal,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Failed to retry failed simulations');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for retrying simulations');
  },

  async compareBehavioralRuns(studyId: string, runIds: string[]): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/behavioral-tests/compare?run_ids=${encodeURIComponent(runIds.join(','))}`,
          {
            headers: this.getAuthHeaders(),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        throw await apiErrorFrom(res, 'Run comparison unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    return { study_id: studyId, compared_run_count: 0, runs: [] };
  },

  // ============================================================================
  // Study Reports, Script Questions & Multi-Turn Interview Methods
  // ============================================================================

  async getStudyReports(studyId: string): Promise<StudyReport[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/reports`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          const reports: unknown = await res.json();
          if (!Array.isArray(reports)) throw new Error('Invalid report list response');
          return reports.map(decodeStudyReport);
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Reports unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    // Mock mode: a study fixture can carry its own pre-built report (demo study).
    await loadMocks();
    const study = this.getStoredUserStudies().find((s) => s.id === studyId);
    if (study?.report) {
      return [{
        ...study.report,
        id: study.report.id || `rep_${studyId}`,
        study_id: studyId,
        title: study.report.title || study.title,
        created_at: study.report.created_at || study.updated_at,
      }];
    }
    return [];
  },

  async getLatestStudyReport(studyId: string): Promise<StudyReport | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/reports/latest`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        if (res.status === 404) return null;
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Latest report unavailable');
      } catch (error) {
        lastKnownLive = false;
        throw error;
      }
    }
    return null;
  },

  async getStudyReport(studyId: string, reportId: string): Promise<StudyReport> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/reports/${reportId}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          return decodeStudyReport(await res.json());
        }
        throw await apiErrorFrom(res, 'Failed to fetch report');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Report not found');
  },

  async generateStudyReport(studyId: string, title?: string, signal?: AbortSignal): Promise<StudyReport> {
    if (!this.isMockMode()) {
      if (this.getPendingJobHandle(studyId, 'report')) return this.resumeStudyReport(studyId, signal);
      await waitForStudyWrites(studyId);
      try {
        // Job endpoint first: synthesis reads every interview + runs LLM
        // calls (150s budget) — 202 + poll instead of one long request.
        const jobRes = await fetch(`${API_BASE}/studies/${studyId}/reports/generate/jobs`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ title }),
          signal,
        });
        if (jobRes.status === 202) {
          const { job_id } = await jobRes.json();
          this.rememberJobHandle(studyId, 'report', job_id);
          lastKnownLive = true;
          return await this.resumeStudyReport(studyId, signal);
        }
        // Older backend without job endpoints — fall back to the sync call.
        if (jobRes.status === 404 || jobRes.status === 405) {
          const res = await fetch(`${API_BASE}/studies/${studyId}/reports/generate`, {
            method: 'POST',
            headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ title }),
            // Report synthesis reads every interview + runs LLM synthesis;
            // 120s aborted real runs mid-generation.
            signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
          });
          if (res.ok) {
            lastKnownLive = true;
            return await res.json();
          }
          throw await apiErrorFrom(res, 'Report generation failed');
        }
        throw await apiErrorFrom(jobRes, 'Report generation failed');
      } catch (e) {
        // Honest job failures mean the backend responded fine — only genuine
        // connectivity loss should mark it dead.
        if (!(e as { isJobFailure?: boolean })?.isJobFailure) lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend connection required for report generation');
  },

  async generateStudyScriptQuestions(
    studyId: string,
    prompt?: string,
    count = 5
  ): Promise<{
    study_id: string;
    questions: string[];
    count: number;
    /** 'llm' = written for this study; 'fallback_static' = canned starter questions. */
    source?: 'llm' | 'fallback_static';
    fallback_reason?: string | null;
    /** Revision after the server persisted the script (already saved; do not re-send). */
    study_revision?: number | null;
  }> {
    if (!this.isMockMode()) {
      try {
        // The server persists the script itself; a queued client save must not
        // race its revision bump.
        await waitForStudyWrites(studyId);
        const res = await fetch(`${API_BASE}/studies/${studyId}/script/generate`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ prompt, question_count: count }),
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          const result = await res.json();
          if (Array.isArray(result?.questions)) {
            invalidateStudiesCache();
            adoptStudyRevision(studyId, result.study_revision, { script_questions: result.questions });
          }
          return result;
        }
        lastKnownLive = false;
        throw await apiErrorFrom(res, 'Script generation failed');
      } catch (err) {
        // Canned questions must never impersonate LLM output in live mode.
        lastKnownLive = false;
        throw err;
      }
    }
    return {
      study_id: studyId,
      questions: [
        `How do you currently solve problems related to ${prompt || 'this product area'}?`,
        'What other tools or alternatives have you evaluated, and where do they fail?',
        'What would be the most critical feature to make this an indispensable daily solution?',
        'What is your willingness to pay and pricing expectation for this tool?',
        'What is your primary concern before committing to this workflow?',
      ],
      count: 5,
      // Mock mode is sample data end to end; label it as such rather than as LLM output.
      source: 'llm',
    };
  },

  async runBatchStudyInterviews(
    studyId: string,
    personaIds?: string[],
    questions?: string[],
    signal?: AbortSignal
  ): Promise<any> {
    if (!this.isMockMode()) {
      const pending = this.getPendingJobHandle(studyId, 'batch');
      if (pending) return this.getBatchRunStatus(studyId, pending, signal);
      await waitForStudyWrites(studyId);
      try {
        // Starts a background job (202); progress comes from getBatchRunStatus.
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/batch-run`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ persona_ids: personaIds, questions }),
          signal: signal ?? AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          const job = await res.json();
          this.rememberJobHandle(studyId, 'batch', job.job_id);
          return job;
        }
        throw await apiErrorFrom(res, 'Batch interview run failed');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    return { job_id: `bjob_mock_${Date.now()}`, study_id: studyId, status: 'running', total_personas: 3, personas: {} };
  },

  async getBatchRunStatus(studyId: string, jobId: string, signal?: AbortSignal): Promise<any> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/batch-run/${jobId}`, {
        headers: this.getAuthHeaders(),
        signal: signal ?? AbortSignal.timeout(TIMEOUT_MS.POLL),
      });
      if (!res.ok) {
        throw await apiErrorFrom(res, 'Batch status failed');
      }
      lastKnownLive = true;
      return await res.json();
    }
    return { job_id: jobId, study_id: studyId, status: 'completed', completed_count: 3, failed_count: 0, personas: {} };
  },

  // ---------------------------------------------------------------------------
  // Stripe Payments & Subscription
  // ---------------------------------------------------------------------------

  async createCheckoutSession(
    plan: string = 'pro',
    successUrl?: string,
    cancelUrl?: string,
  ): Promise<{ session_id: string; url: string; plan: string }> {
    if (!this.isMockMode()) {
      if ((await this.getSubscription()).billing_enabled !== true) throw new Error('Payments are disabled');
      const res = await fetch(`${API_BASE}/payments/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.getAuthHeaders(),
        },
        body: JSON.stringify({ plan, success_url: successUrl, cancel_url: cancelUrl }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Checkout creation failed (${res.status})` }));
        throw new Error(err.detail || 'Failed to create checkout session');
      }
      return await res.json();
    }
    throw new Error('Payments are disabled in mock mode');
  },

  async getSubscription(): Promise<{
    plan: string;
    status: string;
    is_paid: boolean;
    expires_at?: string | null;
    has_billing_account: boolean;
    billing_enabled?: boolean;
  }> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/payments/subscription`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Get subscription failed (${res.status})` }));
        throw new Error(err.detail || 'Failed to fetch subscription status');
      }
      return await res.json();
    }
    return {
      plan: 'free',
      status: 'active',
      is_paid: false,
      has_billing_account: false,
      billing_enabled: false,
    };
  },

  async createPortalSession(returnUrl?: string): Promise<{ url: string }> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/payments/create-portal-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.getAuthHeaders(),
        },
        body: JSON.stringify({ return_url: returnUrl }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Portal session failed (${res.status})` }));
        throw new Error(err.detail || 'Failed to open customer portal');
      }
      return await res.json();
    }
    return { url: '/app' };
  },
};

// A 401 on an authenticated call rotates the session once and replays the
// request; only when no refresh path is left does the caller see the 401.
setUnauthorizedRecovery(async (): Promise<Record<string, string> | null> => {
  if (api.isMockMode()) return null;
  const result = await api.refreshToken().catch(() => null);
  if (!result) return null;
  const token = api.getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
});





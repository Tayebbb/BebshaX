import {
  Business,
  Conversation,
  ConversationTurn,
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
import { neonAuth } from './neonAuth';
import { createResearchApi } from './researchApi';

const API_BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8000/api';

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
      const res = await fetch(`${API_BASE}/health`, {
        headers: this.getAuthHeaders(),
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
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch routes status (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
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
        const err = await res.json().catch(() => ({ detail: 'Failed to create business' }));
        throw new Error(err.detail || err.message || `Failed to create business (HTTP ${res.status})`);
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

  async generatePersona(
    businessId: string,
    audienceSegment: string,
    hints: string[]
  ): Promise<{ persona: Persona; provenance: ProvenanceRecord }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/businesses/${businessId}/personas`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            audience_segment: audienceSegment,
            generation_hints: hints,
            hints: hints.join(', '),
          }),
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          const persona: Persona = await res.json();

          // Query freshest provenance record for this persona
          const provRes = await this.getProvenance(1);
          const prov = provRes.items[0] || {
            request_id: `req_${Date.now().toString(36)}`,
            task: 'PERSONA_GENERATION' as const,
            pool: 'reasoning',
            persona_id: persona.id,
            conversation_id: null,
            created_at: new Date().toISOString(),
            routing_path: ['pollinations/deepseek-r1'],
            attempts: [],
            served_by_provider: 'pollinations',
            served_by_model: persona.generation_model || 'deepseek-r1',
            input_tokens: 1420,
            output_tokens: 850,
            total_latency_ms: 1200,
            success: true,
          };

          const { mockStore } = await loadMocks();
          mockStore.personas[persona.id] = persona;
          return { persona, provenance: prov };
        }
        lastKnownLive = false;
        const err = await res.json().catch(() => ({ detail: 'Persona generation failed' }));
        throw new Error(err.detail || err.message || `Persona generation failed (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }

    // Mock generation simulation
    const id = `per_${Date.now().toString(36)}`;
    const newPersona: Persona = {
      id,
      business_id: businessId,
      name: `Synthetic Persona (${audienceSegment.split(' ')[0] || 'User'})`,
      status: 'active',
      version: 1,
      archetype: 'The Adaptive Adopter',
      tagline: `Targeted persona synthesized for: ${audienceSegment.slice(0, 60)}...`,
      demographics: {
        age: 32,
        gender: 'Non-binary',
        occupation: audienceSegment.includes('driver') ? 'Independent Courier' : 'Professional Specialist',
        income_bracket: '$45,000 - $58,000 / year',
        location: 'Chicago, IL (Urban)',
        education: "Bachelor's Degree",
      },
      attributes: [
        {
          category: 'Goals',
          title: 'Frictionless Task Completion',
          description: 'Prioritizes workflows that eliminate redundant manual inputs and deliver instant feedback.',
          provenance_class: 'OBSERVED',
          evidence: {
            source: 'PersonaHub Grounding Slice',
            quote: 'Target audience segment emphasizes rapid feedback loops and minimal cognitive load.',
            confidence: 0.94,
          },
        },
        {
          category: 'Pain Points',
          title: 'Unclear Pricing & Subscription Traps',
          description: 'Extremely wary of surprise charges or vague recurring tiers with penalty terms.',
          provenance_class: 'INFERRED',
          evidence: {
            source: 'EmpatheticDialogues Corpus',
            quote: 'Users consistently express frustration with obscure billing models.',
            confidence: 0.89,
          },
        },
        {
          category: 'Behaviors',
          title: 'Multi-Device Synchronized Usage',
          description: 'Seamlessly switches between mobile browser during transit and desktop at work.',
          provenance_class: 'SYNTHETIC',
          evidence: null,
        },
      ],
      consistency_score: 0.97,
      grounding_ratio: 0.67,
      critic_notes: 'Verified: Synthetic persona passes all validation heuristics with no demographic inconsistencies.',
      generation_model: 'pollinations/deepseek-r1',
      created_at: new Date().toISOString(),
    };

    const newProvenance: ProvenanceRecord = {
      request_id: `req_${Date.now().toString(36)}`,
      task: 'PERSONA_GENERATION',
      pool: 'reasoning',
      persona_id: id,
      conversation_id: null,
      created_at: new Date().toISOString(),
      routing_path: ['groq/llama-3.3-70b-versatile', 'pollinations/deepseek-r1'],
      attempts: [
        {
          attempt_number: 1,
          provider: 'pollinations',
          model: 'deepseek-r1',
          started_at: new Date().toISOString(),
          latency_ms: 1180,
          success: true,
          failure_kind: null,
          failure_detail: null,
          fallback_reason: null,
          notes: ['Direct route completion'],
        },
      ],
      served_by_provider: 'pollinations',
      served_by_model: 'deepseek-r1',
      input_tokens: 1650,
      output_tokens: 880,
      total_latency_ms: 1180,
      success: true,
    };

    const { mockStore } = await loadMocks();
    mockStore.personas[id] = newPersona;
    mockStore.provenance.unshift(newProvenance);
    return { persona: newPersona, provenance: newProvenance };
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
              importance: d.importance ?? 0.8,
              recency_weight: 0.9,
              relevance_score: 0.95,
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
        const errorData = await res.json().catch(() => ({ detail: `Failed to start conversation (${res.status})` }));
        throw new Error(errorData.detail || errorData.message || 'Failed to start conversation');
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
        const errorData = await res.json().catch(() => ({ detail: `Interview message failed with status ${res.status}` }));
        throw new Error(errorData.detail || errorData.message || 'Interview message failed');
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
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch evaluation metrics (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    const { mockEvaluationMetrics } = await loadMocks();
    return mockEvaluationMetrics;
  },

  // 9. Authentication & User Management (JWT + Neon DB)
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
      const token = localStorage.getItem('bebshax_auth_token');
      if (token && this._isTokenExpired(token)) {
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
      if (token) {
        localStorage.setItem('bebshax_auth_token', token);
      } else {
        localStorage.removeItem('bebshax_auth_token');
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
    try {
      if (user) {
        localStorage.setItem('bebshax_auth_user', JSON.stringify(user));
      } else {
        localStorage.removeItem('bebshax_auth_user');
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
    };
    if (this.isMockMode()) {
      headers['X-BebshaX-Mock'] = '1';
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  },

  async refreshToken(): Promise<AuthResponse | null> {
    const token = this.getAuthToken();
    if (!token) return null;
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          this.setAuthToken(result.access_token);
          this.setStoredUser(result.user);
          lastKnownLive = true;
          return result;
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }
    return null;
  },

  /** Return all registered users. Requires a valid login token (any authenticated user). */
  async listUsers(): Promise<User[]> {
    if (this.isMockMode()) return [];
    try {
      const res = await fetch(`${API_BASE}/auth/users`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (res.ok) {
        lastKnownLive = true;
        return await res.json();
      }
      lastKnownLive = false;
    } catch {
      lastKnownLive = false;
    }
    return [];
  },

  async syncUser(data: {
    neon_token: string;
    auth_provider?: string;
  }): Promise<AuthResponse | null> {
    if (this.isMockMode()) return null;
    try {
      const res = await fetch(`${API_BASE}/auth/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          neon_token: data.neon_token,
          auth_provider: data.auth_provider || 'neon',
        }),
        signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
      });
      if (res.ok) {
        const result: AuthResponse = await res.json();
        this.setAuthToken(result.access_token);
        this.setStoredUser(result.user);
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/auth/signup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(30000),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          lastKnownLive = true;
          return result;
        }
        if (res.status === 409) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.detail || 'An account with this email address already exists.');
        }
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Registration failed');
      } catch (backendErr: any) {
        throw backendErr;
      }
    }

    // Mock fallback response
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
    const mockRes: AuthResponse = {
      access_token: `mock_jwt_${Date.now()}`,
      token_type: 'bearer',
      expires_in_days: 7,
      user: mockUser,
    };
    return mockRes;
  },

  async signin(data: SignInData): Promise<AuthResponse> {
    if (!this.isMockMode()) {
      // 1. Primary: Direct Backend API authentication (verifies against PostgreSQL users table)
      try {
        const res = await fetch(`${API_BASE}/auth/signin`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          this.setAuthToken(result.access_token);
          this.setStoredUser(result.user);
          lastKnownLive = true;
          return result;
        }
        if (res.status === 401 || res.status === 403) {
          const errorData = await res.json().catch(() => ({}));
          const detail: string = errorData.detail || 'Invalid email or password.';
          if (detail.includes('EMAIL_NOT_VERIFIED')) {
            const err = new Error(
              'Your email address is not verified yet. Enter the 6-digit code we send you to finish signing in.'
            ) as Error & { code: string };
            err.code = 'EMAIL_NOT_VERIFIED';
            throw err;
          }
          throw new Error(detail);
        }
      } catch (backendErr: any) {
        if (backendErr.code === 'EMAIL_NOT_VERIFIED') {
          throw backendErr;
        }
        if (backendErr.message && (backendErr.message.includes('Invalid email') || backendErr.message.includes('disabled'))) {
          throw backendErr;
        }

        // 2. Secondary: Neon Auth authentication fallback — a session only
        // exists if Neon authenticates AND the server-side /auth/sync
        // (which verifies the Neon token + emailVerified) mints a real JWT.
        try {
          const neonRes = await neonAuth.signIn({
            email: data.email,
            password: data.password,
          });
          if (neonRes.token) {
            const synced = await this.syncUser({ neon_token: neonRes.token });
            if (synced) return synced;
          }
          throw new Error(
            'Signed in with Neon, but the BebshaX backend is unreachable to establish a session. Please try again.'
          );
        } catch (neonErr: any) {
          throw neonErr || backendErr;
        }
      }
    }

    // Mock fallback response
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
    const token = this.getAuthToken();
    if (!token) return null;

    if (!this.isMockMode()) {
      // 1. Check Neon Auth live session (with token if present)
      try {
        const neonUser = await neonAuth.getSession(token);
        if (neonUser) {
          lastKnownLive = true;
          this.setStoredUser(neonUser);
          if (neonUser.token) {
            this.setAuthToken(neonUser.token);
          }
          return neonUser;
        }
      } catch {
        // ignore neon check error
      }

      // 2. Check Backend API /auth/me if we have a token
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
        if (res.ok) {
          lastKnownLive = true;
          const user = await res.json();
          this.setStoredUser(user);
          return user;
        } else if (res.status === 401 || res.status === 403) {
          // Token is rejected or invalid
          lastKnownLive = true;
          this.setAuthToken(null);
          this.setStoredUser(null);
          return null;
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
        // On network failure with valid non-expired token, return stored user if present
        return this.getStoredUser();
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
    _type: 'email-verification' | 'forget-password' | 'sign-in' = 'email-verification'
  ): Promise<boolean> {
    return await this.resendVerificationEmail(email);
  },

  async verifyEmailOtp(
    email: string,
    otp: string
  ): Promise<{ user: User; token?: string | null }> {
    if (!this.isMockMode()) {
      try {
        await fetch(`${API_BASE}/auth/verify-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: otp.trim() }),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD),
        });
      } catch {
        // Proceed — AuthContext handles session creation via signin retry
      }
      const verifiedUser: User = {
        id: '',
        email,
        full_name: email.split('@')[0],
        avatar_url: null,
        is_active: true,
        is_verified: true,
        auth_provider: 'email',
        created_at: new Date().toISOString(),
      };
      return { user: verifiedUser, token: null };
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
      return await neonAuth.resetPasswordWithOtp({ email, otp, password });
    }
    return true;
  },

  async signout(): Promise<void> {
    this.setAuthToken(null);
    this.setStoredUser(null);
    if (!this.isMockMode()) {
      await neonAuth.signOut();
    }
  },

  // 10. Research Studies Management (New Study, Dashboard, Workflows)
  // 10. Research Studies Management (User-Scoped 5-Step Workflow Persistence)
  getUserStudiesStorageKey(): string {
    const user = this.getStoredUser();
    return `bebshax_studies_${user?.id || 'default_user'}`;
  },

  getStoredUserStudies(): Study[] {
    try {
      const key = this.getUserStudiesStorageKey();
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed;
        }
      }
    } catch {
      // ignore
    }
    // Sync helper: mock-mode callers await loadMocks() before reaching this
    // fallback, so the cache is populated. Before any mock load (live mode,
    // cold cache) there are no seed studies to serve — return the empty list
    // instead of leaking fixtures into the live localStorage cache.
    return _mocksSync ? [..._mocksSync.mockStore.studies] : [];
  },

  saveStoredUserStudies(studies: Study[]) {
    try {
      const key = this.getUserStudiesStorageKey();
      localStorage.setItem(key, JSON.stringify(studies));
    } catch {
      // ignore
    }
  },

  async getStudies(): Promise<Study[]> {
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
            this.saveStoredUserStudies(data);
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
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          headers: this.getAuthHeaders(),
          // Restores the whole workflow state — aborting early loses chat/personas in the UI.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        throw new Error(`Failed to fetch study (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
    }
    await loadMocks();
    const studies = this.getStoredUserStudies();
    const study = studies.find((s) => s.id === id);
    return study ? { ...study } : null;
  },

  async getStudy(id: string): Promise<Study | null> {
    return this.getStudyById(id);
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
          const current = this.getStoredUserStudies();
          const next = [created, ...current.filter((s) => s.id !== created.id)];
          this.saveStoredUserStudies(next);
          return created;
        }
        lastKnownLive = false;
        const err = await res.json().catch(() => ({ detail: 'Failed to create study' }));
        throw new Error(err.detail || err.message || `Failed to create study (HTTP ${res.status})`);
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

  async updateStudy(id: string, updates: Partial<Study>): Promise<Study> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          method: 'PATCH',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(updates),
          // Large JSON payloads (personas_data, chat history) but pure DB write.
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          const updated = await res.json();
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
        const err = await res.json().catch(() => ({ detail: 'Failed to update study' }));
        throw new Error(err.detail || err.message || `Failed to update study (HTTP ${res.status})`);
      } catch (err) {
        lastKnownLive = false;
        throw err;
      }
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
        const err = await res.json().catch(() => ({ detail: 'Failed to save audience' }));
        throw new Error(err.detail || err.message || `Failed to save audience (HTTP ${res.status})`);
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
        const err = await res.json().catch(() => ({ detail: 'Copilot turn failed' }));
        throw new Error(err.detail || `Copilot turn failed (HTTP ${res.status})`);
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
        const err = await res.json().catch(() => ({ detail: 'Role suggestion failed' }));
        throw new Error(err.detail || `Role suggestion failed (HTTP ${res.status})`);
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
    if (!this.isMockMode()) {
      // Live mode: no silent mock substitution. A generation failure must be
      // visible to the user — fabricated personas would poison their research.
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
        const err = await res.json().catch(() => ({ detail: 'Persona generation failed' }));
        throw new Error(err.detail || 'Persona generation failed');
      }
      lastKnownLive = true;
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) {
        throw new Error('Persona generation returned no personas');
      }
      const { mockStore } = await loadMocks();
      data.forEach((p) => {
        mockStore.personas[p.id] = p;
      });
      return data;
    }

    const { mockGeneratedPersonas } = await loadMocks();
    return mockGeneratedPersonas(prompt, title);
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
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to ingest dataset URL');
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
          headers: this.getAuthHeaders(),
          body: formData,
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to upload dataset');
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
        const err = await res.json().catch(() => ({ detail: 'Dataset persona generation failed' }));
        throw new Error(err.detail || `Dataset persona generation failed (HTTP ${res.status})`);
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
        const err = await res.json().catch(() => ({ detail: 'Segmentation run failed' }));
        throw new Error(err.detail || `Segmentation run failed (HTTP ${res.status})`);
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
      } catch {
        lastKnownLive = false;
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
        median_budget: idx === 0 ? '৳350' : '৳750',
        budget_range: idx === 0 ? '৳250–৳500' : '৳500–৳1200',
        age_range: idx === 0 ? '18–22' : '19–23',
        tech_familiarity: idx === 0 ? 'Medium' : 'High',
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
  async pollGenerationJob<T>(pollUrl: string, opts?: { intervalMs?: number; timeoutMs?: number }): Promise<T> {
    const interval = opts?.intervalMs ?? 2500;
    const deadline = Date.now() + (opts?.timeoutMs ?? 600000);
    let transientFailures = 0;
    for (;;) {
      try {
        const res = await fetch(pollUrl, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(TIMEOUT_MS.POLL),
        });
        if (res.status === 404) {
          const err = await res.json().catch(() => ({ detail: 'job not found' }));
          throw Object.assign(new Error(err.detail || 'job not found'), { isJobFailure: true });
        }
        if (!res.ok) throw new Error(`poll ${res.status}`);
        transientFailures = 0;
        const job = await res.json();
        if (job.status === 'completed') return job.result as T;
        if (job.status === 'failed') {
          throw Object.assign(new Error(job.error || 'generation job failed'), { isJobFailure: true });
        }
      } catch (e) {
        if ((e as { isJobFailure?: boolean })?.isJobFailure) throw e;
        // Transient blip — the job is still running server-side; a 10-minute
        // wait must survive a dropped poll or two.
        transientFailures += 1;
        if (transientFailures >= 4) throw e;
      }
      if (Date.now() > deadline) {
        // The backend is alive and the job may still be running — only the
        // client stopped waiting. Propagate as a job-level outcome so callers
        // never degrade this into fabricated mock success.
        throw Object.assign(
          new Error('generation is taking longer than expected — it continues in the background'),
          { isJobFailure: true }
        );
      }
      await new Promise((r) => setTimeout(r, interval));
    }
  },

  async generateSyntheticPersonas(
    studyId: string,
    payload: GeneratePersonasPayload
  ): Promise<{ run: PersonaGenerationRun; personas: SyntheticPersona[] }> {
    if (!this.isMockMode()) {
      try {
        // Job endpoint first: generation runs for minutes at free-tier
        // latency — the POST returns 202 immediately and we poll.
        const jobRes = await fetch(`${API_BASE}/studies/${studyId}/personas/generate/jobs`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        if (jobRes.status === 202) {
          const { job_id } = await jobRes.json();
          lastKnownLive = true;
          try {
            return await this.pollGenerationJob(
              `${API_BASE}/studies/${studyId}/personas/generate/jobs/${job_id}`
            );
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
          const err = await res.json().catch(() => ({ detail: 'Persona generation failed' }));
          throw new Error(err.detail || `Persona generation failed (HTTP ${res.status})`);
        }
        lastKnownLive = false;
        const jobErr = await jobRes.json().catch(() => ({ detail: 'Persona generation failed' }));
        throw new Error(jobErr.detail || `Persona generation failed (HTTP ${jobRes.status})`);
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
        const err = await res.json().catch(() => ({ detail: 'Persona regeneration failed' }));
        throw new Error(err.detail || `Persona regeneration failed (HTTP ${res.status})`);
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
        const err = await res.json().catch(() => ({ detail: 'Failed to start interview' }));
        throw new Error(err.detail || 'Failed to start interview');
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

        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews?${q.toString()}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
      }
      return { interviews: [], total: 0 };
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

  async getStudyInterviewDetail(studyId: string, interviewId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/${interviewId}`, {
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
    throw new Error('Interview not found');
  },

  async sendInterviewMessage(
    studyId: string,
    interviewId: string,
    payload: { content: string }
  ): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/interviews/${interviewId}/messages`,
          {
            method: 'POST',
            headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(payload),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to send message' }));
        throw new Error(err.detail || 'Failed to send message');
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
    onDelta: (text: string) => void
  ): Promise<any> {
    if (this.isMockMode()) throw new Error('Backend required for live persona interview');

    const res = await fetch(
      `${API_BASE}/studies/${studyId}/interviews/${interviewId}/messages/stream`,
      {
        method: 'POST',
        headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ content }),
      }
    );
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => ({ detail: `Stream failed (${res.status})` }));
      const e = new Error(err.detail || 'Stream failed') as Error & { status?: number };
      e.status = res.status;
      lastKnownLive = false;
      throw e;
    }
    lastKnownLive = true;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let done: any = null;

    const handleFrame = (frame: string) => {
      const lines = frame.split(/\r?\n/);
      const eventLine = lines.find((l) => l.startsWith('event:'));
      // Per the SSE spec, multiple data: lines concatenate with newlines.
      const dataPayload = lines
        .filter((l) => l.startsWith('data:'))
        .map((l) => l.slice(5).replace(/^ /, ''))
        .join('\n');
      if (!eventLine || !dataPayload) return;
      const event = eventLine.slice(6).trim();
      const data = JSON.parse(dataPayload);
      if (event === 'delta') onDelta(data.text || '');
      else if (event === 'done') done = data;
      else if (event === 'error') {
        const e = new Error(data.detail || 'interview turn failed') as Error & { kind?: string };
        e.kind = data.kind;
        throw e;
      }
    };

    try {
      for (;;) {
        const { value, done: eof } = await reader.read();
        if (eof) break;
        buffer += decoder.decode(value, { stream: true });
        let match: RegExpExecArray | null;
        const boundary = /\r?\n\r?\n/;
        while ((match = boundary.exec(buffer)) !== null) {
          const frame = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          handleFrame(frame);
        }
      }
      if (buffer.trim()) handleFrame(buffer);
    } finally {
      reader.cancel().catch(() => {});
    }

    if (!done) throw new Error('Stream ended without a final reply');
    return done;
  },

  async completeStudyInterview(studyId: string, interviewId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/interviews/${interviewId}/complete`,
          {
            method: 'POST',
            headers: this.getAuthHeaders(),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to complete interview' }));
        throw new Error(err.detail || 'Failed to complete interview');
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
        const err = await res.json().catch(() => ({ detail: 'Failed to create behavioral test' }));
        throw new Error(err.detail || 'Failed to create behavioral test');
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
      } catch {
        lastKnownLive = false;
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

  async getBehavioralTestDetail(studyId: string, testId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to fetch test detail' }));
        throw new Error(err.detail || 'Failed to fetch test detail');
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
        const err = await res.json().catch(() => ({ detail: 'Failed to update test' }));
        throw new Error(err.detail || 'Failed to update test');
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

  async triggerBehavioralTestRun(studyId: string, testId: string, payload: any): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}/runs`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to start simulation run' }));
        throw new Error(err.detail || 'Failed to start simulation run');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for running simulation');
  },

  async getBehavioralTestRuns(studyId: string, testId: string): Promise<any[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/${testId}/runs`, {
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

  async getBehavioralRunStatus(studyId: string, runId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/runs/${runId}`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to fetch run status' }));
        throw new Error(err.detail || 'Failed to fetch run status');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Backend required for run status');
  },

  async getBehavioralRunResults(studyId: string, runId: string): Promise<any> {
    return this.getBehavioralRunStatus(studyId, runId);
  },

  async retryFailedBehavioralRun(studyId: string, runId: string): Promise<any> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/behavioral-tests/runs/${runId}/retry-failed`, {
          method: 'POST',
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to retry failed simulations' }));
        throw new Error(err.detail || 'Failed to retry failed simulations');
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
      } catch {
        lastKnownLive = false;
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
          return await res.json();
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
      return [];
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
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
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
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Failed to fetch report' }));
        throw new Error(err.detail || 'Failed to fetch report');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Report not found');
  },

  async generateStudyReport(studyId: string, title?: string): Promise<StudyReport> {
    if (!this.isMockMode()) {
      try {
        // Job endpoint first: synthesis reads every interview + runs LLM
        // calls (150s budget) — 202 + poll instead of one long request.
        const jobRes = await fetch(`${API_BASE}/studies/${studyId}/reports/generate/jobs`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ title }),
        });
        if (jobRes.status === 202) {
          const { job_id } = await jobRes.json();
          lastKnownLive = true;
          return await this.pollGenerationJob<StudyReport>(
            `${API_BASE}/studies/${studyId}/reports/generate/jobs/${job_id}`,
            { timeoutMs: 300000 }
          );
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
          const err = await res.json().catch(() => ({ detail: 'Report generation failed' }));
          throw new Error(err.detail || 'Report generation failed');
        }
        const err = await jobRes.json().catch(() => ({ detail: 'Report generation failed' }));
        throw new Error(err.detail || 'Report generation failed');
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
  ): Promise<{ study_id: string; questions: string[]; count: number }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/script/generate`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ prompt, question_count: count }),
          signal: AbortSignal.timeout(TIMEOUT_MS.LLM),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
        const err = await res.json().catch(() => ({ detail: 'Script generation failed' }));
        throw new Error(err.detail || `Script generation failed (HTTP ${res.status})`);
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
    };
  },

  async runBatchStudyInterviews(
    studyId: string,
    personaIds?: string[],
    questions?: string[]
  ): Promise<any> {
    if (!this.isMockMode()) {
      try {
        // Starts a background job (202); progress comes from getBatchRunStatus.
        const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/batch-run`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ persona_ids: personaIds, questions }),
          signal: AbortSignal.timeout(TIMEOUT_MS.CRUD_HEAVY),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({ detail: 'Batch interview run failed' }));
        throw new Error(err.detail || 'Batch interview run failed');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    return { job_id: `bjob_mock_${Date.now()}`, study_id: studyId, status: 'running', total_personas: 3, personas: {} };
  },

  async getBatchRunStatus(studyId: string, jobId: string): Promise<any> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/studies/${studyId}/interviews/batch-run/${jobId}`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(TIMEOUT_MS.POLL),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Batch status failed (${res.status})` }));
        const e = new Error(err.detail || 'Batch status failed') as Error & { status?: number };
        e.status = res.status;
        throw e;
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
      const res = await fetch(`${API_BASE}/payments/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...this.getAuthHeaders(),
        },
        body: JSON.stringify({ plan, success_url: successUrl, cancel_url: cancelUrl }),
        signal: AbortSignal.timeout(15000),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `Checkout creation failed (${res.status})` }));
        throw new Error(err.detail || 'Failed to create checkout session');
      }
      return await res.json();
    }
    return {
      session_id: `cs_mock_${Date.now()}`,
      url: `/app?checkout=success&plan=${plan}`,
      plan,
    };
  },

  async getSubscription(): Promise<{
    plan: string;
    status: string;
    is_paid: boolean;
    expires_at?: string | null;
    has_billing_account: boolean;
  }> {
    if (!this.isMockMode()) {
      const res = await fetch(`${API_BASE}/payments/subscription`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(10000),
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
        signal: AbortSignal.timeout(15000),
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






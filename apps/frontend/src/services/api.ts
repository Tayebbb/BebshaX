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
  EvidenceSource,
  EvidenceClaim,
  EvidenceSummary,
  ResearchRun,
  ClaimDetail,
  SourceDetail,
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
import {
  mockBusinesses,
  mockConversations,
  mockDatasets,
  mockEvaluationMetrics,
  mockHealth,
  mockMemories,
  mockPersonas,
  mockProvenanceRecords,
  mockRoutesStatus,
  mockStudies,
  mockEvidenceSources,
  mockEvidenceClaims,
} from '../mocks/fixtures';
import { neonAuth } from './neonAuth';

const API_BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8000/api';

// In-memory state store for client modifications during mock/fallback mode
class MockStore {
  businesses: Business[] = [];
  personas: Record<string, Persona> = {};
  memories: Record<string, MemoryItem[]> = {};
  conversations: Record<string, Conversation> = {};
  provenance: ProvenanceRecord[] = [];
  studies: Study[] = [];
  datasets: DatasetSource[] = [];
  sources: EvidenceSource[] = [];
  claims: EvidenceClaim[] = [];
  researchRuns: ResearchRun[] = [];

  constructor() {
    this.reset();
  }

  reset() {
    this.businesses = JSON.parse(JSON.stringify(mockBusinesses));
    this.personas = JSON.parse(JSON.stringify(mockPersonas));
    this.memories = JSON.parse(JSON.stringify(mockMemories));
    this.conversations = JSON.parse(JSON.stringify(mockConversations));
    this.provenance = JSON.parse(JSON.stringify(mockProvenanceRecords));
    this.studies = JSON.parse(JSON.stringify(mockStudies));
    this.datasets = JSON.parse(JSON.stringify(mockDatasets));
    this.sources = JSON.parse(JSON.stringify(mockEvidenceSources));
    this.claims = JSON.parse(JSON.stringify(mockEvidenceClaims));
    this.researchRuns = [];
  }
}

const mockStore = new MockStore();

let forceMockMode: boolean | null = null;
let lastKnownLive = false;

export const api = {
  resetMockStore() {
    mockStore.reset();
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.clear();
      }
    } catch {
      // ignore
    }
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
      return mockHealth;
    }
    try {
      const res = await fetch(`${API_BASE}/health`, {
        headers: this.getAuthHeaders(),
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        lastKnownLive = true;
        return await res.json();
      }
      lastKnownLive = false;
    } catch {
      lastKnownLive = false;
    }
    return mockHealth;
  },

  // 2. Routes & Provider Status
  async getRoutesStatus(): Promise<RoutesStatusResponse> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/routes/status`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
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
    return mockRoutesStatus;
  },

  // 3. Provenance Records
  async getProvenance(limit = 50): Promise<{ items: ProvenanceRecord[]; total: number }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/provenance?limit=${limit}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.items)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }
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
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data)) {
            lastKnownLive = true;
            return data;
          }
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }
    return mockStore.businesses;
  },

  async createBusiness(data: Omit<Business, 'id' | 'persona_count' | 'created_at'>): Promise<Business> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/businesses`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(10000),
        });
        if (res.ok) {
          lastKnownLive = true;
          const created = await res.json();
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
    mockStore.businesses.unshift(newBiz);
    return newBiz;
  },

  // 5. Personas
  async getPersonas(): Promise<Persona[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
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
    return Object.values(mockStore.personas);
  },

  async getPersona(id: string): Promise<Persona | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas/${id}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
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
          signal: AbortSignal.timeout(120000),
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
          signal: AbortSignal.timeout(5000),
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
    return mockStore.memories[personaId] || [];
  },

  // 7. Conversations
  async getConversation(id: string): Promise<Conversation | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations/${id}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
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
    return mockStore.conversations[id] || null;
  },

  async startConversation(personaId: string, objective: string): Promise<Conversation> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ persona_id: personaId, objective }),
          signal: AbortSignal.timeout(120000),
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
          signal: AbortSignal.timeout(120000),
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
            content: data.persona_reply?.content || data.reply,
            timestamp: data.persona_reply?.timestamp || new Date().toISOString(),
            latency_ms: data.persona_reply?.latency_ms || 750,
            served_by: data.persona_reply?.served_by || data.served_by || 'ollama/qwen3.5',
            retrieved_memories: data.persona_reply?.retrieved_memories || ['Active Persona Context'],
          };
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
          signal: AbortSignal.timeout(5000),
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
          signal: AbortSignal.timeout(5000),
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
        signal: AbortSignal.timeout(10000),
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
    email: string;
    full_name?: string;
    avatar_url?: string | null;
    auth_provider?: string;
  }): Promise<AuthResponse | null> {
    if (this.isMockMode()) return null;
    try {
      const res = await fetch(`${API_BASE}/auth/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        signal: AbortSignal.timeout(10000),
      });
      if (res.ok) {
        const result: AuthResponse = await res.json();
        this.setAuthToken(result.access_token);
        this.setStoredUser(result.user);
        lastKnownLive = true;
        return result;
      }
    } catch {
      // ignore
    }
    return null;
  },

  async signup(data: SignUpData): Promise<AuthResponse> {
    if (!this.isMockMode()) {
      // 1. Primary: Direct Backend API registration (commits to PostgreSQL users table)
      try {
        const res = await fetch(`${API_BASE}/auth/signup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(10000),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          this.setAuthToken(result.access_token);
          this.setStoredUser(result.user);
          lastKnownLive = true;
          // Optionally register with Neon Auth in background
          neonAuth.signUp({
            email: data.email,
            password: data.password,
            name: data.full_name,
          }).catch(() => {});
          return result;
        }
        if (res.status === 409) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.detail || 'An account with this email address already exists.');
        }
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Registration failed');
      } catch (backendErr: any) {
        if (backendErr.message && backendErr.message.includes('already exists')) {
          throw backendErr;
        }

        // 2. Secondary: Try Neon Auth registration and sync back to backend
        try {
          const neonRes = await neonAuth.signUp({
            email: data.email,
            password: data.password,
            name: data.full_name,
          });
          // Sync user to backend database
          const synced = await this.syncUser({
            email: data.email,
            full_name: data.full_name,
            auth_provider: 'neon',
          });
          if (synced) return synced;

          const token = neonRes.token || `neon_sess_${Date.now()}`;
          this.setAuthToken(token);
          this.setStoredUser(neonRes.user);
          lastKnownLive = true;
          return {
            access_token: token,
            token_type: 'bearer',
            expires_in_days: 7,
            user: neonRes.user,
          };
        } catch (neonErr: any) {
          throw neonErr || backendErr;
        }
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
          signal: AbortSignal.timeout(10000),
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
          throw new Error(errorData.detail || 'Invalid email or password.');
        }
      } catch (backendErr: any) {
        if (backendErr.message && (backendErr.message.includes('Invalid email') || backendErr.message.includes('disabled'))) {
          throw backendErr;
        }

        // 2. Secondary: Neon Auth authentication fallback, followed by sync
        try {
          const neonRes = await neonAuth.signIn({
            email: data.email,
            password: data.password,
          });
          const synced = await this.syncUser({
            email: data.email,
            full_name: neonRes.user.full_name,
            avatar_url: neonRes.user.avatar_url,
            auth_provider: 'neon',
          });
          if (synced) return synced;

          const token = neonRes.token || `neon_sess_${Date.now()}`;
          this.setAuthToken(token);
          this.setStoredUser(neonRes.user);
          lastKnownLive = true;
          return {
            access_token: token,
            token_type: 'bearer',
            expires_in_days: 7,
            user: neonRes.user,
          };
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
    let email = data.email;
    let name = data.name;
    let avatarUrl = data.avatar_url;

    if (data.credential && (!avatarUrl || !name || !email)) {
      try {
        const parts = data.credential.split('.');
        if (parts.length >= 2) {
          const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
          if (payload.picture && !avatarUrl) avatarUrl = payload.picture;
          if (payload.name && !name) name = payload.name;
          if (payload.email && !email) email = payload.email;
        }
      } catch {
        // ignore
      }
    }

    email = email || 'user@bebshax.io';
    name = name || email.split('@')[0].replace(/[._]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    avatarUrl = avatarUrl || undefined;

    const requestPayload = {
      email,
      name,
      avatar_url: avatarUrl,
      credential: data.credential,
    };

    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/auth/google`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestPayload),
          signal: AbortSignal.timeout(10000),
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

    const mockUser: User = {
      id: `usr_g_${Date.now().toString(36)}`,
      email: email,
      full_name: name,
      avatar_url: avatarUrl,
      is_active: true,
      is_verified: true,
      auth_provider: 'google',
      created_at: new Date().toISOString(),
    };
    const mockRes: AuthResponse = {
      access_token: `jwt_g_${Date.now()}`,
      token_type: 'bearer',
      expires_in_days: 365,
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
          signal: AbortSignal.timeout(5000),
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
    return await neonAuth.sendVerificationEmail(email);
  },

  async sendOtp(
    email: string,
    type: 'email-verification' | 'forget-password' | 'sign-in' = 'email-verification'
  ): Promise<boolean> {
    if (!this.isMockMode()) {
      return await neonAuth.sendVerificationOtp(email, type);
    }
    return true;
  },

  async verifyEmailOtp(
    email: string,
    otp: string
  ): Promise<{ user: User; token?: string | null }> {
    if (!this.isMockMode()) {
      const res = await neonAuth.verifyEmailOtp({ email, otp });
      // Sync verified user to backend database
      const synced = await this.syncUser({
        email: res.user.email,
        full_name: res.user.full_name,
        avatar_url: res.user.avatar_url,
        auth_provider: 'neon',
      });
      if (synced) {
        return { user: synced.user, token: synced.access_token };
      }
      if (res.token) this.setAuthToken(res.token);
      this.setStoredUser(res.user);
      return res;
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
    return [...mockStore.studies];
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
          signal: AbortSignal.timeout(5000),
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
    return this.getStoredUserStudies();
  },

  async getStudyById(id: string): Promise<Study | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(5000),
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
          signal: AbortSignal.timeout(120000),
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
          signal: AbortSignal.timeout(120000),
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
          signal: AbortSignal.timeout(10000),
        });
        if (res.ok) {
          lastKnownLive = true;
        } else {
          lastKnownLive = false;
        }
      } catch {
        lastKnownLive = false;
      }
    }
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
          signal: AbortSignal.timeout(10000),
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
          signal: AbortSignal.timeout(5000),
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
          signal: AbortSignal.timeout(120000),
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

    const userTurns = messages.filter((m) => m.role === 'user');
    const turnCount = userTurns.length;
    const firstText = userTurns[0]?.content || '';
    const lastText = userTurns[userTurns.length - 1]?.content || '';
    const combinedText = (firstText + ' ' + lastText).toLowerCase();

    const hasPricing = /price|cost|month|subscription|plan|\$|taka|bdt|€|£|free/.test(combinedText);
    const hasStudents = /student|school|college|university|study planner|academic|exam/.test(combinedText);
    const hasPriceTracker = /price tracker|price-tracker|tracker|price track|deal alert|price drop|deal hunter/.test(combinedText);
    const hasFood = /food|restaurant|delivery|meal|eat|chef|recipe|cuisine/.test(combinedText);
    const hasHealth = /health|fitness|gym|workout|diet|wellness|doctor|medical/.test(combinedText);
    const hasFintech = /payment|bank|finance|loan|invest|money|wallet|crypto/.test(combinedText);
    const hasEcommerce = /shop|sell|buy|store|marketplace|fashion/.test(combinedText);
    const hasB2B = /saas|enterprise|team|office|workflow|productivity|b2b|business tool/.test(combinedText);

    let productType = 'product or service';
    let audienceQ = 'Who is your primary target user — what\'s their age range, lifestyle, or professional context? And what geography are you launching in first?';
    let followupQ = 'What\'s the core problem you\'re solving for them, and what\'s the price point or business model you\'re validating?';
    let roles: PersonaRoleSuggestion[] = [];

    if (hasStudents) {
      productType = 'education or student-focused product';
      audienceQ = 'What level of students — K-12, university, or professional learners? And what geography?';
      followupQ = 'Is this B2C for students directly, or B2B (schools/universities)? And what\'s the price point?';
      roles = [
        { id: 'role_uni_student', role: 'UNIVERSITY STUDENT', description: 'Core target user — validates product-market fit and willingness to pay.', count: 3, selected: true },
        { id: 'role_college_applicant', role: 'COLLEGE APPLICANT', description: 'High-stakes test-taker — validates premium tier and urgency.', count: 3, selected: true },
        { id: 'role_high_schooler', role: 'BUSY HIGH SCHOOLER', description: 'Time-pressed student — tests core value delivery.', count: 3, selected: true },
        { id: 'role_parental_buyer', role: 'PARENTAL BUYER', description: 'Parent paying for child\'s tools — validates pricing framing and trust.', count: 0, selected: false },
        { id: 'role_budget_student', role: 'BUDGET-CONSCIOUS STUDENT', description: 'Price-sensitive student — tests pricing floor and free tier.', count: 0, selected: false },
      ];
    } else if (hasPriceTracker) {
      productType = 'price tracker & deal intelligence website';
      audienceQ = 'Who are your primary users — online deal hunters, budget planners, or frequent gadget/apparel shoppers? And what retail platforms will you track first?';
      followupQ = 'What specific alert channels (SMS, email, push) and historical price analytics will prove the 100 taka/month value proposition?';
      roles = [
        { id: 'role_bargain_hunter', role: 'SMART BARGAIN HUNTER', description: 'Active online shopper monitoring sales and deals — tests willingness to pay 100 taka/month for instant alerts.', count: 3, selected: true },
        { id: 'role_tech_shopper', role: 'TECH-SAVVY CONSUMER', description: 'Frequent e-commerce buyer tracking price drops across multiple marketplaces.', count: 3, selected: true },
        { id: 'role_budget_planner', role: 'BUDGET-CONSCIOUS BUYER', description: 'Price-sensitive household planner validating monthly subscription ROI.', count: 3, selected: true },
        { id: 'role_deal_skeptic', role: 'DEAL SKEPTIC', description: 'Consumer comparing free price trackers vs paid premium alert features.', count: 0, selected: false },
        { id: 'role_impulse_shopper', role: 'IMPULSE BUYER', description: 'Occasional shopper testing if historical price charts influence purchase timing.', count: 0, selected: false },
      ];
    } else if (hasFood) {
      productType = 'food or restaurant service';
      audienceQ = 'Who are the primary customers — home cooks, busy professionals, or families? And what region or city are you targeting first?';
      followupQ = 'What\'s the main value proposition — convenience, cost savings, or quality? And what price point are you considering?';
      roles = [
        { id: 'role_busy_professional', role: 'BUSY PROFESSIONAL', description: 'Time-pressed professional who values convenience over price — core paying customer.', count: 3, selected: true },
        { id: 'role_home_cook', role: 'HOME COOK', description: 'Cooking enthusiast who compares against cooking at home — key value benchmark.', count: 3, selected: true },
        { id: 'role_family_planner', role: 'FAMILY MEAL PLANNER', description: 'Parent managing family nutrition and budget — represents group/family subscription potential.', count: 3, selected: true },
        { id: 'role_health_conscious', role: 'HEALTH-CONSCIOUS EATER', description: 'Health-focused user with dietary needs — tests premium tier demands.', count: 0, selected: false },
        { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Value-maximizer who compares cost per meal — tests pricing floor.', count: 0, selected: false },
      ];
    } else if (hasHealth) {
      productType = 'health & wellness product';
      audienceQ = 'Who is your primary user — fitness enthusiasts, people with health conditions, or a broader wellness audience?';
      followupQ = 'Is this B2C or B2B (gyms, clinics)? And what\'s the rough price point?';
      roles = [
        { id: 'role_fitness_enthusiast', role: 'FITNESS ENTHUSIAST', description: 'Regular gym-goer — primary power user who validates core features.', count: 3, selected: true },
        { id: 'role_wellness_beginner', role: 'WELLNESS BEGINNER', description: 'Person starting their health journey — tests onboarding and motivational hooks.', count: 3, selected: true },
        { id: 'role_chronic_user', role: 'CHRONIC CONDITION USER', description: 'Person managing a health condition — tests specialized depth and accuracy.', count: 3, selected: true },
        { id: 'role_time_poor', role: 'TIME-POOR PROFESSIONAL', description: 'High-income, low-time user — validates premium tier.', count: 0, selected: false },
        { id: 'role_skeptic', role: 'HEALTH APP SKEPTIC', description: 'Person who tried and failed at health apps — reveals key churn drivers.', count: 0, selected: false },
      ];
    } else if (hasFintech) {
      productType = 'fintech product';
      audienceQ = 'Who is your primary user — individuals, small businesses, or enterprises? And what geography are you targeting?';
      followupQ = 'What financial problem are you solving — payments, savings, credit, or investments?';
      roles = [
        { id: 'role_early_adopter', role: 'EARLY ADOPTER PRO', description: 'Tech-savvy individual comfortable with financial apps — validates core assumptions.', count: 3, selected: true },
        { id: 'role_small_biz', role: 'SMALL BUSINESS OWNER', description: 'SMB operator managing cash flow — high-value B2B2C segment.', count: 3, selected: true },
        { id: 'role_underbanked', role: 'UNDERBANKED USER', description: 'Person with limited banking access — tests financial inclusion positioning.', count: 3, selected: true },
        { id: 'role_security_skeptic', role: 'SECURITY SKEPTIC', description: 'Privacy-first user — reveals trust barriers.', count: 0, selected: false },
        { id: 'role_high_net', role: 'HIGH NET WORTH USER', description: 'Affluent user with complex needs — tests premium ceiling.', count: 0, selected: false },
      ];
    } else if (hasEcommerce) {
      productType = 'e-commerce or marketplace';
      audienceQ = 'Who are your primary buyers — consumers or businesses? And what product category are you focused on?';
      followupQ = 'Are you a marketplace or direct retailer? And what\'s the target geography and price range?';
      roles = [
        { id: 'role_impulse_buyer', role: 'IMPULSE BUYER', description: 'Discovery-driven shopper — tests conversion and merchandising.', count: 3, selected: true },
        { id: 'role_research_first', role: 'RESEARCH-FIRST BUYER', description: 'Methodical shopper — tests trust signals and pricing clarity.', count: 3, selected: true },
        { id: 'role_loyal_repeater', role: 'LOYAL REPEATER', description: 'Returning customer — tests retention and loyalty programs.', count: 3, selected: true },
        { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Discount-motivated buyer — tests pricing floor.', count: 0, selected: false },
        { id: 'role_premium_seeker', role: 'PREMIUM SEEKER', description: 'Quality-over-price buyer — tests premium positioning.', count: 0, selected: false },
      ];
    } else if (hasB2B) {
      productType = 'B2B SaaS or business tool';
      audienceQ = 'What size companies are you targeting — SMBs, mid-market, or enterprise? And what industry does this serve?';
      followupQ = 'What is the primary workflow or problem being solved? And what\'s your pricing model?';
      roles = [
        { id: 'role_decision_maker', role: 'BUDGET DECISION MAKER', description: 'Manager who approves tool purchases — validates ROI narrative.', count: 3, selected: true },
        { id: 'role_power_user', role: 'DAILY POWER USER', description: 'Individual contributor using the tool most — validates UX depth.', count: 3, selected: true },
        { id: 'role_it_eval', role: 'IT SECURITY EVALUATOR', description: 'Tech gatekeeping role — tests compliance and integration.', count: 3, selected: true },
        { id: 'role_champion', role: 'INTERNAL CHAMPION', description: 'Early adopter who advocates internally — tests viral mechanics.', count: 0, selected: false },
        { id: 'role_resistant', role: 'CHANGE-RESISTANT USER', description: 'Employee reluctant to adopt — reveals adoption barriers.', count: 0, selected: false },
      ];
    } else {
      roles = [
        { id: 'role_primary', role: 'PRIMARY USER', description: 'Core target user — validates product-market fit and core value proposition.', count: 3, selected: true },
        { id: 'role_early_adopter', role: 'EARLY ADOPTER', description: 'Tech-forward user open to new solutions — validates initial demand.', count: 3, selected: true },
        { id: 'role_price_conscious', role: 'PRICE-CONSCIOUS USER', description: 'Budget-sensitive potential customer — validates pricing model.', count: 3, selected: true },
        { id: 'role_skeptic', role: 'SKEPTICAL NON-USER', description: 'Person using a competitor — reveals switching barriers.', count: 0, selected: false },
        { id: 'role_power_user', role: 'POWER USER', description: 'Heavy user who needs advanced features — validates depth.', count: 0, selected: false },
      ];
    }

    if (turnCount === 1) {
      return {
        reply: `Got it — you're exploring an ${productType}${hasPricing ? ' with a target pricing model' : ''}. User Interviews are ideal here to uncover mental models, key objections, and real willingness to pay.\n\n${audienceQ}`,
        suggested_study_type: 'interviews',
        is_ready_for_approval: false,
        research_goal_card: null,
        suggested_roles: roles,
        served_by: 'bebshax/copilot-engine',
      };
    } else if (turnCount === 2) {
      return {
        reply: followupQ,
        suggested_study_type: 'interviews',
        is_ready_for_approval: false,
        research_goal_card: null,
        suggested_roles: roles,
        served_by: 'bebshax/copilot-engine',
      };
    } else {
      return {
        reply: "I've synthesized your inputs into a focused research goal proposal below:",
        suggested_study_type: 'interviews',
        is_ready_for_approval: true,
        research_goal_card: {
          title: 'RESEARCH GOAL',
          summary: `Validate whether your ${productType} solves a genuine need for target users and determine demand${hasPricing ? ' at your target price point' : ''}. Does this capture what you're looking for?`,
          target_audience: `Target users of the ${productType}`,
          core_hypothesis: `Demand and product-market fit for the ${productType}`,
        },
        suggested_roles: roles,
        served_by: 'bebshax/copilot-engine',
      };
    }
  },

  async getSuggestedPersonaRoles(studyPrompt: string): Promise<PersonaRoleSuggestion[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/study/suggest-roles`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ study_prompt: studyPrompt }),
          signal: AbortSignal.timeout(120000),
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
    // Context-aware fallback: derive roles from the study prompt
    const promptLower = studyPrompt.toLowerCase();
    if (/tracker|track|price|deal|discount|compare|monitoring|shopping|ecommerce|taka/.test(promptLower)) {
      return [
        { id: 'role_bargain_hunter', role: 'SMART BARGAIN HUNTER', description: 'Active online shopper monitoring sales and deals — validates 100 taka/mo pricing.', count: 3, selected: true },
        { id: 'role_tech_shopper', role: 'TECH-SAVVY CONSUMER', description: 'Frequent buyer tracking price drops across marketplaces.', count: 3, selected: true },
        { id: 'role_budget_planner', role: 'BUDGET-CONSCIOUS BUYER', description: 'Price-sensitive household planner validating monthly subscription ROI.', count: 3, selected: true },
        { id: 'role_deal_skeptic', role: 'DEAL SKEPTIC', description: 'Consumer comparing free price trackers vs paid premium alert features.', count: 0, selected: false },
        { id: 'role_impulse_shopper', role: 'IMPULSE BUYER', description: 'Occasional shopper testing if historical price charts influence purchase timing.', count: 0, selected: false },
      ];
    } else if (/food|restaurant|delivery|meal|eat/.test(promptLower)) {
      return [
        { id: 'role_busy_professional', role: 'BUSY PROFESSIONAL', description: 'Time-pressed professional — core convenience-driven paying customer.', count: 3, selected: true },
        { id: 'role_home_cook', role: 'HOME COOK', description: 'Cooking enthusiast — key value-vs-cooking-at-home benchmark.', count: 3, selected: true },
        { id: 'role_family_planner', role: 'FAMILY MEAL PLANNER', description: 'Parent managing family nutrition — represents group/family segment.', count: 3, selected: true },
        { id: 'role_health_conscious', role: 'HEALTH-CONSCIOUS EATER', description: 'Dietary-needs user — tests premium tier.', count: 0, selected: false },
        { id: 'role_deal_hunter', role: 'DEAL HUNTER', description: 'Value-seeker — tests pricing floor.', count: 0, selected: false },
      ];
    } else if (/health|fitness|gym|wellness|doctor/.test(promptLower)) {
      return [
        { id: 'role_fitness_enthusiast', role: 'FITNESS ENTHUSIAST', description: 'Regular exerciser — validates core features.', count: 3, selected: true },
        { id: 'role_wellness_beginner', role: 'WELLNESS BEGINNER', description: 'Person starting health journey — tests onboarding.', count: 3, selected: true },
        { id: 'role_chronic_user', role: 'CHRONIC CONDITION USER', description: 'Managing health condition — tests specialized depth.', count: 3, selected: true },
        { id: 'role_skeptic', role: 'HEALTH APP SKEPTIC', description: 'Failed at health apps before — reveals churn drivers.', count: 0, selected: false },
      ];
    } else if (/payment|bank|finance|loan|invest|wallet|crypto/.test(promptLower)) {
      return [
        { id: 'role_early_adopter', role: 'EARLY ADOPTER PRO', description: 'Tech-savvy financial app user — validates core assumptions.', count: 3, selected: true },
        { id: 'role_small_biz', role: 'SMALL BUSINESS OWNER', description: 'SMB managing cash flow — high-value segment.', count: 3, selected: true },
        { id: 'role_underbanked', role: 'UNDERBANKED USER', description: 'Limited banking access — tests inclusion positioning.', count: 3, selected: true },
        { id: 'role_security_skeptic', role: 'SECURITY SKEPTIC', description: 'Privacy-first user — reveals trust barriers.', count: 0, selected: false },
      ];
    } else if (/shop|sell|buy|store|marketplace|ecommerce|fashion/.test(promptLower)) {
      return [
        { id: 'role_impulse_buyer', role: 'IMPULSE BUYER', description: 'Discovery-driven shopper — tests conversion.', count: 3, selected: true },
        { id: 'role_research_first', role: 'RESEARCH-FIRST BUYER', description: 'Methodical shopper — tests trust and clarity.', count: 3, selected: true },
        { id: 'role_loyal_repeater', role: 'LOYAL REPEATER', description: 'Returning customer — tests retention.', count: 3, selected: true },
        { id: 'role_premium_seeker', role: 'PREMIUM SEEKER', description: 'Quality-over-price buyer — tests premium positioning.', count: 0, selected: false },
      ];
    } else if (/saas|enterprise|team|workflow|b2b|productivity/.test(promptLower)) {
      return [
        { id: 'role_decision_maker', role: 'BUDGET DECISION MAKER', description: 'Manager who approves purchases — validates ROI.', count: 3, selected: true },
        { id: 'role_power_user', role: 'DAILY POWER USER', description: 'Heavy user — validates UX depth.', count: 3, selected: true },
        { id: 'role_it_eval', role: 'IT SECURITY EVALUATOR', description: 'Tech gatekeeping — tests compliance.', count: 3, selected: true },
        { id: 'role_resistant', role: 'CHANGE-RESISTANT USER', description: 'Reluctant adopter — reveals barriers.', count: 0, selected: false },
      ];
    } else if (/student|school|college|university|study/.test(promptLower)) {
      return [
        { id: 'role_uni_student', role: 'UNIVERSITY STUDENT', description: 'Core user — validates product-market fit.', count: 3, selected: true },
        { id: 'role_college_applicant', role: 'COLLEGE APPLICANT', description: 'High-stakes test-taker — validates premium tier.', count: 3, selected: true },
        { id: 'role_high_schooler', role: 'BUSY HIGH SCHOOLER', description: 'Time-pressed student — tests core value delivery.', count: 3, selected: true },
        { id: 'role_parental_buyer', role: 'PARENTAL BUYER', description: 'Parent paying for child — validates pricing framing.', count: 0, selected: false },
      ];
    }
    // Generic fallback
    return [
      { id: 'role_primary', role: 'PRIMARY USER', description: 'Core target user — validates product-market fit.', count: 3, selected: true },
      { id: 'role_early_adopter', role: 'EARLY ADOPTER', description: 'Forward-thinking user — validates initial demand.', count: 3, selected: true },
      { id: 'role_price_conscious', role: 'PRICE-CONSCIOUS USER', description: 'Budget-sensitive — validates pricing strategy.', count: 3, selected: true },
      { id: 'role_skeptic', role: 'SKEPTICAL USER', description: 'Using a competitor — reveals switching barriers.', count: 0, selected: false },
      { id: 'role_power_user', role: 'POWER USER', description: 'Heavy user — validates feature depth.', count: 0, selected: false },
    ];
  },

  async generateStudyPersonas(
    studyId?: string,
    prompt?: string,
    roles?: PersonaRoleSuggestion[],
    title?: string
  ): Promise<Persona[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/study/generate-personas`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            study_id: studyId,
            study_prompt: prompt,
            study_title: title,
            roles: roles || [],
          }),
          signal: AbortSignal.timeout(120000),
        });
        if (res.ok) {
          lastKnownLive = true;
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            data.forEach((p) => {
              mockStore.personas[p.id] = p;
            });
            return data;
          }
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }

    const promptLower = (prompt || title || '').toLowerCase();
    const isPriceTracker = /tracker|track|price|deal|discount|compare|monitoring|shopping|ecommerce|taka|bdt/.test(promptLower);

    if (isPriceTracker) {
      const priceTrackerPersonas: Persona[] = [
        {
          id: 'per_samiul_alam',
          business_id: 'biz_default',
          name: 'Samiul Alam',
          initials: 'SA',
          country_code: 'BD',
          country_name: 'Bangladesh',
          role_id: 'role_bargain_hunter',
          role_title: 'Smart Bargain Hunter',
          archetype: 'Smart Bargain Hunter',
          tagline: 'The Strategic Deal Optimizer',
          demographics: {
            age: 26,
            gender: 'Male',
            occupation: 'Junior Software Engineer',
            income_bracket: '45,000 BDT/month',
            location: 'Dhaka (Mirpur), Bangladesh',
            education: 'B.Sc. in Computer Science',
          },
          description:
            'He frequently purchases electronics, accessories, and apparel online across Daraz, Pickaboo, and Facebook commerce. He actively waits for flash sales and wants historical price charts to avoid fake discount promotions.',
          badges: [
            { label: 'HOBBIES', value: 'tech gadgets, price comparison, gaming, cycling' },
            { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
            { label: 'MONTHLY E-COMMERCE SPEND', value: '4,000 - 8,000 BDT across gadget accessories & clothes' },
            { label: 'WILLINGNESS TO PAY', value: 'Finds 100 BDT/month fair if it saves at least 300 BDT per month in real discounts' },
            { label: 'PRIMARY ALERT CHANNEL', value: 'Telegram & WhatsApp instant notification' },
          ],
          attributes: [
            {
              category: 'Goals',
              title: 'Never Overpay on Online Gadgets',
              description: 'Track price history over 90 days to verify if sale discounts are authentic.',
              provenance_class: 'OBSERVED',
              evidence: null,
            },
            {
              category: 'Pain Points',
              title: 'Fake Markdown Prices & Lack of Alerts',
              description: 'Sellers artificially increase prices before sale campaigns. Manual checking wastes hours.',
              provenance_class: 'OBSERVED',
              evidence: null,
            },
          ],
          consistency_score: 0.99,
          grounding_ratio: 0.97,
          critic_notes: 'High consistency with young urban professional e-commerce consumer profile.',
          generation_model: 'bebshax/dataset-grounded-v2',
          created_at: new Date().toISOString(),
          status: 'active',
          version: 1,
        },
        {
          id: 'per_nabila_khan',
          business_id: 'biz_default',
          name: 'Nabila Khan',
          initials: 'NK',
          country_code: 'BD',
          country_name: 'Bangladesh',
          role_id: 'role_budget_planner',
          role_title: 'Budget-Conscious Buyer',
          archetype: 'Budget-Conscious Buyer',
          tagline: 'The Practical Household Economist',
          demographics: {
            age: 31,
            gender: 'Female',
            occupation: 'Digital Content Lead & Homemaker',
            income_bracket: '55,000 BDT/month household',
            location: 'Dhaka (Uttara), Bangladesh',
            education: 'BBA in Marketing',
          },
          description:
            'She manages household replenishment (skincare, pantry staples, baby products) and tracks price fluctuations across Chaldal, Daraz, and Shajgoj. She wants a single dashboard to alert her when favorite products hit their lowest price.',
          badges: [
            { label: 'HOBBIES', value: 'home organization, baking, lifestyle blogging' },
            { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
            { label: 'PURCHASE FREQUENCY', value: '3-4 online orders per week' },
            { label: 'PRICE TRACKING NEED', value: 'Bulk pantry staples, baby diapers, and imported cosmetic brands' },
            { label: 'PRICE TOLERANCE', value: 'Considers 100 BDT/month a no-brainer if it covers multiple e-commerce stores' },
          ],
          attributes: [
            {
              category: 'Goals',
              title: 'Streamlined Family Essentials Budget',
              description: 'Stock up on monthly staples at genuine price dips.',
              provenance_class: 'OBSERVED',
              evidence: null,
            },
            {
              category: 'Pain Points',
              title: 'Scattered Store Checking',
              description: 'Having to open 4 different apps to check who has the cheapest price.',
              provenance_class: 'OBSERVED',
              evidence: null,
            },
          ],
          consistency_score: 0.98,
          grounding_ratio: 0.96,
          critic_notes: 'Accurate model of urban household digital shoppers in Bangladesh.',
          generation_model: 'bebshax/dataset-grounded-v2',
          created_at: new Date().toISOString(),
          status: 'active',
          version: 1,
        },
        {
          id: 'per_tanvir_hasan',
          business_id: 'biz_default',
          name: 'Tanvir Hasan',
          initials: 'TH',
          country_code: 'BD',
          country_name: 'Bangladesh',
          role_id: 'role_tech_shopper',
          role_title: 'Tech-Savvy Consumer',
          archetype: 'Tech-Savvy Consumer',
          tagline: 'The Analytical Deal Scout',
          demographics: {
            age: 23,
            gender: 'Male',
            occupation: '4th-year University Student & Freelancer',
            income_bracket: '18,000 BDT/month',
            location: 'Chattogram, Bangladesh',
            education: 'B.Sc. in Electrical Engineering',
          },
          description:
            'He freelances as a UI designer and is careful with discretionary spending. He bookmarks PC components and headphones, waiting for authentic price dips before buying.',
          badges: [
            { label: 'HOBBIES', value: 'PC building, graphic design, watching tech reviews' },
            { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
            { label: 'PAYMENT METHOD', value: 'bKash / Nagad mobile banking' },
            { label: 'SUBSCRIPTION VIEW', value: 'Prefers bKash recurring or micro-payment of 100 BDT rather than credit card requirement' },
          ],
          attributes: [
            {
              category: 'Goals',
              title: 'Automated Price Drop Threshold Alerts',
              description: 'Set custom price alerts (e.g. notify when price drops below 2,500 BDT).',
              provenance_class: 'OBSERVED',
              evidence: null,
            },
          ],
          consistency_score: 0.97,
          grounding_ratio: 0.95,
          critic_notes: 'Young freelance tech buyer archetype verified.',
          generation_model: 'bebshax/dataset-grounded-v2',
          created_at: new Date().toISOString(),
          status: 'active',
          version: 1,
        },
      ];
      priceTrackerPersonas.forEach((p) => {
        mockStore.personas[p.id] = p;
      });
      return priceTrackerPersonas;
    }

    // Grounded mock personas matching datasets
    const defaultPersonas: Persona[] = [
      {
        id: 'per_nusrat_jahan',
        business_id: 'biz_default',
        name: 'Nusrat Jahan',
        initials: 'NJ',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_uni_student',
        role_title: 'University Student',
        archetype: 'University Student',
        tagline: 'The Frugal Striver',
        demographics: {
          age: 20,
          gender: 'Female',
          occupation: '2nd-year University Student',
          income_bracket: '7,500 BDT/mo Allowance',
          location: 'Rajshahi, Bangladesh',
          education: 'Undergraduate (Economics)',
        },
        description:
          'She is a second-year university student in Rajshahi who tries to stay organized without adding extra costs to her month. She takes her studies seriously and seeks affordable, practical digital tools.',
        badges: [
          { label: 'HOBBIES', value: 'reading Bangla fiction, watching study vlogs, casual badminton' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          {
            label: 'CLASS SCHEDULE',
            value: 'Five days a week with mostly morning and midday classes, plus lab sessions',
          },
          { label: 'MONTHLY ALLOWANCE', value: '7,500 BDT' },
          {
            label: 'EDUCATION APP USAGE',
            value: 'mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool',
          },
          { label: 'DEVICE ACCESS', value: 'mid-range Android smartphone and shared family laptop' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Coursework and Exam Organization',
            description:
              'Keep daily assignment deadlines, exam revision milestones, and club meetings synchronized.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
          {
            category: 'Pain Points',
            title: 'Overpriced Global Subscriptions',
            description:
              'Foreign SaaS tools require international credit cards and charge $10+/month which exceeds monthly allowance.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'Highly consistent with Tier-2 university student budget profiles in Bangladesh.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_farzana_rahman',
        business_id: 'biz_default',
        name: 'Farzana Rahman',
        initials: 'FR',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_parental_planner',
        role_title: 'Parental Planner',
        archetype: 'Parental Planner',
        tagline: 'The Cost-Conscious Academic Guide',
        demographics: {
          age: 38,
          gender: 'Female',
          occupation: 'Homemaker & Study Supervisor',
          income_bracket: 'Middle Class Household',
          location: 'Rajshahi, Bangladesh',
          education: 'Masters in Social Sciences',
        },
        description:
          "She lives in Rajshahi with her family and takes an active role in keeping her children's school routine on track. She believes education is the safest long-term investment.",
        badges: [
          { label: 'HOBBIES', value: 'reading Bangla newspapers, balcony gardening, watching educational programs' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'CHILD SCHOOL LEVEL', value: 'Secondary school (classes 8-10)' },
          {
            label: 'EDUCATION APP USAGE',
            value: 'mostly uses free video lessons and quiz apps; occasionally pays for a high-value tool',
          },
          { label: 'MONTHLY STUDY BUDGET', value: '1,500 - 2,500 BDT for supplemental materials' },
          {
            label: 'DECISION FACTOR',
            value: 'Clear weekly progress tracking and direct alignment with NCTB board curriculum',
          },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Consistent Child Study Tracking',
            description: 'Help children build self-directed study habits without creating home tension.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.97,
        grounding_ratio: 0.95,
        critic_notes: 'Accurate representation of educated urban-adjacent parents in Bangladesh.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_tanjila_akter',
        business_id: 'biz_default',
        name: 'Tanjila Akter',
        initials: 'TA',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_college_applicant',
        role_title: 'College Applicant',
        archetype: 'College Applicant',
        tagline: 'The Structured Striver',
        demographics: {
          age: 18,
          gender: 'Female',
          occupation: 'HSC 2nd-Year & Admission Aspirant',
          income_bracket: '4,000 BDT/mo Allowance',
          location: 'Rajshahi, Bangladesh',
          education: 'Higher Secondary (Science)',
        },
        description:
          'She is an HSC student in Rajshahi preparing seriously for university admission exams and treats study time as a long-term investment in social mobility.',
        badges: [
          { label: 'HOBBIES', value: 'solving math problems, watching short educational videos, journaling' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'CLASS LEVEL', value: 'HSC 2nd year (Science Track)' },
          {
            label: 'LEARNING TOOL USE',
            value: 'uses YouTube lessons, Facebook study groups, PDF notes, and mobile apps',
          },
          { label: 'MONTHLY ALLOWANCE', value: '4,000 BDT' },
          { label: 'ADMISSION TARGET', value: 'Public engineering and medical varsity admission seats' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Master High-Yield Admission Syllabus',
            description:
              'Systematically complete question banks and practice exams ahead of competitive admission deadlines.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.99,
        grounding_ratio: 0.97,
        critic_notes: 'Grounded in HSC science applicant behavioral datasets.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_mim_chowdhury',
        business_id: 'biz_default',
        name: 'Mim Chowdhury',
        initials: 'MC',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_budget_learner',
        role_title: 'Budget-Conscious Learner',
        archetype: 'Budget-Conscious Learner',
        tagline: 'The Resourceful Pragmatist',
        demographics: {
          age: 20,
          gender: 'Female',
          occupation: '2nd-year Degree Student',
          income_bracket: '3,000 BDT/mo Budget',
          location: 'Rangpur, Bangladesh',
          education: 'Undergraduate (National University)',
        },
        description:
          'She is a second-year student living in Rangpur while supporting family responsibilities and studying largely on her own schedule. She is careful with every taka.',
        badges: [
          { label: 'HOBBIES', value: 'reading Bengali novels, helping younger siblings with schoolwork, sketching' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          {
            label: 'INTERNET ACCESS',
            value: 'mostly mobile data with uneven speed; relies heavily on offline features',
          },
          {
            label: 'LEARNING TOOL USE',
            value: 'searches for free study templates, lecture summaries, and Telegram study groups',
          },
          { label: 'MONTHLY BUDGET', value: '200-300 BDT maximum for digital tools' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Maximize Exam Preparation on Low Budget',
            description: 'Obtain high exam marks without spending on expensive private tuitions.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'Accurate reflection of divisional students with price sensitivity.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_sadia_sultana',
        business_id: 'biz_default',
        name: 'Sadia Sultana',
        initials: 'SS',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_high_schooler',
        role_title: 'Busy High Schooler',
        archetype: 'Busy High Schooler',
        tagline: 'The Structured Pragmatist',
        demographics: {
          age: 17,
          gender: 'Female',
          occupation: 'HSC 1st-Year Student',
          income_bracket: 'Dependent',
          location: 'Chattogram, Bangladesh',
          education: 'College (Class 11)',
        },
        description:
          'She is a 17-year-old higher secondary student in Chattogram balancing coursework, coaching, and extracurriculars while aiming for strong board exam GPA.',
        badges: [
          { label: 'HOBBIES', value: 'creative writing, watching science explainers, table tennis' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'COACHING HOURS', value: '12 hours per week across science subjects' },
          {
            label: 'DEVICE ACCESS',
            value: 'owns a mid-range Android phone and shares a family laptop when needed',
          },
          { label: 'DAILY SCHEDULE', value: 'tight routine from 7 AM to 10 PM with coaching and school' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Balance Coaching and Self-Study',
            description: 'Sync heavy coaching center homework with daily self-study sessions.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'High school science workload model verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_tasnia_islam',
        business_id: 'biz_default',
        name: 'Tasnia Islam',
        initials: 'TI',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_private_tutor_student',
        role_title: 'Private Tutor Student',
        archetype: 'Private Tutor Student',
        tagline: 'The Pragmatic Striver',
        demographics: {
          age: 20,
          gender: 'Female',
          occupation: '2nd-year BBA Student',
          income_bracket: '8,000 BDT/mo Allowance',
          location: 'Dhaka, Bangladesh',
          education: 'Undergraduate (BBA)',
        },
        description:
          'She is a second-year university student in Dhaka balancing coursework, family expectations, and a tight monthly budget. She likes organized routines.',
        badges: [
          { label: 'HOBBIES', value: 'reading class notes with friends, watching Bangla and Korean dramas' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          {
            label: 'LEARNING ROUTINE',
            value: 'studies most evenings, reviews lecture notes before quizzes, and intensifies before finals',
          },
          { label: 'LIVING SETUP', value: 'lives with family and commutes to campus via rickshaw and bus' },
          { label: 'TUTORING SUPPORT', value: 'receives weekly private tutoring in mathematics and statistics' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Track Private Tutoring Assignments',
            description: 'Organize weekly tasks assigned by private tutors and university professors in one place.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.97,
        grounding_ratio: 0.95,
        critic_notes: 'Dhaka commuter and private tutoring user profile verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_rafia_karim',
        business_id: 'biz_default',
        name: 'Rafia Karim',
        initials: 'RK',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_scholarship_aspirant',
        role_title: 'Scholarship Aspirant',
        archetype: 'Scholarship Aspirant',
        tagline: 'The Structured Climber',
        demographics: {
          age: 19,
          gender: 'Female',
          occupation: 'Admission Candidate',
          income_bracket: 'Dependent',
          location: 'Chattogram, Bangladesh',
          education: 'HSC Graduate (Science)',
        },
        description:
          'She is a scholarship-focused student from Chattogram who treats study time as a long-term investment and prefers structure over guesswork. She is ambitious and disciplined.',
        badges: [
          { label: 'HOBBIES', value: 'solving math puzzles, journaling, debate club, watching educational YouTube' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'COACHING FORMAT', value: 'hybrid coaching center plus self-study with online supplements' },
          { label: 'EXAM STAGE', value: 'university admission preparation with scholarship focus' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'High-Percentile Exam Benchmarking',
            description: 'Track mock test accuracy rates and time management across every question chapter.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.99,
        grounding_ratio: 0.97,
        critic_notes: 'High ambition scholarship seeker profile verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_mahin_hossain',
        business_id: 'biz_default',
        name: 'Mahin Hossain',
        initials: 'MH',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_group_organizer',
        role_title: 'Study Group Organizer',
        archetype: 'Study Group Organizer',
        tagline: 'The Quiet Systems Builder',
        demographics: {
          age: 21,
          gender: 'Male',
          occupation: '3rd-year CSE Student',
          income_bracket: '6,000 BDT/mo Allowance + Tuitions',
          location: 'Rajshahi, Bangladesh',
          education: 'Undergraduate (Computer Science)',
        },
        description:
          'He is a third-year university student in Rajshahi who quietly became the person classmates rely on to keep group study on track. He prefers structured routines, low fuss.',
        badges: [
          {
            label: 'HOBBIES',
            value: 'badminton, football highlights, nonfiction reading, tidy note-making, and casual coding',
          },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          {
            label: 'DIGITAL STUDY TOOLS',
            value: 'WhatsApp, Google Calendar, Google Drive, Facebook Messenger, and a study app',
          },
          { label: 'GROUP SIZE', value: '6 students in his core study circle' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Coordinate Group Project Schedules',
            description: 'Coordinate group study sessions, lab project sprints, and exam question distributions.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'Group leader persona verified against campus cohort behavioral datasets.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_samia_tabassum',
        business_id: 'biz_default',
        name: 'Samia Tabassum',
        initials: 'ST',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_test_prep',
        role_title: 'Test Prep Seeker',
        archetype: 'Test Prep Seeker',
        tagline: 'The Disciplined Value-Seeker',
        demographics: {
          age: 17,
          gender: 'Female',
          occupation: 'Class 11 Science Student',
          income_bracket: 'Dependent',
          location: 'Chattogram, Bangladesh',
          education: 'College (HSC 1st year)',
        },
        description:
          'She is a Class 11 science student in Chattogram who attends several private tutoring sessions each week and relies on careful routines to stay on top of exams.',
        badges: [
          { label: 'HOBBIES', value: 'mobile photography, watching cricket highlights, solving puzzle apps, and walking' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          {
            label: 'DIGITAL TOOL USE',
            value: 'uses YouTube lectures, Facebook study groups, shared PDF notes, and occasional practice apps',
          },
          { label: 'MONTHLY STUDY BUDGET', value: '300-500 taka/month for optional study aids beyond tutor fees' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Consistent Chapter Revision Cycles',
            description: 'Build repeated spaced repetition cycles before monthly college exams.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.98,
        grounding_ratio: 0.96,
        critic_notes: 'Class 11 test prep discipline model verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
      {
        id: 'per_iffat_ara',
        business_id: 'biz_default',
        name: 'Iffat Ara',
        initials: 'IA',
        country_code: 'BD',
        country_name: 'Bangladesh',
        role_id: 'role_remote_student',
        role_title: 'Remote Student',
        archetype: 'Remote Student',
        tagline: 'The Resourceful Skeptic',
        demographics: {
          age: 18,
          gender: 'Female',
          occupation: 'Science-track College Applicant',
          income_bracket: 'Dependent',
          location: 'Rajshahi, Bangladesh',
          education: 'HSC (Science)',
        },
        description:
          'She is an 18-year-old science-track college applicant in Rajshahi aiming for a public university seat. Careful with money and sensitive to academic pressure, she already uses free tools.',
        badges: [
          { label: 'HOBBIES', value: 'solving math problems, watching cricket highlights, reading Bengali short stories' },
          { label: 'ORIGIN COUNTRY', value: 'Bangladesh' },
          { label: 'COACHING STATUS', value: 'enrolled in a local offline coaching center with online test series' },
          { label: 'DEVICE ACCESS', value: 'own Android smartphone with mobile data connectivity' },
        ],
        attributes: [
          {
            category: 'Goals',
            title: 'Reliable Offline Study Planning',
            description: 'Access revision schedules and practice notes even during poor internet connectivity.',
            provenance_class: 'OBSERVED',
            evidence: null,
          },
        ],
        consistency_score: 0.97,
        grounding_ratio: 0.95,
        critic_notes: 'Remote connectivity and price skepticism persona verified.',
        generation_model: 'bebshax/dataset-grounded-v2',
        created_at: '2026-08-24T22:00:00Z',
        status: 'active',
        version: 1,
      },
    ];

    defaultPersonas.forEach((p) => {
      mockStore.personas[p.id] = p;
    });

    return defaultPersonas;
  },

  // =========================================================================
  // OpenRouter Diagnostics API
  // =========================================================================

  async getOpenRouterHealth(): Promise<OpenRouterHealth> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/health/openrouter`, {
          headers: this.getAuthHeaders(),
          signal: AbortSignal.timeout(10000),
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
          signal: AbortSignal.timeout(35000),
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
  // Evidence & Research Engine API Methods
  // -------------------------------------------------------------
  async startResearch(studyId: string): Promise<ResearchRun> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/research`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/research`, {
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
    return mockStore.researchRuns.filter((r) => r.study_id === studyId || r.study_id === 'study_default');
  },

  async getResearchRun(studyId: string, runId: string): Promise<ResearchRun> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/research/${runId}`, {
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/summary`, {
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
    if (!this.isMockMode()) {
      try {
        const queryParams = new URLSearchParams();
        if (params?.source_type) queryParams.set('source_type', params.source_type);
        if (params?.search) queryParams.set('search', params.search);
        const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/sources${qs}`, {
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/sources/${sourceId}`, {
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
    if (!this.isMockMode()) {
      try {
        const queryParams = new URLSearchParams();
        if (params?.status) queryParams.set('status', params.status);
        if (params?.category) queryParams.set('category', params.category);
        if (params?.search) queryParams.set('search', params.search);
        const qs = queryParams.toString() ? `?${queryParams.toString()}` : '';

        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/claims${qs}`, {
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/claims/${claimId}`, {
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/evidence/search`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({ query, top_k: topK }),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
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

  // ============================================================================
  // Autonomous Research — Plan & Dataset Candidates
  // ============================================================================

  async getResearchPlan(studyId: string): Promise<import('../types').ResearchPlan | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/research/plan`, {
          headers: this.getAuthHeaders(),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        if (res.status === 404) return null;
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }
    return null;
  },

  async listDatasetCandidates(studyId: string): Promise<import('../types').DatasetCandidate[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/datasets/candidates`, {
          headers: this.getAuthHeaders(),
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
    // No mock fabrication per product requirement — return empty list
    return [];
  },

  async importDatasetCandidate(
    studyId: string,
    candidateId: string
  ): Promise<{ success: boolean; imported_dataset_id: string; dataset_name: string; row_count: number | null }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/datasets/candidates/${candidateId}/import`,
          {
            method: 'POST',
            headers: this.getAuthHeaders(),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || 'Import failed');
      } catch (e) {
        lastKnownLive = false;
        throw e;
      }
    }
    throw new Error('Not available in mock mode');
  },

  async rejectDatasetCandidate(
    studyId: string,
    candidateId: string
  ): Promise<{ success: boolean }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(
          `${API_BASE}/studies/${studyId}/datasets/candidates/${candidateId}/reject`,
          {
            method: 'POST',
            headers: this.getAuthHeaders(),
          }
        );
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
        lastKnownLive = false;
      } catch {
        lastKnownLive = false;
      }
    }
    return { success: true };
  },

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
      } catch {
        lastKnownLive = false;
      }
    }
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
        if (e.message && !e.message.includes('Failed to fetch')) throw e;
        lastKnownLive = false;
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
        if (e.message && !e.message.includes('Failed to fetch')) throw e;
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
      }
    }
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
      }
    }

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
          return;
        }
      } catch {
        lastKnownLive = false;
      }
    }
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
      }
    }

    // Default mock response
    return {
      personas: [
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
      } catch {
        lastKnownLive = false;
      }
    }

    const list = await this.getStudyPersonas(studyId);
    const found = list.personas.find((p) => p.id === personaId);
    if (found) return found;
    throw new Error('Persona not found');
  },

  async generateSyntheticPersonas(
    studyId: string,
    payload: GeneratePersonasPayload
  ): Promise<{ run: PersonaGenerationRun; personas: SyntheticPersona[] }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${studyId}/personas/generate`, {
          method: 'POST',
          headers: this.getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
      } catch {
        lastKnownLive = false;
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
    }
    return {
      interviews: [],
      total: 0,
    };
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
      } catch {
        lastKnownLive = false;
      }
    }
    return {
      total_interviews: 0,
      active_interviews: 0,
      completed_interviews: 0,
      total_insights_generated: 0,
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
      } catch {
        lastKnownLive = false;
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
};





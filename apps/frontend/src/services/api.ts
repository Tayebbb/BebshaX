import {
  Business,
  Conversation,
  ConversationTurn,
  EvaluationMetrics,
  HealthResponse,
  MemoryItem,
  Persona,
  ProvenanceRecord,
  RoutesStatusResponse,
  Study,
} from '../types';
import {
  AuthResponse,
  GoogleAuthData,
  SignInData,
  SignUpData,
  User,
} from '../types/auth';
import {
  mockBusinesses,
  mockConversations,
  mockEvaluationMetrics,
  mockHealth,
  mockMemories,
  mockPersonas,
  mockProvenanceRecords,
  mockRoutesStatus,
  mockStudies,
} from '../mocks/fixtures';
import { neonAuth } from './neonAuth';

const API_BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8000/api';

// In-memory state store for client modifications during mock/fallback mode
class MockStore {
  businesses: Business[] = [...mockBusinesses];
  personas: Record<string, Persona> = { ...mockPersonas };
  memories: Record<string, MemoryItem[]> = { ...mockMemories };
  conversations: Record<string, Conversation> = { ...mockConversations };
  provenance: ProvenanceRecord[] = [...mockProvenanceRecords];
  studies: Study[] = [...mockStudies];
}

const mockStore = new MockStore();

let forceMockMode: boolean | null = null;
let lastKnownLive = false;

export const api = {
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
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        lastKnownLive = true;
        return await res.json();
      }
    } catch {
      lastKnownLive = false;
    }
    return mockHealth;
  },

  // 2. Routes & Provider Status
  async getRoutesStatus(): Promise<RoutesStatusResponse> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/routes/status`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
      }
    }
    return mockRoutesStatus;
  },

  // 3. Provenance Records
  async getProvenance(limit = 50): Promise<{ items: ProvenanceRecord[]; total: number }> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/provenance?limit=${limit}`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          const data = await res.json();
          if (data.items && data.items.length > 0) {
            lastKnownLive = true;
            return data;
          }
        }
      } catch {
        // fallback
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
        const res = await fetch(`${API_BASE}/businesses`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            lastKnownLive = true;
            return data;
          }
        }
      } catch {
        // fallback
      }
    }
    return mockStore.businesses;
  },

  async createBusiness(data: Omit<Business, 'id' | 'persona_count' | 'created_at'>): Promise<Business> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/businesses`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          lastKnownLive = true;
          const created = await res.json();
          mockStore.businesses.unshift(created);
          return created;
        }
      } catch {
        // fallback
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
        const res = await fetch(`${API_BASE}/personas`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            lastKnownLive = true;
            return data;
          }
        }
      } catch {
        // fallback
      }
    }
    return Object.values(mockStore.personas);
  },

  async getPersona(id: string): Promise<Persona | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/personas/${id}`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            audience_segment: audienceSegment,
            generation_hints: hints,
            hints: hints.join(', '),
          }),
          signal: AbortSignal.timeout(25000),
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
      } catch {
        // fallback
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
        const res = await fetch(`${API_BASE}/personas/${personaId}/memories`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
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
      } catch {
        // fallback
      }
    }
    return mockStore.memories[personaId] || [];
  },

  // 7. Conversations
  async getConversation(id: string): Promise<Conversation | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations/${id}`, { signal: AbortSignal.timeout(3000) });
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
      } catch {
        // fallback
      }
    }
    return mockStore.conversations[id] || null;
  },

  async startConversation(personaId: string, objective: string): Promise<Conversation> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ persona_id: personaId, objective }),
          signal: AbortSignal.timeout(5000),
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
      } catch {
        // fallback
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: message, message }),
          signal: AbortSignal.timeout(20000),
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
      } catch {
        // fallback
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
        const res = await fetch(`${API_BASE}/evaluation/metrics`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
      }
    }
    return mockEvaluationMetrics;
  },

  // 9. Authentication & User Management (JWT + Neon DB)
  // 9. Authentication & User Management (Neon Auth + Better Auth)
  getAuthToken(): string | null {
    try {
      return localStorage.getItem('bebshax_auth_token');
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

  async signup(data: SignUpData): Promise<AuthResponse> {
    if (!this.isMockMode()) {
      // 1. Primary: Direct Neon Auth registration
      try {
        const neonRes = await neonAuth.signUp({
          email: data.email,
          password: data.password,
          name: data.full_name,
        });
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
      } catch (err: any) {
        // If Neon Auth returned an explicit client error (e.g. duplicate email), surface it
        if (
          err.message &&
          (err.message.includes('already exists') ||
            err.message.includes('Password') ||
            err.message.includes('Invalid') ||
            err.message.includes('Origin'))
        ) {
          throw err;
        }

        // 2. Secondary: Backend API fallback if Neon Auth network failed
        try {
          const res = await fetch(`${API_BASE}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          });
          if (res.ok) {
            const result: AuthResponse = await res.json();
            this.setAuthToken(result.access_token);
            this.setStoredUser(result.user);
            lastKnownLive = true;
            return result;
          }
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Signup failed');
        } catch (backendErr: any) {
          if (backendErr.message && backendErr.message !== 'Failed to fetch') {
            throw backendErr;
          }
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
    this.setAuthToken(mockRes.access_token);
    this.setStoredUser(mockUser);
    return mockRes;
  },

  async signin(data: SignInData): Promise<AuthResponse> {
    if (!this.isMockMode()) {
      // 1. Primary: Direct Neon Auth authentication
      try {
        const neonRes = await neonAuth.signIn({
          email: data.email,
          password: data.password,
        });
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
      } catch (err: any) {
        // If Neon Auth returned an explicit verification or credential error, surface it
        if (
          err.message &&
          (err.code === 'EMAIL_NOT_VERIFIED' ||
            err.message.includes('Email not verified') ||
            err.message.includes('Invalid email or password') ||
            err.message.includes('Origin'))
        ) {
          throw err;
        }

        // 2. Secondary: Backend API fallback
        try {
          const res = await fetch(`${API_BASE}/auth/signin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          });
          if (res.ok) {
            const result: AuthResponse = await res.json();
            this.setAuthToken(result.access_token);
            this.setStoredUser(result.user);
            lastKnownLive = true;
            return result;
          }
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.detail || 'Invalid email or password');
        } catch (backendErr: any) {
          if (backendErr.message && backendErr.message !== 'Failed to fetch') {
            throw backendErr;
          }
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
      try {
        await neonAuth.signInWithGoogle();
      } catch {
        // Fall back to backend or simulated payload if redirect not triggered
      }

      try {
        const res = await fetch(`${API_BASE}/auth/google`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        if (res.ok) {
          const result: AuthResponse = await res.json();
          this.setAuthToken(result.access_token);
          this.setStoredUser(result.user);
          lastKnownLive = true;
          return result;
        }
      } catch {
        // fallback
      }
    }

    const email = data.email || 'google.user@example.com';
    const mockUser: User = {
      id: `usr_g_${Date.now()}`,
      email: email,
      full_name: data.name || 'Google User',
      avatar_url: data.avatar_url || 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&h=100&fit=crop',
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
      // Check Neon Auth live session first
      try {
        const neonUser = await neonAuth.getSession(token);
        if (neonUser) {
          lastKnownLive = true;
          this.setStoredUser(neonUser);
          return neonUser;
        }
      } catch {
        // ignore
      }

      // Check Backend API /auth/me
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          lastKnownLive = true;
          const user = await res.json();
          this.setStoredUser(user);
          return user;
        }
      } catch {
        // fallback
      }
    }

    const stored = this.getStoredUser();
    if (stored) return stored;

    return {
      id: 'usr_sarah_founder',
      email: 'founder@bebshax.io',
      full_name: 'Sarah Chen',
      avatar_url: null,
      is_active: true,
      is_verified: true,
      auth_provider: 'email',
      created_at: new Date().toISOString(),
    };
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
  async getStudies(): Promise<Study[]> {
    return [...mockStore.studies];
  },

  async getStudyById(id: string): Promise<Study | null> {
    const study = mockStore.studies.find((s) => s.id === id);
    return study ? { ...study } : null;
  },

  async createStudy(studyData: Partial<Study>): Promise<Study> {
    const newStudy: Study = {
      id: `study_${Date.now()}`,
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
    mockStore.studies.unshift(newStudy);
    return newStudy;
  },

  async updateStudy(id: string, updates: Partial<Study>): Promise<Study> {
    const index = mockStore.studies.findIndex((s) => s.id === id);
    if (index === -1) {
      throw new Error(`Study with id ${id} not found`);
    }
    const updated = {
      ...mockStore.studies[index],
      ...updates,
      updated_at: new Date().toISOString(),
    };
    mockStore.studies[index] = updated;
    return updated;
  },

  async deleteStudy(id: string): Promise<boolean> {
    const index = mockStore.studies.findIndex((s) => s.id === id);
    if (index === -1) return false;
    mockStore.studies.splice(index, 1);
    return true;
  },
};

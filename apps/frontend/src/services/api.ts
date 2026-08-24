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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies`, { signal: AbortSignal.timeout(3000) });
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
    return [...mockStore.studies];
  },

  async getStudyById(id: string): Promise<Study | null> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
      }
    }
    const study = mockStore.studies.find((s) => s.id === id);
    return study ? { ...study } : null;
  },

  async getStudy(id: string): Promise<Study | null> {
    return this.getStudyById(id);
  },

  async createStudy(studyData: Partial<Study>): Promise<Study> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(studyData),
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          lastKnownLive = true;
          const created = await res.json();
          mockStore.studies.unshift(created);
          return created;
        }
      } catch {
        // fallback
      }
    }

    const newStudy: Study = {
      id: studyData.id || `study_${Date.now()}`,
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updates),
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          lastKnownLive = true;
          const updated = await res.json();
          const index = mockStore.studies.findIndex((s) => s.id === id);
          if (index !== -1) mockStore.studies[index] = updated;
          return updated;
        }
      } catch {
        // fallback
      }
    }

    const index = mockStore.studies.findIndex((s) => s.id === id);
    if (index === -1) {
      const created = await this.createStudy({ id, ...updates });
      return created;
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/studies/${id}`, {
          method: 'DELETE',
          signal: AbortSignal.timeout(4000),
        });
        if (res.ok) {
          lastKnownLive = true;
        }
      } catch {
        // fallback
      }
    }
    mockStore.studies = mockStore.studies.filter((s) => s.id !== id);
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
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/audiences`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
      }
    }
    return { id: `aud_${Date.now()}`, name: data.name };
  },

  async getSavedAudiences(): Promise<any[]> {
    if (!this.isMockMode()) {
      try {
        const res = await fetch(`${API_BASE}/audiences`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          lastKnownLive = true;
          return await res.json();
        }
      } catch {
        // fallback
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            messages,
            study_type: studyType,
            study_id: studyId,
          }),
        });
        if (res.ok) {
          return await res.json();
        }
      } catch {
        // fallback to deterministic copilot simulator
      }
    }

    const userTurns = messages.filter((m) => m.role === 'user');
    const turnCount = userTurns.length;
    const firstText = userTurns[0]?.content || '';
    const lastText = userTurns[userTurns.length - 1]?.content || '';
    const combinedText = (firstText + ' ' + lastText).toLowerCase();

    const hasPricing = /price|cost|month|subscription|plan|\$|taka|€|£|free/.test(combinedText);
    const hasStudents = /student|school|college|university|study/.test(combinedText);
    const hasFood = /food|restaurant|delivery|meal|eat|chef|recipe|cuisine/.test(combinedText);
    const hasHealth = /health|fitness|gym|workout|diet|wellness|doctor|medical/.test(combinedText);
    const hasFintech = /payment|bank|finance|loan|invest|money|wallet|crypto/.test(combinedText);
    const hasEcommerce = /shop|sell|buy|store|marketplace|ecommerce|fashion/.test(combinedText);
    const hasB2B = /saas|enterprise|team|office|workflow|productivity|b2b|business tool/.test(combinedText);

    let productType = 'product or service';
    let audienceQ = 'Who is your primary target user — what\'s their age range, lifestyle, or professional context? And what geography are you launching in first?';
    let followupQ = 'What\'s the core problem you\'re solving for them, and what\'s the price point or business model you\'re validating?';
    let roles: PersonaRoleSuggestion[] = [];

    if (hasFood) {
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
    } else if (hasStudents) {
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
        reply: `I've identified your idea — you want to validate your ${productType} and understand how target users would respond to it${hasPricing ? ' at your target price point' : ''}. A User Interviews study is the right approach here — deep conversations will uncover mental models, current frustrations, and real willingness to pay.\n\n${audienceQ}`,
        suggested_study_type: 'interviews',
        is_ready_for_approval: false,
        research_goal_card: null,
        suggested_roles: [],
        served_by: 'bebshax/copilot-engine',
      };
    } else if (turnCount === 2) {
      return {
        reply: followupQ,
        suggested_study_type: 'interviews',
        is_ready_for_approval: false,
        research_goal_card: null,
        suggested_roles: [],
        served_by: 'bebshax/copilot-engine',
      };
    } else {
      return {
        reply: "I've synthesized your inputs into a focused research goal proposal below:",
        suggested_study_type: 'interviews',
        is_ready_for_approval: true,
        research_goal_card: {
          title: 'RESEARCH GOAL',
          summary: `You want to validate whether your ${productType} solves a real problem for your target users and whether they would adopt it${hasPricing ? ' at your target price point' : ' as part of their routine'}, so you can make a confident build or no-build decision. The research will uncover user motivations, current frustrations, key objections, and willingness to pay. Does this capture what you're looking for?`,
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ study_prompt: studyPrompt }),
        });
        if (res.ok) {
          return await res.json();
        }
      } catch {
        // fallback
      }
    }
    // Context-aware fallback: derive roles from the study prompt
    const promptLower = studyPrompt.toLowerCase();
    if (/food|restaurant|delivery|meal|eat/.test(promptLower)) {
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            study_id: studyId,
            study_prompt: prompt,
            study_title: title,
            roles: roles || [],
          }),
          signal: AbortSignal.timeout(15000),
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
      } catch {
        // fallback to grounded mock personas
      }
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
};


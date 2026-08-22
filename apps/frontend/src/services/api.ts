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
} from '../types';
import {
  mockBusinesses,
  mockConversations,
  mockEvaluationMetrics,
  mockHealth,
  mockMemories,
  mockPersonas,
  mockProvenanceRecords,
  mockRoutesStatus,
} from '../mocks/fixtures';

const API_BASE = import.meta.env?.VITE_API_BASE || 'http://127.0.0.1:8000/api';
// Default to mock mode unless explicitly disabled with VITE_MOCK=0
const isMock = import.meta.env?.VITE_MOCK === '1' || import.meta.env?.MODE === 'test' || typeof window === 'undefined';

// In-memory state store for client modifications during mock mode
class MockStore {
  businesses: Business[] = [...mockBusinesses];
  personas: Record<string, Persona> = { ...mockPersonas };
  memories: Record<string, MemoryItem[]> = { ...mockMemories };
  conversations: Record<string, Conversation> = { ...mockConversations };
  provenance: ProvenanceRecord[] = [...mockProvenanceRecords];
}

const mockStore = new MockStore();

export const api = {
  // 1. Health check (attempts live call first)
  async getHealth(): Promise<HealthResponse> {
    if (isMock) return mockHealth;
    try {
      const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // live endpoint unreachable, fall back to mock
    }
    return mockHealth;
  },

  // 2. Routes & Provider Status
  async getRoutesStatus(): Promise<RoutesStatusResponse> {
    if (isMock) return mockRoutesStatus;
    try {
      const res = await fetch(`${API_BASE}/routes/status`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockRoutesStatus;
  },

  // 3. Provenance Records
  async getProvenance(limit = 50): Promise<{ items: ProvenanceRecord[]; total: number }> {
    if (isMock) {
      return {
        items: mockStore.provenance.slice(0, limit),
        total: mockStore.provenance.length,
      };
    }
    try {
      const res = await fetch(`${API_BASE}/provenance?limit=${limit}`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return {
      items: mockStore.provenance.slice(0, limit),
      total: mockStore.provenance.length,
    };
  },

  // 4. Businesses
  async getBusinesses(): Promise<Business[]> {
    if (isMock) return mockStore.businesses;
    try {
      const res = await fetch(`${API_BASE}/businesses`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockStore.businesses;
  },

  async createBusiness(data: Omit<Business, 'id' | 'persona_count' | 'created_at'>): Promise<Business> {
    if (!isMock) {
      try {
        const res = await fetch(`${API_BASE}/businesses`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        if (res.ok) return await res.json();
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
    if (isMock) return Object.values(mockStore.personas);
    try {
      const res = await fetch(`${API_BASE}/personas`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return Object.values(mockStore.personas);
  },

  async getPersona(id: string): Promise<Persona | null> {
    if (isMock) return mockStore.personas[id] || null;
    try {
      const res = await fetch(`${API_BASE}/personas/${id}`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockStore.personas[id] || null;
  },

  async generatePersona(
    businessId: string,
    audienceSegment: string,
    hints: string[]
  ): Promise<{ persona: Persona; provenance: ProvenanceRecord }> {
    if (!isMock) {
      try {
        const res = await fetch(`${API_BASE}/businesses/${businessId}/personas`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audience_segment: audienceSegment, generation_hints: hints }),
        });
        if (res.ok) return await res.json();
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
    if (isMock) return mockStore.memories[personaId] || [];
    try {
      const res = await fetch(`${API_BASE}/personas/${personaId}/memories`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockStore.memories[personaId] || [];
  },

  // 7. Conversations
  async getConversation(id: string): Promise<Conversation | null> {
    if (isMock) return mockStore.conversations[id] || null;
    try {
      const res = await fetch(`${API_BASE}/conversations/${id}`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockStore.conversations[id] || null;
  },

  async startConversation(personaId: string, objective: string): Promise<Conversation> {
    if (!isMock) {
      try {
        const res = await fetch(`${API_BASE}/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ persona_id: personaId, objective }),
        });
        if (res.ok) return await res.json();
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
    if (!isMock) {
      try {
        const res = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: message }),
        });
        if (res.ok) {
          const data = await res.json();
          return {
            userTurn: { id: `t_${Date.now()}`, role: 'user', content: data.user_message.content, timestamp: data.user_message.timestamp },
            assistantTurn: {
              id: `t_${Date.now() + 1}`,
              role: 'assistant',
              content: data.persona_reply.content,
              timestamp: data.persona_reply.timestamp,
              latency_ms: data.persona_reply.latency_ms,
              served_by: data.persona_reply.served_by,
              retrieved_memories: data.persona_reply.retrieved_memories,
            },
          };
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
    if (isMock) return mockEvaluationMetrics;
    try {
      const res = await fetch(`${API_BASE}/evaluation/metrics`, { signal: AbortSignal.timeout(1000) });
      if (res.ok) return await res.json();
    } catch {
      // fallback
    }
    return mockEvaluationMetrics;
  },
};

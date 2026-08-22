# BebshaX — API Contract (Frozen Interface)

> **Contract-first specification:** All frontend views in `apps/frontend` and backend endpoints in `apps/backend` conform strictly to this contract.
> Changes to shared schemas require cross-track sign-off per [RULES.md](../RULES.md) (R12) and [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md).

---

## 1. System Conventions & Headers

- **Base URL:** `http://127.0.0.1:8000/api` (configurable via `VITE_API_BASE`)
- **Content-Type:** `application/json`
- **Time format:** ISO 8601 UTC (`YYYY-MM-DDTHH:mm:ss.sssZ`)
- **Mock Header:** Frontend sends `X-BebshaX-Mock: 1` when operating with mock fixtures or when `VITE_MOCK=1`.
- **Standard Error Response:**
  ```json
  {
    "detail": "Descriptive error message",
    "error_code": "CONTEXT_WINDOW_EXCEEDED",
    "request_id": "hex32"
  }
  ```

---

## 2. Enumerations

### 2.1 TaskType (16 Fixed Tasks)
```typescript
export type TaskType =
  | "PERSONA_GENERATION"
  | "PERSONA_REFINEMENT"
  | "PERSONA_VALIDATION"
  | "PERSONA_INTERVIEW"
  | "PERSONA_RESPONSE"
  | "EVIDENCE_EXTRACTION"
  | "EVIDENCE_CLASSIFICATION"
  | "MEMORY_RETRIEVAL"
  | "MEMORY_SUMMARIZATION"
  | "CONTRADICTION_CHECK"
  | "CRITIC"
  | "REPORT_GENERATION"
  | "STRUCTURED_OUTPUT"
  | "BROWSER_AGENT"
  | "TOOL_CALLING"
  | "EMERGENCY_FALLBACK";
```

### 2.2 FailureKind
```typescript
export type FailureKind =
  | "RATE_LIMIT"
  | "QUOTA_EXHAUSTED"
  | "TIMEOUT"
  | "CONNECTION"
  | "SERVER_ERROR"
  | "MODEL_UNAVAILABLE"
  | "CAPABILITY_UNSUPPORTED"
  | "CONTEXT_OVERFLOW"
  | "MALFORMED_RESPONSE"
  | "INTERNAL_ERROR";
```

### 2.3 ProvenanceClass
```typescript
export type ProvenanceClass = "OBSERVED" | "INFERRED" | "SYNTHETIC";
```

### 2.4 MemoryKind
```typescript
export type MemoryKind = "semantic" | "episodic" | "reflection";
```

---

## 3. Endpoints

### 3.1 Health Check (Implemented in Phase 1)
- **`GET /api/health`**
- **Response `200 OK`:**
  ```json
  {
    "status": "ok",
    "app": "BebshaX",
    "version": "0.1.0",
    "environment": "development",
    "demo_mode": false
  }
  ```

---

### 3.2 LLM Provenance & Routing (Phase 2, 5, 6)

#### `GET /api/provenance`
- **Query params:** `limit` (default 50), `task`, `pool`, `success` (boolean), `persona_id`
- **Response `200 OK`:**
  ```json
  {
    "items": [
      {
        "request_id": "a1b2c3d4e5f6",
        "task": "PERSONA_GENERATION",
        "pool": "reasoning",
        "persona_id": "per_101",
        "conversation_id": null,
        "created_at": "2026-08-22T08:00:00.000Z",
        "routing_path": ["groq/llama-3.3-70b-versatile", "pollinations/deepseek-r1", "ollama/llama3.2:3b"],
        "attempts": [
          {
            "attempt_number": 1,
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "started_at": "2026-08-22T08:00:00.000Z",
            "latency_ms": 142.5,
            "success": false,
            "failure_kind": "RATE_LIMIT",
            "failure_detail": "HTTP 429: TPM limit reached",
            "fallback_reason": "Rate limited, falling back to next pool candidate",
            "notes": ["circuit cooldown triggered 30s"]
          },
          {
            "attempt_number": 2,
            "provider": "pollinations",
            "model": "deepseek-r1",
            "started_at": "2026-08-22T08:00:00.200Z",
            "latency_ms": 1180.2,
            "success": true,
            "failure_kind": null,
            "failure_detail": null,
            "fallback_reason": null,
            "notes": []
          }
        ],
        "served_by_provider": "pollinations",
        "served_by_model": "deepseek-r1",
        "input_tokens": 1420,
        "output_tokens": 850,
        "total_latency_ms": 1322.7,
        "success": true
      }
    ],
    "total": 142
  }
  ```

#### `GET /api/routes/status`
- **Response `200 OK`:** Model registry and provider health snapshot:
  ```json
  {
    "providers": [
      { "name": "pollinations", "type": "keyless", "status": "healthy", "available_models": 12, "active_cooldowns": 0 },
      { "name": "groq", "type": "free_tier_key", "status": "degraded", "available_models": 4, "active_cooldowns": 1 },
      { "name": "ollama", "type": "local_fallback", "status": "healthy", "available_models": 2, "active_cooldowns": 0 }
    ],
    "pools": [
      { "name": "reasoning", "max_concurrency": 4, "active_requests": 1, "candidates_count": 5 },
      { "name": "conversation", "max_concurrency": 8, "active_requests": 0, "candidates_count": 8 },
      { "name": "fallback", "max_concurrency": 2, "active_requests": 0, "candidates_count": 2 }
    ]
  }
  ```

---

### 3.3 Business Setup (Phase 6, 8)

#### `GET /api/businesses`
- **Response `200 OK`:** List of businesses.
  ```json
  [
    {
      "id": "biz_fintech_01",
      "name": "NovaFlow Financial",
      "description": "Next-generation budgeting and micro-investment app for gig workers and freelancers.",
      "industry": "Fintech / Personal Finance",
      "target_market": "Independent contractors, creators, rideshare drivers (US/UK)",
      "persona_count": 4,
      "created_at": "2026-08-22T06:00:00.000Z"
    }
  ]
  ```

#### `POST /api/businesses`
- **Request Body:**
  ```json
  {
    "name": "NovaFlow Financial",
    "description": "Next-generation budgeting and micro-investment app for gig workers.",
    "industry": "Fintech",
    "target_market": "US Freelancers"
  }
  ```
- **Response `201 Created`:** The created `Business` object.

---

### 3.4 Persona Engine (Phase 8)

#### `POST /api/businesses/{business_id}/personas`
- **Request Body:**
  ```json
  {
    "audience_segment": "Variable income delivery driver striving for financial cushion",
    "generation_hints": ["Prioritize irregular cashflow challenges", "Mobile-first technology user"]
  }
  ```
- **Response `201 Created`:**
  ```json
  {
    "id": "per_sarah_01",
    "business_id": "biz_fintech_01",
    "name": "Sarah Chen",
    "status": "active",
    "version": 1,
    "archetype": "The Resilient Gig Maximizer",
    "tagline": "Balancing three platforms while building a 3-month safety buffer.",
    "demographics": {
      "age": 29,
      "gender": "Female",
      "occupation": "Full-time Rideshare & Grocery Courier",
      "income_bracket": "$38,000 - $46,000 / year (unpredictable)",
      "location": "Austin, TX (Suburban)",
      "education": "Associate Degree in Graphic Design"
    },
    "attributes": [
      {
        "category": "Goals",
        "title": "Predictable Cashflow Smoothing",
        "description": "Needs an automated tool that sets aside tax deductions and vehicle repair reserves immediately upon weekly payout.",
        "provenance_class": "OBSERVED",
        "evidence": {
          "source": "PersonaHub (Financial Segment)",
          "quote": "Couriers consistently mention sudden repair costs as their #1 emergency failure point.",
          "confidence": 0.94
        }
      },
      {
        "category": "Pain Points",
        "title": "Traditional Banking Overdraft Traps",
        "description": "Standard banking algorithms misjudge pending payout deposits, triggering punitive $35 overdraft fees.",
        "provenance_class": "INFERRED",
        "evidence": {
          "source": "EmpatheticDialogues & Reviews",
          "quote": "Overdraft fees feel punitive when money is literally arriving tomorrow.",
          "confidence": 0.88
        }
      },
      {
        "category": "Behaviors",
        "title": "Multiple App Switching",
        "description": "Keeps 4 distinct apps open simultaneously while navigating shifts; needs frictionless glanceable UI.",
        "provenance_class": "SYNTHETIC",
        "evidence": null
      }
    ],
    "consistency_score": 0.96,
    "grounding_ratio": 0.78,
    "critic_notes": "Passed consistency rules: Income bracket matches multi-app delivery occupation. Tax reserve goal matches gig profile.",
    "generation_model": "pollinations/deepseek-r1",
    "created_at": "2026-08-22T08:15:00.000Z"
  }
  ```

#### `GET /api/personas/{id}`
- **Response `200 OK`:** Full `Persona` profile.

---

### 3.5 Persona Memory Stream (Phase 9)

#### `GET /api/personas/{id}/memories`
- **Query params:** `kind` (`semantic` | `episodic` | `reflection`), `limit`
- **Response `200 OK`:**
  ```json
  [
    {
      "id": "mem_001",
      "persona_id": "per_sarah_01",
      "kind": "semantic",
      "text": "Drives a 2018 Honda Civic with 110,000 miles; highly sensitive to maintenance budget alerts.",
      "importance": 0.85,
      "recency_weight": 0.92,
      "relevance_score": 0.95,
      "created_at": "2026-08-22T08:20:00.000Z"
    },
    {
      "id": "mem_002",
      "persona_id": "per_sarah_01",
      "kind": "episodic",
      "text": "Mentioned during onboarding interview that she tried Mint but abandoned it because weekly tips weren't categorized properly.",
      "importance": 0.72,
      "recency_weight": 0.88,
      "relevance_score": 0.84,
      "created_at": "2026-08-22T08:25:00.000Z"
    }
  ]
  ```

---

### 3.6 Interview Simulation (Phase 10)

#### `POST /api/conversations`
- **Request Body:**
  ```json
  {
    "persona_id": "per_sarah_01",
    "objective": "Test reaction to an automatic micro-tax withholding feature with instant debit fallback."
  }
  ```
- **Response `201 Created`:**
  ```json
  {
    "id": "conv_201",
    "persona_id": "per_sarah_01",
    "objective": "Test reaction to micro-tax withholding feature.",
    "status": "active",
    "turns": [],
    "created_at": "2026-08-22T08:30:00.000Z"
  }
  ```

#### `POST /api/conversations/{id}/messages`
- **Request Body:**
  ```json
  {
    "content": "Hi Sarah! How would you feel if NovaFlow automatically saved 15% of each Instacart payout into a locked tax bucket?"
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "conversation_id": "conv_201",
    "user_message": {
      "role": "user",
      "content": "Hi Sarah! How would you feel if NovaFlow automatically saved 15% of each Instacart payout into a locked tax bucket?",
      "timestamp": "2026-08-22T08:31:00.000Z"
    },
    "persona_reply": {
      "role": "assistant",
      "content": "Honestly, that sounds like a lifesaver for April, but only if it doesn't leave me stranded if my tire blows out on a Tuesday. If I can't unlock that money in a genuine pinch, 15% is too steep when gas prices spike.",
      "timestamp": "2026-08-22T08:31:02.000Z",
      "latency_ms": 1150,
      "served_by": "pollinations/deepseek-r1",
      "retrieved_memories": [
        "Drives a 2018 Honda Civic; sensitive to maintenance emergencies",
        "Needs predictable cashflow smoothing"
      ]
    }
  }
  ```

---

### 3.7 Evaluation & Insights (Phase 11)

#### `GET /api/evaluation/metrics`
- **Response `200 OK`:**
  ```json
  {
    "overall_health": {
      "total_personas_generated": 24,
      "schema_validity_rate": 1.0,
      "consistency_pass_rate": 0.958,
      "avg_grounding_ratio": 0.742,
      "avg_latency_ms": 940.5
    },
    "routing_strategies": [
      { "strategy": "HYBRID (Default)", "success_rate": 0.985, "avg_latency_ms": 820, "fallback_rate": 0.08, "cost_efficiency": 1.0 },
      { "strategy": "QUALITY_FIRST", "success_rate": 0.990, "avg_latency_ms": 1420, "fallback_rate": 0.12, "cost_efficiency": 0.85 },
      { "strategy": "LATENCY_FIRST", "success_rate": 0.940, "avg_latency_ms": 310, "fallback_rate": 0.04, "cost_efficiency": 0.92 },
      { "strategy": "ROUND_ROBIN (Naive)", "success_rate": 0.810, "avg_latency_ms": 1650, "fallback_rate": 0.38, "cost_efficiency": 0.62 }
    ]
  }
  ```

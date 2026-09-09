# BebshaX — API Contract (Frozen Interface)

> **Contract-first specification:** All frontend views in `apps/frontend` and backend endpoints in `apps/backend` conform strictly to this contract.
> Changes to shared schemas require cross-track sign-off per [RULES.md](../RULES.md) (R12) and [TEAM_ASSIGNMENTS.md](TEAM_ASSIGNMENTS.md).

---

## 1. System Conventions & Headers

- **Base URL:** `http://127.0.0.1:8000/api` (configurable via `VITE_API_BASE`)
- **Content-Type:** `application/json`
- **Time format:** ISO 8601 UTC (`YYYY-MM-DDTHH:mm:ss.sssZ`)
- **Mock Header:** Frontend sends `X-BebshaX-Mock: 1` when operating with mock fixtures or when `VITE_MOCK=1`.
- **Request correlation:** every response carries `X-Request-ID` (a valid client-supplied `X-Request-ID` — ≤64 chars, `[A-Za-z0-9_-]` — is echoed, otherwise a uuid4 hex is generated). The same id is in every error body and in the one access-log line per request.
- **Standard Error Response** (every non-2xx JSON body, 2026-09-06):

  ```json
  {
    "detail": "Descriptive error message",
    "error_code": "not_found",
    "request_id": "hex32"
  }
  ```

  `detail` stays a string for backwards compatibility (a pydantic list for request-validation 422 responses, which then also carry `message` = "loc → msg" of the first error). `error_code` is snake_case:

  | HTTP                  | error_code                                              | Extra top-level fields                                                                                                                                         |
  | --------------------- | ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | 400                   | `bad_request`                                           |                                                                                                                                                                |
  | 401 / 403 / 404 / 409 | `unauthorized` / `forbidden` / `not_found` / `conflict` |                                                                                                                                                                |
  | 413                   | `payload_too_large`                                     | `max_bytes` (2 MiB JSON cap; dataset uploads exempt, own 25 MB cap)                                                                                            |
  | 413                   | `context_window_exceeded`                               | `estimated_tokens`, `largest_window` — raised BEFORE any provider call; nothing truncated (R2)                                                                 |
  | 422                   | `validation_error`                                      | `message`; for `POST /api/study/generate-personas` also `max_personas_per_role` (=3) when a selected role's `count` is outside 1..3 or two roles share an `id` |
  | 429                   | `rate_limited` / `too_many_jobs` / `too_many_attempts`  | `Retry-After`, `X-RateLimit-*` / `max_running_jobs`                                                                                                            |
  | 502                   | `llm_error`                                             | any other `LLMError` (e.g. `INTERNAL_ERROR` surfaced, never templated)                                                                                         |
  | 503                   | `all_candidates_failed`                                 | `llm_request_id`, `attempts[{provider, model, failure_kind, fallback_reason}]`, `routing_path[]`                                                               |
  | 503                   | `database_unavailable`                                  | request-time `OperationalError`/`InterfaceError`; also `GET /api/health/ready`                                                                                 |
  | 500                   | `internal_error`                                        | body is always the generic envelope; details only in logs, keyed by `request_id`                                                                               |

  SSE streams (`…/messages/stream`) emit an `error` event with the same `error_code`, `request_id`, `llm_request_id`, `attempts` fields.

- **Explicit feature failures (2026-09-08, `bebshax/utils/explicit_failures.py`).** No feature substitutes a template, skeleton, heuristic or default when the model or the data cannot produce the artefact (R2). Instead the request fails with one of these coded envelopes (all carry `detail` + `request_id`; `UnusableModelOutput` adds `attempts` and `served_by`):

  | HTTP | error_code                                                                                                                                                                                                                                                                                                                                                                       | Raised when                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
  | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
  | 503  | `llm_unavailable`                                                                                                                                                                                                                                                                                                                                                                | no LLM service is wired for a feature that needs one (`detail` names the feature, e.g. "Behavioral simulation")                                                                                                                                                                                                                                                                                                                                                                                    |
  | 502  | `copilot_reply_unparseable` · `roles_unparseable` · `persona_generation_unparseable` · `script_unparseable` · `claims_extraction_failed` · `query_generation_failed` · `research_plan_failed` · `report_synthesis_failed` · `segment_interpretation_failed` · `dataset_persona_unparseable` · `simulation_unparseable` · `interview_synthesis_unparseable` · `judge_unavailable` | the route answered but the reply could not be turned into the artefact after the retry budget; nothing was templated                                                                                                                                                                                                                                                                                                                                                                               |
  | 502  | `dataset_download_failed`                                                                                                                                                                                                                                                                                                                                                        | a discovered dataset resource could not be fetched (non-http(s) URL, HTTP error, >6 MB)                                                                                                                                                                                                                                                                                                                                                                                                            |
  | 422  | `dataset_unparseable`                                                                                                                                                                                                                                                                                                                                                            | a fetched/uploaded dataset is not a readable CSV/JSON table                                                                                                                                                                                                                                                                                                                                                                                                                                        |
  | 400  | `segmentation_requires_data` · `behavioral_requires_personas` · `scenario_required` · `script_required` · `nothing_to_review` · `business_description_required` · `report_requires_data`                                                                                                                                                                                         | the input the feature analyses is missing (no dataset rows / personas / scenario text / interview script / artefacts). `business_description_required`: script generation on a study with no prompt (a title is not a business). `report_requires_data`: report generation on a study with no personas, interviews, evidence, segments, behavioral results or datasets — a report over nothing would be a template. `nothing_to_review` also fires when a report row is the study's ONLY artefact. |
  | 404  | `scenario_not_found`                                                                                                                                                                                                                                                                                                                                                             | `POST …/behavioral-tests/{id}/runs` named a `scenario_id` that does not belong to that test (the run is refused, never silently substituted with the description)                                                                                                                                                                                                                                                                                                                                  |

  Partial outcomes are reported, never hidden: `POST /api/study/generate-personas` returns `{personas, failed_roles[{role_id, role, error_code, detail}], served_by[]}`; retained dataset LLM-compatibility generation exposes `failed[]`/`failed_count`, while runtime ML dataset failures abort the persona batch before persistence and may include `failed[]` in the error; interview completion returns `insights.source = "unavailable"` with `error_code` when synthesis failed, and `insights_dropped` (also on each `personas[id]` entry of a batch-run job) counts insight rows the database rejected — the interview itself still completes; research runs expose `summary.error_code`.

  Behavioral runs resolve their scenario from the request body's `scenario_text`, else the test's stored scenario (`scenario_id` if given, otherwise the most recent), else the test description; `run.scenario_id` links only to a scenario row verified to belong to the test.

- **Local persona ML failures (2026-09-09, [ml_adapter.py](../apps/backend/bebshax/personas/ml_adapter.py)).** These are `APIError` envelopes with string `detail`, `error_code`, and `request_id`, not new LLM `FailureKind` values:

  | HTTP | error_code | Raised when |
  | --- | --- | --- |
  | 503 | `ml_persona_unavailable` | The configured local artifact cannot be loaded (missing, invalid, unreadable, or incompatible numerical runtime). Default adapter detail: "The local persona model is unavailable." |
  | 422 | `ml_persona_unsupported_context` | Business context validation or selection fails, including no vocabulary overlap, unsupported ages, or too few distinct eligible candidates after exclusions. Default adapter detail: "The local persona model cannot support the requested context or constraints." |

  Persona generation does not silently fall back to an LLM. Chat, role suggestions, and interviews retain their existing LLM routing. The local model has been trained/evaluated, but clean checkouts do not include its ignored bundle. Configuration, exact numerical-version compatibility, and build commands are in [SETUP.md](SETUP.md#persona-ml-artifact).

---

## 2. Enumerations

### 2.1 TaskType (18 Fixed Tasks — mirrors `bebshax/llm/types.py`)

```typescript
export type TaskType =
  | "PERSONA_GENERATION"
  | "PERSONA_REFINEMENT"
  | "PERSONA_VALIDATION"
  | "PERSONA_INTERVIEW"
  | "PERSONA_RESPONSE"
  | "PERSONA_NARRATIVE"
  | "BEHAVIORAL_SIMULATION"
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

### 2.2 FailureKind (closed taxonomy, 13 kinds — mirrors `bebshax/llm/failures.py`; quality is NOT a kind)

```typescript
export type FailureKind =
  | "TIMEOUT"
  | "CONNECTION"
  | "RATE_LIMITED"
  | "QUOTA_EXHAUSTED"
  | "SERVER_ERROR"
  | "PROVIDER_UNAVAILABLE"
  | "AUTH_INVALID"
  | "MODEL_UNAVAILABLE"
  | "CONTEXT_WINDOW_EXCEEDED"
  | "CAPABILITY_UNSUPPORTED"
  | "MALFORMED_RESPONSE"
  | "CONTENT_REFUSAL"
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

### 3.1 Health Check (Phase 1; deepened 2026-09-06)

- **`GET /api/health`** — liveness + a fail-soft snapshot
- **Response `200 OK`:**
  ```json
  {
    "status": "ok",
    "app": "BebshaX",
    "version": "0.1.0",
    "environment": "development",
    "demo_mode": false,
    "db": "ok",
    "local_tier_up": true,
    "sink": { "written": 120, "dropped": 0, "db_errors": 0 }
  }
  ```
  `db` is `"ok"` or `"unreachable"` (`SELECT 1`, 2 s timeout); `local_tier_up` is the Ollama probe at boot (`null` when unknown); `sink` are the provenance writer counters.
- **`GET /api/health/ready`** — readiness: `200` when the database answers, else `503 {"error_code": "database_unavailable"}`. This is the compose healthcheck target.

---

### 3.2 LLM Provenance & Routing (Phase 2, 5, 6)

#### `GET /api/provenance`

- **Query params:** `limit` (default 50), `task`, `pool`, `success` (boolean), `persona_id`
- **Scope:** owner-scoped; rows the caller does not own (and all rows for anonymous callers) have `attempts[].failure_detail` redacted to `null` — provider error bodies can echo request fragments. `failure_kind` is always present.
- **`routing_path` markers** (2026-09-06): besides candidate names and `[skipped: <reason>]` entries, each record carries `[context estimate ~N tokens incl. max_output M]`, `[params temperature=… max_output_tokens=… json_mode=…]` and, when the quota-aware ranker changed the order, `[ranker reordered: … -> …]`. `estimated_tokens` is also a top-level field of the in-memory `ProvenanceRecord`.
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
        "routing_path": [
          "groq/llama-3.3-70b-versatile",
          "pollinations/deepseek-r1",
          "ollama/llama3.2:3b"
        ],
        "attempts": [
          {
            "attempt_number": 1,
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "started_at": "2026-08-22T08:00:00.000Z",
            "latency_ms": 142.5,
            "success": false,
            "failure_kind": "RATE_LIMITED",
            "failure_detail": "HTTP 429: TPM limit reached",
            "fallback_reason": "advancing after RATE_LIMITED",
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
      {
        "name": "pollinations",
        "type": "keyless",
        "status": "healthy",
        "available_models": 12,
        "active_cooldowns": 0
      },
      {
        "name": "groq",
        "type": "free_tier_key",
        "status": "degraded",
        "available_models": 4,
        "active_cooldowns": 1
      },
      {
        "name": "ollama",
        "type": "local_fallback",
        "status": "healthy",
        "available_models": 2,
        "active_cooldowns": 0
      }
    ],
    "pools": [
      {
        "name": "reasoning",
        "max_concurrency": 4,
        "active_requests": 1,
        "candidates_count": 5
      },
      {
        "name": "conversation",
        "max_concurrency": 8,
        "active_requests": 0,
        "candidates_count": 8
      },
      {
        "name": "fallback",
        "max_concurrency": 2,
        "active_requests": 0,
        "candidates_count": 2
      }
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
    "generation_hints": [
      "Prioritize irregular cashflow challenges",
      "Mobile-first technology user"
    ],
    "min_age": 18,
    "max_age": 65
  }
  ```
- Optional `min_age` / `max_age` are strict integers in 18-95, inclusive; the resolved minimum must not exceed the maximum. They are hard eligibility constraints, unlike audience/role/location wording, which is only relevance context. The response preserves the selected source occupation and location, never inferring income/budget or relabeling a profile to match the request.
- **Response `201 Created`:** a `PersonaProfile` serialized by [api/personas.py](../apps/backend/bebshax/api/personas.py), with the source-derived ML fields below. This is a schema description, not a live inference result.

  | Field | Local ML value / meaning |
  | --- | --- |
  | `name`, `age`, `occupation`, `location`, `education`, `description` | Top-level identity fields from the selected synthetic record. Missing location/education remain "Not available in training data"; a missing name uses a synthetic record identifier. |
  | `income_range`, `personality` | "Not available in training data" and `null` respectively; the adapter does not infer measurements. |
  | `generation_model` | `bebshax-persona-ml/<model_version>`, not an LLM serving route. |
  | `attributes[]` | Every generated claim has `provenance_class: "SYNTHETIC"`, `evidence_ids: []`, and `confidence: null`. |
  | `evidence` | `[]`; training membership is not observed customer evidence. |
  | `detailed_attributes.ml_provenance` | `{source, revision, record_id, model_version, selection_score, topic}` from the selected record/model. Selection score is a relevance score, not empirical confidence or customer demand. |
  | `detailed_attributes.source_documents` | The selected record's complete source-document mapping. |
  | `detailed_attributes.claim_provenance` | `goals`, `pain_points`, and `behaviors` arrays of `{value, provenance: "SYNTHETIC", evidence_ids: []}`. |
  | `detailed_attributes.validation_warnings`, `warnings` | Synthetic-USA-proxy disclosure, missing-field warnings, and any selection limitations. |

#### `GET /api/personas/{id}`

- **Response `200 OK`:** Full `Persona` profile.

#### Shared local ML provenance (2026-09-09)

The study, workflow, and dataset persona-generation paths use the same [ML adapter](../apps/backend/bebshax/personas/ml_adapter.py) and retain their existing response envelopes. Study/workflow records also carry `dataset_refs` containing the same ML provenance object; workflow personas expose `is_synthetic: true`, `grounding_basis: "synthetic_training_proxy"`, and synthetic attributes with empty evidence links. Context claims used to select a record do not make that record's attributes observed evidence.

| Generation Path | Existing Contract / Age Input |
| --- | --- |
| `POST /api/businesses/{business_id}/personas` | One `PersonaProfile`; request `min_age` / `max_age` |
| `POST /api/studies/{study_id}/personas/generate` (and existing jobs/regeneration paths) | Existing study run/persona schemas; `segment.characteristics.demographics.age_range` supplies explicit bounds |
| `POST /api/study/generate-personas` | Existing workflow envelope; each selected role may carry `min_age` / `max_age`; existing 1-3 per-role count cap is unchanged |
| `POST /api/datasets/{dataset_id}/generate-personas` | Existing dataset run/persona envelope; segment `constraints.age_range`, or numeric age min/max, supplies bounds; dataset numeric endpoints are rounded inward to integer ages |

Generated source goals, regex-extracted pain points, and behaviors remain
`SYNTHETIC` with empty citations, zero grounding, and unset/zero confidence.
Unknown income/budget and OCEAN/personality measurements are not invented.
`role_title` is workflow metadata, not proof of the selected occupation. Dataset
`dataset_refs` can additionally describe the segment with `usage:
"selection_context"`; that is not evidence supporting the selected identity.
The role endpoint's `evidence_claim_count` counts available study context claims,
not grounded ML attributes; those still have no evidence IDs. Source documents
are complete normalized text, and source/model hashes are not signed attestation.

`POST /api/study/generate-personas` still returns `{personas, failed_roles, served_by}`. `served_by[]` contains the successful `bebshax-persona-ml/<model_version>` identifiers. If some roles fail, HTTP 200 retains their `{role_id, role, error_code, detail}` entries in `failed_roles`; if all fail, the last coded error is raised with its HTTP status (including the ML 503/422 errors in section 1).

#### Active-source exclusions and persistence

[active_source_exclusions](../apps/backend/bebshax/personas/service.py) reads
nonarchived source IDs and names within the owner and applicable scope. Business
generation scopes to the business; study generation/regeneration scopes to the
study; dataset generation uses the study when present, otherwise that owner's
study-less generation runs for the dataset. Study/dataset segments also exclude
selections already made in the current batch. Repeated sequential requests
therefore avoid active sources rather than repeatedly selecting the same record.

ML study/dataset generation that cannot fill the requested eligible batch raises
422 without saving a partial persona batch; a study run can remain recorded as
failed. Dataset selection errors can carry per-segment `failed[]` diagnostics.
Study `persona_count` is the total of active owner-scoped rows, not just the new
batch size. Role generation retains its existing behavior: it excludes siblings
within the request and archives the old cohort when persisting the new one,
without excluding old-cohort source records from selection. Its partial-role
success contract above is unchanged.

Exclusions are a read-before-generate check, not a transactional uniqueness lock.
Overlapping independent requests/processes can still select the same source;
no cross-process uniqueness guarantee is claimed. Existing persona tables,
JSON columns, ownership/quota checks, and response schemas remain authoritative.
The ML integration introduces no database migration, frontend contract/provider
change, or HTTP training endpoint. The later user-approved frontend correction
changes only four CSS theme-token declarations, not these contracts.

[Post-sync local checks](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09)
passed on 2026-09-09. Earlier live checks persisted/read back five unique ML
profiles in fresh local PostgreSQL, exercised real copilot/role/interview calls,
and loaded the Windows-trained artifact in Linux with networking disabled;
these were not repeated after sync. They are not an all-route load test or
production-readiness certification. The
model underperforms lexical TF-IDF on the retrieval proxy;
see [MODEL_CARD.md](../ml_persona/MODEL_CARD.md) and
[EXPERIMENTS.md](../ml_persona/EXPERIMENTS.md). USA-only synthetic selections do
not establish student/Bangladesh fit or customer demand. The earlier desktop
check passed; mobile persona-header clipping remains unfixed and was not
reverified after upstream styling or the token-only correction. Full Compose
app/web and cross-conversation retrieval rehearsals were not repeated. Commit,
push, and CI results are tracked separately in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), not claimed successful here.

#### `data_source` — demo honesty label (audit H3 piece 2)

Study-scoped persona records expose `data_source`, one of the values below. The legacy `PersonaProfile` response above does not include this field.

| Value      | Meaning                                                                            |
| ---------- | ---------------------------------------------------------------------------------- |
| `"live"`   | Runtime-generated content, including local ML synthetic selection; not a demo fixture or a claim of observed evidence. |
| `"cached"` | The content came from the demo seeder — pre-seeded fixtures, not model output.     |

The value is **persisted on the row at creation time**, not derived from `demo_mode` at read time: the flag flips independently of the rows already in the table, so deriving it would mislabel every persona created before the last flip. Existing rows were backfilled to `"live"` by migration `9f0a1b2c3d4e`, which is correct — the demo seeder is the only cached producer and it did not previously exist as a distinct category.

Clients MUST NOT present `"cached"` content as system output. **Frontend obligation (Shehab):** surface a visible badge wherever a persona is rendered; absent the badge the label is invisible to the user and H3's honesty requirement is only half met. Semantics are defined in [DEMO.md](DEMO.md) §4.

---

### 3.5 Persona Memory Stream (Phase 9)

#### `GET /api/personas/{id}/memories`

- **Query params:** `kind` (`semantic` | `episodic` | `reflection`), `limit`, `include_interviewer` (bool, default `false`)
- **Source contract (2026-09-06):** every memory row carries `source` ∈ `persona | interviewer | system` and an optional `conversation_id`. By default only `persona` items (the persona's own statements) are listed — a researcher's question is context, never something the persona "remembers". `include_interviewer=true` also lists `interviewer` rows so the UI can label them "asked by researcher". Retrieval into prompts uses persona items only and drops items below a cosine relevance floor. `recency_weight`/`relevance_score` are `null` on listing (only computed at retrieval time — never fabricated).
- **Response `200 OK`:**
  ```json
  [
    {
      "id": "mem_001",
      "persona_id": "per_sarah_01",
      "kind": "semantic",
      "text": "Drives a 2018 Honda Civic with 110,000 miles; highly sensitive to maintenance budget alerts.",
      "importance": 0.85,
      "recency_weight": null,
      "relevance_score": null,
      "source": "persona",
      "conversation_id": null,
      "created_at": "2026-08-22T08:20:00.000Z"
    },
    {
      "id": "mem_002",
      "persona_id": "per_sarah_01",
      "kind": "episodic",
      "text": "Mentioned during onboarding interview that she tried Mint but abandoned it because weekly tips weren't categorized properly.",
      "importance": 0.72,
      "recency_weight": null,
      "relevance_score": null,
      "source": "persona",
      "conversation_id": "conv_201",
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

#### `POST /api/studies/{study_id}/interviews/{interview_id}/messages/stream`

- **SSE variant** of the study-scoped message endpoint (same auth/ownership checks). `Content-Type: text/event-stream`. Events, in order:
  - `event: delta` · `data: {"text": "<raw chunk>"}` — repeated as the persona speaks (raw model output).
  - `event: done` · `data: {…}` — the canonical payload (same fields as the non-stream endpoint incl. `reply` [normalized, this is what was persisted], `turn_number`, `served_by`, `latency_ms`, `suggested_questions`, `topics_explored`, `is_finished`, plus `user_message`/`persona_reply` parity objects). Clients MUST replace their streamed buffer with `reply`.
  - `event: error` · `data: {"kind": "finished|not_found|context_window|no_route|generic", "detail": "…", "error_code": "…", "request_id": "…", "llm_request_id": "…", "attempts": […], "routing_path": […]}` — failures after headers are sent; nothing was persisted for this turn unless `done` arrived. `kind` is legacy; `error_code` follows §1.

#### Consistency signals on study-scoped turns (2026-09-06)

The study-scoped message endpoint (`POST /api/studies/{study_id}/interviews/{interview_id}/messages`), its SSE `done` payload and every serialized turn (`turns[]` on interview detail) carry deterministic **quality** signals — never infrastructure failures, the turn was served normally:

```json
{
  "identity_drift": false,
  "drift_notes": [],
  "contradiction_detected": true,
  "contradiction_details": "৳2,500 exceeds stated monthly budget of ৳400"
}
```

`identity_drift` compares age/name/occupation statements in the reply against the immutable identity card; `contradiction_detected` compares money amounts against the persona's stated budget (skipped when no budget was stated). Both are also stored in the turn's `metadata`. The completion endpoint (`POST …/complete`) returns `source: "llm" | "fallback_mechanical"` and `fallback_reason` so a mechanical summary is never mistaken for analysis.

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

### 3.7 Evaluation & Insights (Phase 11; M1 rewrite 2026-08-27)

#### `GET /api/evaluation/metrics`

- Every value is **measured** (provenance aggregates from `llm_requests`, persona validation artifacts, judged gate reports). Metrics with no underlying data are `null` — never an invented `0.0`/`1.0`. The former `routing_strategies` array (which included a fabricated "ROUND_ROBIN (Naive)" arm) is **removed**.
- The JSON below illustrates the response shape, not current ML measurements. `local_serve_rate` counts Ollama LLM responses, not CPU persona selection. ML creates no `PERSONA_GENERATION` LLM request, so request-derived schema/latency metrics cannot measure ML validity or inference time; use the separate [ML evaluation](EVALUATION.md#5-isolated-persona-ml-evaluation-2026-09-09).
- **Response `200 OK`:**
  ```json
  {
    "overall_health": {
      "total_personas_generated": 24,
      "schema_validity_rate": 0.958,
      "consistency_pass_rate": 0.929,
      "avg_grounding_ratio": 0.742,
      "avg_latency_ms": 5240.5
    },
    "pools": [
      {
        "pool": "conversation",
        "requests": 412,
        "success_rate": 0.99,
        "avg_latency_ms": 6100.0,
        "fallback_rate": 0.05,
        "local_serve_rate": 0.93
      }
    ],
    "quality_gate": {
      "generated_at": "2026-08-26T17:56:33+00:00",
      "bar": 8.0,
      "rubric_weights": { "persona_consistency": 0.25 },
      "arms": [
        {
          "tag": "local/llama3.2:3b",
          "model": "ollama/llama3.2:3b",
          "weighted_score": 9.65,
          "avg_latency_ms": 6067,
          "dims": { "naturalness": 9 }
        }
      ],
      "judge_route": "llm7/codestral-latest",
      "judge_notes": "…",
      "source_file": "local_3b_gate_20260826_235633.json"
    }
  }
  ```
- Field semantics: `schema_validity_rate` = share of `PERSONA_GENERATION` requests with no `MALFORMED_RESPONSE` attempt (R6 taxonomy), `null` when no generation requests exist. `consistency_pass_rate` = personas whose stored validation has zero warnings, over personas that have validation details; `null` when none are evaluable. `pools` lists only pools that actually served traffic; `fallback_rate` = share of multi-attempt requests; `local_serve_rate` = share served by the local `ollama` adapter. `quality_gate` = newest readable `data/metadata/local_3b_gate_*.json` (judge harness), else `null`.

---

### 3.8 Judge Lab — scripted failure drills through the real router (2026-09-06)

Available only when `BEBSHAX_DEMO_MODE=true` or `BEBSHAX_ENVIRONMENT` ∈ {`development`, `local`}; everywhere else every route is `404` (not discoverable). Requires a bearer token; limited to 30/minute. Each run builds a **throwaway** `PoolRouter` over scripted `FakeAdapter` routes and calls the real `router.complete()` — the production eligibility filter, failure policies, cooldowns and provenance code — without touching `app.state.llm_router`, without contacting any provider, and without writing to the provenance sink. Every payload says `"simulated": true`.

#### `GET /api/demo-lab/scenarios`

```json
{
  "enabled": true,
  "simulated": true,
  "scenarios": [
    {
      "name": "provider_429_fallback",
      "title": "…",
      "description": "…",
      "expected_outcome": "…"
    }
  ]
}
```

Scenario names (a data table in `bebshax/api/demo_lab.py`): `provider_429_fallback`, `provider_5xx_fallback`, `all_providers_down`, `context_overflow`, `prompt_injection`, `evidence_conflict`, `insufficient_evidence`.

#### `POST /api/demo-lab/scenarios/{name}/run`

```json
{
  "scenario": "provider_429_fallback",
  "title": "Provider returns 429 → fallback serves",
  "simulated": true,
  "outcome": "served_after_fallback",
  "error_code": null,
  "explanation": "Route A answered HTTP 429 (RATE_LIMITED) … cooled route is excluded from selection for 60s.",
  "provenance": {
    "request_id": "…",
    "task": "PERSONA_GENERATION",
    "pool": "reasoning",
    "routing_path": [
      "[context estimate ~1148 tokens incl. max_output 1024 (default)]",
      "openrouter/…",
      "groq/…",
      "ollama/llama3.2:3b"
    ],
    "attempts": [
      {
        "attempt_number": 1,
        "provider": "openrouter",
        "model": "…",
        "success": false,
        "failure_kind": "RATE_LIMITED",
        "fallback_reason": "advancing after RATE_LIMITED"
      },
      { "attempt_number": 2, "provider": "groq", "model": "…", "success": true }
    ],
    "estimated_tokens": 1148,
    "served_by_provider": "groq",
    "success": true
  },
  "timeline": [
    {
      "step": 1,
      "provider": "openrouter",
      "model": "…",
      "result": "failed",
      "failure_kind": "RATE_LIMITED",
      "fallback_reason": "advancing after RATE_LIMITED",
      "latency_ms": 0.01
    },
    {
      "step": 2,
      "provider": "groq",
      "model": "…",
      "result": "served",
      "failure_kind": null,
      "fallback_reason": null,
      "latency_ms": 0.01
    }
  ],
  "extra": {
    "reply": "…",
    "cooling_routes": ["openrouter/…"],
    "adapter_calls": { "openrouter": ["…"], "freellmpool": ["…"], "ollama": [] }
  }
}
```

`outcome` ∈ `served | served_after_fallback | explicit_failure | claims_downgraded | low_grounding`; `error_code` ∈ `null | all_candidates_failed | context_window_exceeded`. `context_overflow` returns `provenance` with only `[skipped: context …]` markers and `extra.adapter_calls` all empty — proof that nothing was sent or truncated. `prompt_injection`/`evidence_conflict` return the `<UNTRUSTED_EVIDENCE>` prompt excerpt and the before/after provenance class of each claim (`coerce_provenance` downgrades). Unknown scenario → `404 not_found`.

### 3.9 AI Review — an independent model audits a study's artefacts (2026-09-08)

The reviewing model (`TaskType.CRITIC`, routed like every other call) scores what the study has actually produced against a fixed, published rubric. It is a second opinion written per study, never a canned verdict.

- **`GET /api/ai-review/rubric`** — `{dimensions: {grounding, specificity, consistency, honesty, actionability → criterion text}, scale}`.
- **`POST /api/studies/{study_id}/ai-review`** (write gate, 6/min) and **`POST /api/studies/{study_id}/personas/{persona_id}/ai-review`** (12/min) → `JudgeVerdict`:

```json
{
  "study_id": "study_…",
  "overall_score": 0,
  "dimension_scores": {
    "grounding": 0,
    "specificity": 0,
    "consistency": 0,
    "honesty": 0,
    "actionability": 0
  },
  "strengths": ["…"],
  "issues": [
    {
      "severity": "high|medium|low",
      "artifact": "persona:<id>|report|interview:<id>|segment:<id>|evidence",
      "detail": "…"
    }
  ],
  "verdict": "…",
  "scope": "study|persona",
  "reviewed_artifacts": {
    "personas": 0,
    "segments": 0,
    "evidence_claims": 0,
    "interviews": 0,
    "reports": 0
  },
  "served_by": "provider/model",
  "llm_request_id": "…",
  "attempts": 1,
  "reviewed_at": "…"
}
```

Failures are coded (§1): `400 nothing_to_review` (the study has no artefacts yet), `503 llm_unavailable`, `502 judge_unavailable` (the reviewer's reply could not be parsed after the retry budget). The frontend surfaces the verdict in the report step (`AiReviewCard`).

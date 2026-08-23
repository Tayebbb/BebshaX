# BebshaX — Persona Engine (Phase 8)

How a persona goes from a business description to a stored, evidence-grounded, consistency-checked profile.

## Pipeline

```
business (name + description)
  → EvidenceStore.retrieve()          deterministic idf-weighted lexical retrieval over the
                                      Phase-7 processed datasets (k=6, per-source cap, capped
                                      memory; missing datasets degrade to zero evidence)
  → diversity seed                    one PersonaHub sketch chosen deterministically per attempt —
                                      used ONLY to diversify perspective (persona-driven synthesis,
                                      arXiv:2406.20094), never copied into the identity
  → PERSONA_GENERATION                json_mode, temp 0.8, via PoolRouter → reasoning pool
  → parse + pydantic validation       (GeneratedPersona schema)
  → coerce_provenance()               machine-enforced honesty (see below)
  → check_consistency()               deterministic table-driven rules
  → [one PERSONA_REFINEMENT round]    only for schema-invalid output OR consistency errors
  → optional CRITIC pass              issues become warnings, never failures
  → save_persona()                    personas + persona_details + persona_attributes +
                                      persona_evidence (Postgres, alembic a8f3c2d91e04)
```

## Provenance is enforced in code, not trusted from the LLM

Every attribute carries `OBSERVED | INFERRED | SYNTHETIC` (`bebshax/persona/schema.py::coerce_provenance`):

| Model claims                                                    | We store                        |
| --------------------------------------------------------------- | ------------------------------- |
| OBSERVED + valid evidence id (one actually shown in the prompt) | OBSERVED with the citation      |
| OBSERVED + fabricated/unknown id                                | **INFERRED, citation stripped** |
| INFERRED                                                        | INFERRED                        |
| anything else / garbage label                                   | SYNTHETIC                       |

Downgrades only — a claim can never be upgraded past what its citations prove. With zero evidence available, the prompt explicitly forbids OBSERVED. Live verification (2026-08-23): real generation produced 3 OBSERVED (verified citations) + 13 INFERRED.

## Failure discipline (R2)

- Transport/429/timeout/malformed-JSON are **infrastructure** — handled inside `LLMService`/`PoolRouter`, invisible here.
- Schema-invalid or contradiction-carrying output is a **content** problem: exactly ONE `PERSONA_REFINEMENT` round, then explicit `PersonaGenerationFailed` (HTTP 422 with violations). Never silently degraded, never truncated.
- Low answer quality is neither: it belongs to the Phase-11 evaluator, which consumes `PersonaProfile.to_eval_dict()` (contract-tested).

## Consistency rules (table-driven, `bebshax/persona/consistency.py`)

- `age_occupation` (error): occupation markers imply minimum ages (retired ≥50, CEO ≥25, ...).
- `income_luxury` (error): low-income markers + habitual-luxury phrasing in any attribute.
- `location_timezone` (warning): location vs contradicting timezone mentions.
- `age_student` (warning): student aged >60 — verify intent.

Extend by adding table entries + a test, not code branches.

## Dataset usage (optimized, not heavy)

- Lazy one-time load, ≤30k records/dataset, texts truncated to 500 chars, tiny df-index → milliseconds per retrieval, a few MB of RAM, zero new dependencies.
- Evidence blocks in prompts are id-tagged and truncated — whole prompt stays ~2–3k tokens, fitting every pool member including the 16k local models.
- Semantic (pgvector) retrieval replaces the lexical scorer in Phase 9 without changing the engine (EvidenceStore is the seam).

## Memory (Phase 9)

Persistent persona memory: a pgvector stream implementing the generative-agents retrieval concept on our stack.

- **Kinds:** `episodic` (raw observations, written per interview turn from Phase 10), `semantic`, `reflection` (distilled insights).
- **Retrieval score:** `0.60·cosine + 0.25·recency + 0.15·importance`, recency = exponential decay with a 48 h half-life (weights injectable on `MemoryService`). Retrieval touches `last_accessed`; scoring runs in Python (identical on sqlite unit paths and Postgres), with an HNSW cosine index on the pg side for future SQL-side pre-filtering.
- **Embeddings & the space-consistency rule** (documented deviation from the spec): cosine is only meaningful within ONE embedding space, but freellmpool's embed failover can serve different models per call. Therefore: the **default backend is a deterministic local hash embedding** (`local-hash-384` — offline, free, stable forever; lexical-strength semantics), and the **freellmpool backend requires a pinned model** (`BEBSHAX_EMBEDDING_BACKEND=freellmpool` + `BEBSHAX_EMBEDDING_MODEL=…`). Every row stores its `embedding_space` tag and retrieval filters to the query's space — vectors from different spaces are never compared.
- **Reflection:** ≥8 episodic memories → latest batch summarized via `MEMORY_SUMMARIZATION` (fast pool) into ≤3 first-person `reflection` items at importance 0.8. Best-effort: unparseable output logs and skips — reflection can never break a conversation.
- Verified live on pgvector: 20 memories → expected top-k ordering; reflection stored and retrievable (`pytest -m integration apps/backend/tests/memory/test_pg_integration.py`).

## Interviews (Phase 10)

Multi-turn interviews with a **stable identity** — the persona is composed per turn, never regenerated.

- **Per-turn composition** (`bebshax/interview/engine.py`): system = immutable identity card (`build_identity_card`, byte-identical every turn) + in-character constraints + business context + objective + top-k retrieved memories (Phase 9) + evidence themes; history = ALL prior turns; then the new interviewer message. If nothing fits, the router raises `ContextWindowExceeded` — identity/evidence are never truncated (R2). Memories legitimately evolve between turns; the identity never does.
- **Routing:** `PERSONA_INTERVIEW` → conversation pool. Each exchange is written back as an episodic observation memory (importance 0.4); `MemoryService.reflect()` distills them after conversations.
- **REST:** `POST /api/personas/{id}/conversations` · `POST /api/conversations/{id}/messages` → `{reply, turn_number, served_by}` · `GET /api/conversations/{id}` (transcript). 404/413/503 mappings as elsewhere.
- **Live verification (2026-08-23):** 5-turn interview of a freshly generated persona served by FOUR different providers mid-conversation (kilo/llm7/ovh) — name, age, and occupation stayed consistent (`scripts/smoke_interview.py`). Observed free-tier quality artifact (a reasoning model leaking its thinking) is a Phase-11 evaluation concern, not an infrastructure failure — by design.

## REST API (`bebshax/api/personas.py`)

| Endpoint                             | Purpose                                           | Errors                                                                                        |
| ------------------------------------ | ------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `POST /api/businesses`               | create business                                   | —                                                                                             |
| `GET /api/businesses`                | list                                              | —                                                                                             |
| `POST /api/businesses/{id}/personas` | generate + store one persona                      | 404 unknown business · 422 generation failed (violations listed) · 413 context · 503 no route |
| `GET /api/personas/{id}`             | full profile incl. attributes, evidence, warnings | 404                                                                                           |

App wiring (`main.py` lifespan) now also connects **Sazid's `ProvenanceSink` to the PoolRouter** — every LLM request lands in `llm_requests` (fail-soft; DB issues never fail a request).

## Verification

- Unit: `apps/backend/tests/persona/` — 26 tests (coercion, retrieval, rules, refinement budget, explicit failure, critic, round-trip persistence, HTTP flow).
- Live: `python scripts/smoke_persona.py` (needs `docker compose up -d db`, `alembic upgrade head`, optionally `setup_datasets.py --profile minimal`).

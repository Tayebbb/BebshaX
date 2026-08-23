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

| Model claims | We store |
|---|---|
| OBSERVED + valid evidence id (one actually shown in the prompt) | OBSERVED with the citation |
| OBSERVED + fabricated/unknown id | **INFERRED, citation stripped** |
| INFERRED | INFERRED |
| anything else / garbage label | SYNTHETIC |

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

## REST API (`bebshax/api/personas.py`)

| Endpoint | Purpose | Errors |
|---|---|---|
| `POST /api/businesses` | create business | — |
| `GET /api/businesses` | list | — |
| `POST /api/businesses/{id}/personas` | generate + store one persona | 404 unknown business · 422 generation failed (violations listed) · 413 context · 503 no route |
| `GET /api/personas/{id}` | full profile incl. attributes, evidence, warnings | 404 |

App wiring (`main.py` lifespan) now also connects **Sazid's `ProvenanceSink` to the PoolRouter** — every LLM request lands in `llm_requests` (fail-soft; DB issues never fail a request).

## Verification

- Unit: `apps/backend/tests/persona/` — 26 tests (coercion, retrieval, rules, refinement budget, explicit failure, critic, round-trip persistence, HTTP flow).
- Live: `python scripts/smoke_persona.py` (needs `docker compose up -d db`, `alembic upgrade head`, optionally `setup_datasets.py --profile minimal`).

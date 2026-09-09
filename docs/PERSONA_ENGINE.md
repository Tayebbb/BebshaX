# BebshaX — Persona Engine (Phase 8)

How a persona goes from business context to a stored profile. As of 2026-09-09,
runtime generation uses the isolated local non-LLM selector. The original
Phase-8 LLM path remains for explicit compatibility callers; it is not fallback
behavior for an unavailable model.

## Pipeline

```text
business / study segment / selected role / dataset context
  -> strict BusinessContext + explicit age bounds + source exclusions
  -> shared MLPersonaAdapter (lazy local load, bounded off-event-loop inference)
  -> training-fitted TF-IDF + NMF similarity and diversity-aware selection
  -> complete normalized synthetic source bundles, without replacement
  -> existing GeneratedPersona / PersonaProfile / GeneratedPersonaDraft mappings
  -> existing persona tables and JSON fields; SYNTHETIC claims, empty citations
```

The four paths, mappings, and ownership are detailed in
[ml_persona/ARCHITECTURE.md](../ml_persona/ARCHITECTURE.md). Selection makes no
LLM calls and performs no training or download in a request. It preserves source
names, ages, occupation, geography, goals, pain points, behaviors, and documents.
Income/budget and OCEAN/personality measurements remain unavailable, never
invented. Role and location are soft hints, with mismatch warnings; explicit
`min_age`/`max_age` are hard inclusive integer constraints in 18–95. A student-oriented request
does not relabel a selected adult as a student or establish real customer fit.

### Retained LLM Compatibility Path

The following branch runs only when `PersonaEngine` is constructed without an
ML adapter. Normal API wiring supplies the adapter. It remains relevant to the
historical Phase-8 checks, not the current model's training or generation metrics.

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

## Provenance is enforced in code

For ML selections, [ml_adapter.py](../apps/backend/bebshax/personas/ml_adapter.py)
marks every generated claim `SYNTHETIC` with empty evidence IDs/citations.
`detailed_attributes.ml_provenance` carries source, revision, record ID, model
version, selection score, and topic; `source_documents` preserves full normalized
narratives. Draft/workflow `dataset_refs` are source metadata, not evidence.
Grounding and confidence remain zero/unset. Source-derived goals and regex-selected
pain points are hypotheses; training membership never proves an `OBSERVED` claim.

The shared coercion rules also remain available to the LLM compatibility path.
Every attribute carries `OBSERVED | INFERRED | SYNTHETIC` (`bebshax/persona/schema.py::coerce_provenance`):

| Model claims                                                    | We store                        |
| --------------------------------------------------------------- | ------------------------------- |
| OBSERVED + valid evidence id (one actually shown in the prompt) | OBSERVED with the citation      |
| OBSERVED + fabricated/unknown id                                | **INFERRED, citation stripped** |
| INFERRED                                                        | INFERRED                        |
| anything else / garbage label                                   | SYNTHETIC                       |

Downgrades only — a claim can never be upgraded past what its citations prove. With zero evidence available, the compatibility prompt explicitly forbids OBSERVED. Historical LLM verification (2026-08-23) produced 3 OBSERVED (verified citations) + 13 INFERRED; this is not the current ML output contract.

## Failure discipline (R2)

ML loading failures produce 503 `ml_persona_unavailable`; invalid context, no
vocabulary overlap, unsupported ages, or insufficient unique eligible candidates
produce 422 `ml_persona_unsupported_context`. No LLM, fabricated identity, or
smaller selection batch is substituted. The model lives at the default
`data/processed/ml_persona/model` or `BEBSHAX_ML_PERSONA_ARTIFACT_DIR`; see
[SETUP.md](SETUP.md#persona-ml-artifact) for reproduction and compatibility.
Fresh installs contain the package but not the ignored bundle. Exact numerical
versions are pinned in [constraints.txt](../ml_persona/constraints.txt), used
by local and Docker installs. Loading is cached; restart after replacing a
trusted validated artifact. A live chat route does not repair a missing model.

For the retained LLM compatibility path:

- Transport/429/timeout/malformed-JSON are **infrastructure** — handled inside `LLMService`/`PoolRouter`, invisible here.
- Schema-invalid or contradiction-carrying output is a **content** problem: exactly ONE `PERSONA_REFINEMENT` round, then explicit `PersonaGenerationFailed` (HTTP 422 with violations). Never silently degraded, never truncated.
- Low answer quality is neither: it belongs to the Phase-11 evaluator, which consumes `PersonaProfile.to_eval_dict()` (contract-tested).

## Consistency rules (table-driven, `bebshax/persona/consistency.py`)

- `age_occupation` (error): occupation markers imply minimum ages (retired ≥50, CEO ≥25, ...).
- `income_luxury` (error): low-income markers + habitual-luxury phrasing in any attribute.
- `location_timezone` (warning): location vs contradicting timezone mentions.
- `age_student` (warning): student aged >60 — verify intent.

Extend by adding table entries + a test, not code branches.

The default `PersonaEngine` ML branch returns its source-preserving mapped
profile before this LLM refinement/critic pipeline. Bundle preservation and age
eligibility are not claims of universally correct semantic consistency.

## Dataset usage

Only the reviewed synthetic NVIDIA source in the independent `ml_persona`
profile trains the model. Legacy grounding/evaluation datasets, user uploads,
private studies, and conversations do not become training data. Study/dataset
context can inform selection without grounding the selected identity or claims.
Normalization preserves narrative content rather than truncating it to fit a
model. The original `EvidenceStore` and diversity seeds belong to the retained
LLM path, not default ML generation. See [training data](../ml_persona/DATASETS.md).

## Persistence And Repeated Generation

Existing tables and `GeneratedPersona`, `PersonaProfile`, and
`GeneratedPersonaDraft` contracts remain authoritative. Legacy business, study
(including regeneration), and dataset generation load nonarchived source IDs
and names through owner-scoped `active_source_exclusions`. New study/dataset
segments also exclude earlier selections in the same batch; exhaustion fails
with 422 before saving a partial persona batch. Study `persona_count` counts all
active owner-scoped rows, not just the latest run.

Role-based generation still archives the old cohort on persistence and prevents
sibling reuse within the request; it retains `failed_roles` when other roles
succeed. Independent overlapping requests have no transactional uniqueness lock,
so sequential exclusion is not a guarantee of cross-process uniqueness. There
is no new DB migration, frontend, provider, or competing storage schema.

## Memory (Phase 9)

Persistent persona memory: a pgvector stream implementing the generative-agents retrieval concept on our stack.

- **Kinds:** `episodic` (raw observations, written per interview turn from Phase 10), `semantic`, `reflection` (distilled insights).
- **Retrieval score:** `0.60·cosine + 0.25·recency + 0.15·importance`, recency = exponential decay with a 48 h half-life (weights injectable on `MemoryService`). Retrieval touches `last_accessed`; scoring runs in Python (identical on sqlite unit paths and Postgres), with an HNSW cosine index on the pg side for future SQL-side pre-filtering.
- **Embeddings & the space-consistency rule** (documented deviation from the spec): cosine is only meaningful within ONE embedding space, but freellmpool's embed failover can serve different models per call. Therefore: the **default backend is a deterministic local hash embedding** (`local-hash-384` — offline, free, stable forever; lexical-strength semantics), and the **freellmpool backend requires a pinned model** (`BEBSHAX_EMBEDDING_BACKEND=freellmpool` + `BEBSHAX_EMBEDDING_MODEL=…`). Every row stores its `embedding_space` tag and retrieval filters to the query's space — vectors from different spaces are never compared.
- **Reflection:** ≥8 episodic memories → latest batch summarized via `MEMORY_SUMMARIZATION` (fast pool) into ≤3 first-person `reflection` items at importance 0.8. Best-effort: unparseable output logs and skips — reflection can never break a conversation.
- Historical Phase-9 pgvector verification: 20 memories → expected top-k ordering; reflection stored and retrievable. The ML continuation passed the two existing PostgreSQL integration tests, but did not exercise cross-conversation retrieval live.

## Interviews (Phase 10)

Multi-turn interviews with a **stable identity** — the persona is composed per turn, never regenerated.

- **Per-turn composition** (`bebshax/interview/engine.py`): system = immutable identity card (`build_identity_card`, byte-identical every turn) + in-character constraints + business context + objective + top-k retrieved memories (Phase 9) + evidence themes; history = ALL prior turns; then the new interviewer message. If nothing fits, the router raises `ContextWindowExceeded` — identity/evidence are never truncated (R2). Memories legitimately evolve between turns; the identity never does.
- **Routing:** `PERSONA_INTERVIEW` → conversation pool. Each exchange is written back as an episodic observation memory (importance 0.4); `MemoryService.reflect()` distills them after conversations.
- **REST:** `POST /api/personas/{id}/conversations` · `POST /api/conversations/{id}/messages` → `{reply, turn_number, served_by}` · `GET /api/conversations/{id}` (transcript). 404/413/503 mappings as elsewhere.
- **Historical verification (2026-08-23):** an unstored 5-turn LLM-era interview smoke reported provider changes with name, age, and occupation retained. The old authless interview script is not the current authenticated demo procedure. This observation is not a benchmark of ML personas or cross-route quality.

## REST API (`bebshax/api/personas.py`)

| Endpoint                             | Purpose                                           | Errors                                                                                     |
| ------------------------------------ | ------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `POST /api/businesses`               | create business                                   | —                                                                                          |
| `GET /api/businesses`                | list                                              | —                                                                                          |
| `POST /api/businesses/{id}/personas` | select + store one synthetic persona              | 404 unknown business · 422 unsupported ML context/exhaustion · 503 unavailable local model |
| `GET /api/personas/{id}`             | full profile incl. attributes, evidence, warnings | 404                                                                                        |

App wiring (`main.py` lifespan) now also connects **Sazid's `ProvenanceSink` to the PoolRouter** — every LLM request lands in `llm_requests` (fail-soft; DB issues never fail a request).

## Verification

After building the local artifact, the focused offline conversion check is:

```powershell
.venv/Scripts/python.exe -m bebshax_persona_ml smoke --backend --input ml_persona/examples/business.json
```

The post-sync 2026-09-09 run passed all five stages: source, prepared, model,
generation, backend mappings/schema/zero observed evidence. This does not invoke
settings, a DB, network, or an LLM. The other local suites and checks passed at
the scopes in [Post-Sync Verification](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09).
The weaker performance than lexical TF-IDF remains recorded in
[EXPERIMENTS.md](../ml_persona/EXPERIMENTS.md).

Earlier live checks persisted and read back five unique age-bounded personas
with 22 synthetic claims reported and zero LLM generation calls in a fresh local
PostgreSQL database. Seven Freellmpool responses covered context, ten role
suggestions, and two interview turns with four 384-dimensional memory rows.
Linux loaded the Windows-trained artifact and generated five profiles with
networking disabled. These checks were not repeated after sync and are smoke
observations, not a success rate or customer-quality result. Before upstream
styling, desktop passed and mobile header controls clipped; the token-only
correction neither fixes nor reverifies that defect. Full Compose app/web and
cross-conversation retrieval rehearsals were not repeated. Commit, push, and CI
results are tracked separately in the [implementation log](IMPLEMENTATION_PLAN.md),
not claimed successful here. The older dated examples above remain historical.

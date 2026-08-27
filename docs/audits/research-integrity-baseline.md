# Research Integrity Baseline — 2026-08-28

Baseline snapshot taken **before** the Research Integrity, Trust & Showcase Hardening pass. Repository state: `a15dcc6` (all 15 phases complete, pushed). This document records what exists, what the gates report, and the capability inventory the auditor agents start from. The repository — not this document — remains the source of truth.

## 1. Automated gates (fresh runs, this machine)

| Gate | Result |
| --- | --- |
| Backend suite `pytest apps/backend/tests -q` | **423 passed**, 3 DB-integration deselected |
| Frontend `npm test -- --run` | **79 passed** (17 files) |
| Frontend `npm run build` (tsc + vite) | green |
| Theme drift `npm run theme:check` | 0 files needing tokenization |
| Offline evaluation `run_evaluation.py --suite all` | `eval_report_20260828_035252.{md,json}` — 2 persona samples, 7 routing strategies under chaos, 2 replay suites |

## 2. Capability inventory vs. the hardening prompt

| Prompt area | Current state (verified in code) |
| --- | --- |
| Claim classification | `ProvenanceClass` = OBSERVED / INFERRED / SYNTHETIC per attribute (`persona/schema.py`); coercion strips fake citations and downgrades (never upgrades). No UNKNOWN class. |
| Evidence binding | `evidence_ids` per attribute → `Evidence` objects (source, text, relevance, confidence); claim-level provenance in the study pipeline; evidence inspector UI (Evidence Laboratory). |
| Uncertainty | `confidence: float \| None` on attributes/evidence; grounding ratio (evidence-linked/total) surfaced as % in UI; consistency score. No qualitative labels (High/Medium/Low). |
| Persona validity | Deterministic consistency rules (age/occupation, income/luxury, location/timezone) + one refinement budget + explicit `PersonaGenerationFailed(violations)`; `personas/validator.py` for study-scoped grounding scoring; optional CRITIC pass. Contract enforced in code, not yet documented as a contract. |
| Dataset analysis | `datasets/` package: discovery, parser, profiler, security (upload hardening), segmenter, validator; manifest with pinned revisions + sha256; licenses in data/DATASETS.md. Representation-gap/skew surfacing depth = audit target. |
| Behavior follows state | Interview engine composes identity card per turn (byte-identical, test-asserted) + memory retrieval + full history or explicit CWE; live 5-turn cross-provider consistency verified 2026-08-23; automated long-conversation drift tests = audit target. |
| Memory provenance | `memory_items`: kind (semantic/episodic/reflection), importance, recency, embedding-space tag; scoring 0.6·cos + 0.25·recency + 0.15·importance. Source/confidence per item = audit target. |
| Cross-persona synthesis | Study reports exist (`StudyReports`, report generator, `REPORT_GENERATION` task). Supporting/contradicting-persona structure = audit target. |
| Reproducibility | Full `ProvenanceRecord` per LLM call (attempts, served_by, tokens, latency) persisted to `llm_requests`; `PersonaGenerationRun` records; dataset manifest pinned revisions + checksums; persona `version` field. Prompt/evaluator version identifiers = audit target. |
| Routing | Verified end-to-end by the Phase 14 acceptance matrix (13 scenarios → named tests, docs/IMPLEMENTATION_PLAN.md). |
| Routing experiment | 7 strategies (HYBRID default) + chaos sim + RouterArena/xRouteBench replay (`bebshax/evaluation/`, docs/EVALUATION.md). Persona-quality-per-strategy measurement not wired (documented limitation — capability metadata absent from replay sets). |
| Security | JWT env-only + rotation, burned-default rejected; password policy; rate limiting; tenancy columns; dataset upload security module; R4 clean history. Known documented gaps: demo Google auth (frontend fallback), single-worker rate-limit storage. |
| Integrity language | data/DATASETS.md prohibits fine-tuning and flags PersonaHub as never-citable; synthetic-vs-real framing in product copy = audit target. |
| UX/Showcase | Light/dark tokens, GSAP motion, responsive (390/768/1440 verified), skeletons, error turns, CACHED badges, provenance view. Fresh-user walkthrough = audit target. |

## 3. Baseline evaluation outputs

- `data/metadata/eval_report_20260828_035252.md` (fresh): persona quality on 2 fixture samples (validity, grounding ratio, consistency incl. a deliberately inconsistent sample flagged), 7-strategy chaos table (100 % success under scripted failures), replay alignment (HYBRID/LEAST_USED/QUALITY_FIRST/LATENCY_FIRST 100 %; ROUND_ROBIN 34–50 %; CAPABILITY_FIRST/QUOTA_AWARE 0 % on xRouteBench — capability metadata absent from that set).
- Live-path reference points (prior audited sessions, provenance in `llm_requests`): persona generation ~44 s free-tier; identity held across ovh→kilo→llm7 mid-interview failover; local gate llama3.2:3b 9.65/10 at ~6 s/turn.

## 4. Known pre-existing issues carried into this pass

- `Duplicate Operation ID` FastAPI warnings in `api/evidence.py` (cosmetic).
- Google sign-in is a frontend demo fallback (`POST /api/auth/google` 404s); each click mints a fresh local user.
- `model_registry` capability/score columns are schema-only (documented in docs/MODEL_REGISTRY.md).
- Free-tier latency 30–190 s for cloud persona generation.

## 5. Audit protocol for this pass

Independent auditor agents (architecture; research integrity + persona quality; dataset analysis; interview/memory behavior; evaluation + reproducibility; security; UX/showcase judged in-browser) each return scored findings. The Lead Agent consolidates, implements only justified fixes (prompt §0: reject unnecessary items with reasons), re-runs gates and affected auditors, and appends the final audit report to this directory.

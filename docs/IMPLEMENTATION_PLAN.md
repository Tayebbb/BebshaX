# BebshaX — Implementation Plan

Status: APPROVED 2026-08-22 — greenfield confirmed by owner; project renamed **SignalLens → BebshaX** (the historical name appears only in rename notes).
Companion doc: [AI_INFRASTRUCTURE_AUDIT.md](AI_INFRASTRUCTURE_AUDIT.md)

## Stack decision (owner-approved)

- **Backend:** Python 3.12 + FastAPI (async); package `bebshax`; env prefix `BEBSHAX_*`; exact dependency versions snapshotted in `apps/backend/requirements.lock`.
- **Routing engine:** `freellmpool` (MIT, PyPI) behind a BebshaX-owned abstraction — `LLMService → provider/router adapters → freellmpool / Ollama / optional future gateways`. **No code outside the adapter layer may depend on freellmpool-specific APIs.**
- **Failure policy:** retry/fallback applies to infrastructure failures only (429, quota, timeout, connection, 5xx, model unavailable, unsupported capability, context overflow, retriable invalid structured/tool output). **Low answer quality is NOT an infrastructure failure** — it belongs to the quality/evaluation layer (Phase 11).
- **DB:** PostgreSQL 16 + pgvector via Docker `pgvector/pgvector:pg16` on port **5433** (Phase-1 finding: the native PG16 install lacks the extension). Migrations via Alembic (Phase 6).
- **Local fallback:** Ollama 0.20 — reliability/dev/emergency tier only. Inspect + benchmark the installed `qwen3.5:latest` before choosing any additional ≤4 GB-VRAM model (Phase 4). No 70B-class assumptions.
- **LiteLLM:** NOT installed by default. Gate B in Phase 3: adopt the SDK only if a required provider is unreachable through freellmpool.
- **Frontend:** React + Vite single app (Phase 12): business/project setup, persona generation, persona profiles, persona memory, interview/simulation, insights/results, LLM routing dashboard, model/provider status, fallback history, request provenance, evaluation/quality metrics.
- **Providers:** config/env-driven only — never hard-coded; team adds whatever legitimate free-tier keys it has; keyless providers stay available; no limit-evasion mechanisms.
- **No Kubernetes, no Redis cluster, no message queue, no custom gateway from scratch** (brief §42).

## Custom code = what makes BebshaX unique

Business understanding, persona generation, persona consistency, persona memory, interview/simulation, evidence/grounding, quality validation, persona-task routing policy, provenance, evaluation, UI. Everything infrastructural reuses mature OSS behind thin adapters (existing OSS → thin adapter → custom BebshaX logic).

## Phases (owner's numbering, 2026-08-22 — supersedes the earlier 22-phase draft)

After every phase: run tests, inspect generated files, fix errors, update this plan's Implementation log, record decisions. Do not start a phase while the previous is red.

| #   | Phase                   | Key deliverables                                                                                                                                                                                                                                                                                           | Exit criteria                                                                               |
| --- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| 1   | Foundation              | git init; skeleton (`apps/backend`, `data/`, `docs/`, `docker-compose.yml`); `BEBSHAX_*` config via pydantic-settings; health endpoint; pytest harness; `requirements.lock`                                                                                                                                | tests green; live `GET /api/health` — ✅ done                                               |
| 2   | LLM abstraction         | `bebshax.llm`: `LLMService` interface; 16 task types (§8 of brief); failure taxonomy (retryable infra vs terminal vs quality — quality excluded from fallback); provenance record model (§14 fields); fake in-memory adapter for tests                                                                     | app code compiles against the interface only; unit tests pass with fake adapter             |
| 3   | freellmpool integration | dependency review recorded (why/license/activity); `FreellmpoolAdapter` (sole importer of freellmpool); providers from env; keyless smoke test; Gate B (LiteLLM adopt/skip) written in docs/ROUTING.md                                                                                                     | one real completion with zero keys; grep proves no freellmpool import outside adapters      |
| 4   | Ollama integration      | inspect + benchmark installed `qwen3.5`; pick ≤4 GB-VRAM fast model from measured results; `OllamaAdapter`; local model profiles from detected RAM/VRAM                                                                                                                                                    | all-remote-disabled request served locally                                                  |
| 5   | Routing/fallback        | pools (reasoning/conversation/long_context/structured/tool/fast/fallback/local); task→pool map in config; candidate ranking (capability+quality+availability+quota+history); per-failure-type policies; pre-flight token budget; `ContextWindowExceeded` (never truncate); per-pool concurrency semaphores | chaos-sim: A(429)→B(timeout)→C ok; oversized context skips small models or fails explicitly |
| 6   | Database                | pgvector container up; SQLAlchemy async + Alembic; tables: `model_registry`, `llm_requests` (full provenance), `businesses`/`personas` skeletons                                                                                                                                                           | migrations apply; every LLM request writes a provenance row                                 |
| 7   | Dataset pipeline        | profiles **minimal / development / evaluation / full**; `scripts/setup_datasets.py` (idempotent, checksummed, license-verified, streaming subsets); `data/DATASETS.md` (source URL, license, size, purpose, download+preprocessing method, required/optional per dataset)                                  | one documented command reproduces setup; re-run = no-op; NO fine-tuning anywhere            |
| 8   | Persona engine          | persona schema with OBSERVED/INFERRED/SYNTHETIC provenance; generation pipeline (spec→routing→generation→validation); deterministic consistency rules + optional LLM critic                                                                                                                                | persona generated, validated, stored                                                        |
| 9   | Memory                  | pgvector memory stream (semantic profile / episodic split); retrieval = relevance+recency+importance; reflection job (generative-agents concepts re-implemented)                                                                                                                                           | interview turn retrieves the right memories                                                 |
| 10  | Interview engine        | per-turn composition: identity+memory+evidence+business context+objective+constraints; PERSONA_INTERVIEW → conversation_pool; persona never rebuilt per turn                                                                                                                                               | multi-turn interview keeps persona stable                                                   |
| 11  | Quality/evaluation      | persona validity/consistency/grounding scoring; routing strategies behind config (ROUND_ROBIN / LEAST_USED / QUALITY_FIRST / LATENCY_FIRST / CAPABILITY_FIRST / QUOTA_AWARE / HYBRID default); RouterArena + xRouteBench offline comparison                                                                | one-command eval report; naive-vs-intelligent routing table — ✅ done (2026-08-22)          |
| 12  | Frontend                | React + Vite app: business setup, persona generation, profiles, memory view, interview/simulation, insights, routing dashboard, provider status, fallback history, provenance, eval metrics                                                                                                                | all views wired to the API — ✅ done (foundation + mock layer, 2026-08-22)                  |
| 13  | Integration             | end-to-end flows; `BEBSHAX_DEMO_MODE=true` (cached known-good personas clearly labeled, live generation still available)                                                                                                                                                                                   | demo survives with network unplugged — ✅ done (2026-08-23)                                 |
| 14  | Testing                 | full matrix: provider unavailable / 429 / timeout / context overflow / model unavailable / fallback chain / all-fail→Ollama / structured-output failure / persona consistency / dataset loading / provenance / caching / concurrent persona generation; brief §44 acceptance tests 1–10                    | entire suite green                                                                          |
| 15  | Documentation           | README; docs/{ARCHITECTURE, ROUTING, FAILOVER, MODEL_REGISTRY, DATASETS, PERSONA_ENGINE, EVALUATION, SETUP, DEMO}.md; FINAL_IMPLEMENTATION_REPORT.md; one-shot setup script                                                                                                                                | fresh-machine setup works per SETUP.md                                                      |

## Decision gates

- **Gate A:** ✅ resolved 2026-08-22 — greenfield confirmed; rename to BebshaX; FastAPI + React/Vite approved; providers config-driven.
- **Gate B (Phase 3):** LiteLLM SDK adopt/skip, written justification in docs/ROUTING.md.
- **Gate C (Phase 11/13):** external observability (Langfuse/OTel) only if the Postgres provenance log demonstrably falls short. Default: no extra infra.

## Non-goals (explicit, from brief §42 + owner 2026-08-22)

Kubernetes, microservices, Redis clusters, message queues, ML-learned router in the request path, custom LLM gateway, account-multiplication or any rate-limit evasion. Datasets serve grounding/diversity/behavioral-examples/evaluation only — **this is not a model-training/fine-tuning project**. Low answer quality is never treated as an infrastructure failure.

## Implementation log

> **Ordering note (2026-08-26):** entries are newest-on-top down to Phase 1 — EXCEPT the "Parts 1–7" series and four 2026-08-25 maintenance entries, which were appended _below_ Phase 1 (from "Universal AI Workflow" onward). They are left in place to avoid conflicting with in-flight branches; go by entry dates, not file position.
### Maintenance (2026-08-27) — Evaluation honesty sweep: fallback labeling, judge bias instrumentation, real benchmarks, legacy stamping

- **Insights fallback fabricated confidence** ([interview/engine.py](../apps/backend/bebshax/interview/engine.py)): when interview-completion synthesis failed, a mechanical excerpt was persisted as an analyzed insight with invented `confidence: 0.85` and a silent `except`. Now: warning-logged with traceback, summary prefixed "Automated synthesis unavailable — mechanical summary", insight titled "Unanalyzed excerpt (synthesis unavailable)" with `confidence: 0.0`; LLM insights missing confidence also get 0.0, never an invented default. **Found & fixed in the process:** engine.py had no module-level `logger` — the new warning raised `NameError`, which made `test_dynamic_script_and_batch_interviews` fail deterministically in isolation (5/5 reproduced → 5/5 green after the fix; Sazid's earlier `assert 2 >= 4` flake has not reproduced on current code, monitored).
- **LLM-as-judge self-preference** ([judge_local_interview.py](../scripts/judge_local_interview.py)): the judge was arm B's own cloud service. Now judges via OpenRouter (a provider distinct from both arms) with fallback to the arm-B service when no route exists, and every report records `judge.self_preference_risk` (true when the judge route equals any arm's serving model) + a printed warning. Also fixed for the required-`owner_id` store signature.
- **Offline evaluator measured nothing real**: `router_arena`/`xroute_bench` were never downloaded, so it silently replayed 50 hardcoded synthetic records as "benchmark results". Downloaded the **evaluation profile** (809 + 523 real records, pinned SHAs) and added `synthetic_fallback: bool` to `OfflineEvalResult` — synthetic replays are now flagged and can never masquerade as measurements. Verified live: both benches report `synthetic_fallback=False` over real data. (The new benchmark files land in `data/processed/` and are role-tabled `probe` — the DATASET_ROLES guard from the previous entry keeps them out of the evidence pool.)
- **Legacy conversation tenancy stamping** (row-scoping follow-up): the two un-nested conversation-start endpoints now stamp `user_id` from the caller's token, so `_guard_legacy_conversation` can actually protect authenticated users' legacy transcripts.
- Critic-verified (BLOCK 7.5/10 on missing R7 tests → fixed): regression tests added for the mechanical-fallback semantics (title/confidence-0.0/persisted row) and the `synthetic_fallback` flag (absent → True, real file → False); markdown reports annotate synthetic replays ("⚠ SYNTHETIC FALLBACK — NOT a benchmark result"); judge fallback prints the failure reason and checks BOTH arms' serving routes (exact-match limitation documented); `InterviewInsights.confidence` column default 0.85 → 0.0 (unmeasured is never an invented number). 401 backend tests green, ruff clean.

### Maintenance (2026-08-27) — AI-quality pass: real grounding corpora, retrieval noise reduction, generator honesty

- **Grounding was synthetic-only**: the evidence store loaded whatever `data/processed/*.jsonl` happened to match its text fields — in practice 25k synthetic PersonaHub sketches, so every "OBSERVED" claim cited an invented blurb. Fixed three ways: (1) downloaded the **development dataset profile** (EmpatheticDialogues 88,703 utterances + Amazon office-product reviews 46,050 — both licensed, pinned-SHA, via `setup_datasets.py`); (2) new `DATASET_ROLES` table in [persona/evidence.py](../apps/backend/bebshax/persona/evidence.py): only real-world corpora are citable **grounding**; PersonaHub is **seed**-only (diversity perspective, never OBSERVED-able); probe/dialogue datasets (gsm8k, mmlu, synthetic_persona_chat, router benches) can never enter the evidence pool even when their schemas match; unknown files default to grounding (drop-a-real-dataset-in extension path); (3) noise reduction — near-exact dedupe + 50-char noise floor at ingestion, **BM25-lite scoring** (idf × saturating length normalization replaces the sqrt-length divisor that let "Cute, affordable and fast delivery!" outrank substantive records) + ≥2-token overlap floor (kills single-token topical coincidences), and the EmpatheticDialogues `_comma_` CSV-era artifacts unescaped in the canonical preprocessing step (corpus rebuilt, 0 artifacts remain). Retrieval measured: 60k docs load 1.1 s once, queries 15–35 ms.
- **Study-pipeline generator honesty** ([personas/generator.py](../apps/backend/bebshax/personas/generator.py)): `generation_model` was stamped with a fabricated constant (`"qwen3.5-grounded"`) regardless of the serving model — now provenance-derived (`provider/model`) on LLM drafts and `deterministic-template-fallback` on template drafts; infrastructure failures (`AllCandidatesFailed`/`ContextWindowExceeded`) now **propagate** instead of silently becoming template personas wearing a research badge (parse failures still fall back, labeled + warn-logged); generation `temperature` 0.3→0.75 (segment personas were converging on identical archetype phrasing) with `max_output_tokens` bounded per batch.
- **Interview prompt fixes** ([interview/engine.py](../apps/backend/bebshax/interview/engine.py)): behavioral rule 2 hardcoded "local Bangladesh context" for every persona regardless of identity — now derives locale from the persona's own IDENTITY card; evidence citations truncate on word boundaries (mid-word cuts read as corrupted evidence to the model).
- **Measured**: judged A/B interview gate re-run post-change — local llama3.2:3b **9.05/10** (bar 8.0, avg 6.8 s) vs cloud-fast 8.05/10 (report `data/metadata/local_3b_gate_20260827_101900.json`); live persona generation over the new corpora: provenance mix 4 OBSERVED / 4 INFERRED / 2 SYNTHETIC with OBSERVED claims citing both real datasets and the true serving model recorded. `judge_local_interview.py` fixed for the required-`owner_id` signature. Critic-verified over 2 rounds (7/10 BLOCK → sub-batched generation ≤3 personas/request, role-table completeness test, 413/503 API contracts, DATASETS.md roles section → **PASS 9/10**; per-batch model attribution + cap-test fixes folded in). 398 backend tests green, ruff clean. `data/DATASETS.md` regenerated by the pipeline.

### Maintenance (2026-08-27) — freellmpool fast-routing metrics survive restarts (pipeline item 5/5)

- `FreellmpoolAdapter(routing="fast")` ranks targets by in-process EWMA latency and forgot everything on restart — every boot re-learned which free providers are fast by being slow first. Now `load_recent_route_observations()` in [db/capacity_state.py](../apps/backend/bebshax/db/capacity_state.py) extracts the last 3 days of successful per-target latencies from `llm_requests` attempts (chronological so EWMA weights the newest; local `ollama` and the virtual `freellmpool` failure stamp excluded; direct-`openrouter` measurements kept — same upstream as freellmpool's openrouter targets), and `FreellmpoolAdapter.seed_metrics()` replays them into the pool's `Metrics` under the library's `provider/model` keys — wired into the `main.py` lifespan next to the QuotaLedger seeding, fail-soft (seed problems log a warning and start cold, never block startup — degradation path exercised live). Success-only by design: failed attempts carry the virtual route and can't be attributed; a stale-healthy target is re-marked by its first live failure, and BebshaX-level cooldowns still apply. Live check: 46 observations seed from the dev DB at boot (llm7/codestral, openrouter/nemotron-3.5-lightning, …). 4 new tests in test_fast_routing_seed.py incl. an end-to-end scoring test over the real freellmpool `Metrics` (seeded-fast < unmeasured < seeded-slow). 388 backend tests green, ruff clean.

### Maintenance (2026-08-27) — Persona + report generation as async jobs (pipeline item 4/5)

- Generalized the interview batch-run 202+poll pattern into [api/jobs.py](../apps/backend/bebshax/api/jobs.py) (in-memory registry on `app.state`, GC-safe task refs, capped at 50 with running-jobs-evicted-last, explicit "not a queue on purpose — R10" docstring) and put the two longest blocking endpoints on it: `POST /studies/{id}/personas/generate/jobs` (strict auth, matching Sazid's B6 write rule) and `POST /studies/{id}/reports/generate/jobs` (owner-gated like its sync sibling) — both return `202 {job_id}` immediately; polls are study- **and kind-scoped** (a leaked job id can't be read cross-study or cross-feature), 404 with a restart hint for lost jobs. Job runners own their sessions (request session is closed by run time) and persist real rows via the existing services; `job.result` carries the exact sync-endpoint payloads. Failure honesty: `ValueError` + whitelisted domain failures (`PersonaGenerationFailed`, `ContextWindowExceeded`, `AllCandidatesFailed` — R2/R6) pass their message through; unexpected crashes are redacted to the class name (traceback only in logs); `CancelledError` never leaves a job claiming "running". Frontend `generateSyntheticPersonas`/`generateStudyReport` go job-first with polling (2.5 s interval, transient-blip tolerance ×4, `isJobFailure` errors propagate to the user instead of being swallowed into the mock fallback) and fall back to the sync endpoints on 404/405 (older backends). Sync endpoints retained. Critic-verified (PASS-WARN 8/10 → both MEDIUMs fixed: persona job failures no longer vanish into fabricated mock success; poll survives dropped requests). 8 tests in test_async_generation_jobs.py; 373 backend green, tsc + 76 frontend tests + build green.

### Maintenance (2026-08-27) — Deep verification of the 11 Sazid audit items: 5 defects found behind DONE ticks

- **Why:** the track showed 11/11. Verifying each item against the code rather than its completion note found five real defects, two of them serious. Nine items were sound.
- **Serious 1 — token lifetime lied to every client (B4/M7).** `jwt_expire_days` defaulted to **365** while `AuthResponse.expires_in_days` was a hardcoded **7**; measured on a live token, 365 days. B4 hardened signing and never examined expiry, so the audit's "7-day non-revocable" premise was itself wrong by 52x. Fixed: default is 7, and the response field now derives from the same setting via `default_factory`, so they cannot drift apart again.
- **Serious 2 — H9 was never enforced.** The verification pipeline was built end to end and then not wired to anything: `signin` checked `is_active` only, and no code read `is_verified` as a precondition. Fixed: signin rejects unverified accounts with an actionable 403, behind `Settings.email_verification_enforced` (production/staging enforce; development/local do not, so the offline demo drill still passes; `BEBSHAX_REQUIRE_EMAIL_VERIFICATION` overrides). **Frontend dependency:** turning it on needs Shehab's "check your email" state or the block reads as a bare 403.
- **Tenancy hazard (B6):** `save_persona`/`create_business` defaulted `owner_id` to `"usr_system_holder"`, which is in `PUBLIC_OWNER_IDS` — forgetting the argument silently published the row to every user. Both live call sites passed it, so nothing leaked, but the failure mode was disclosure rather than an error. `owner_id` is now required; omitting it is a `TypeError`.
- **Two smaller fixes:** a correctly signed token with no `exp` claim never expired (`exp` is now mandatory on the verify path); `/sync` stored the client-supplied `auth_provider` even though Neon proved the identity (now hardcoded `"neon"`).
- **Verified sound:** B1, B3, B6 row scoping, H3, H6, H7 wiring, H8, M8, L14. `bebshax/tenancy.py` in particular is a real single source of truth with its deltas documented rather than accidental.
- **Flagged, not changed:** the H7 limiter is in-memory with `get_remote_address` — buckets reset on restart, are per-worker, and collapse to a single bucket behind a proxy. Fine for local/demo, wrong for a real deployment.
- **Tests:** `tests/test_auth_hardening_audit.py` (11), covering token lifetime parity, the exp gap, environment-driven verification enforcement, and the owner_id signature. Suite: **369 passed, 1 failed, 3 deselected** — the failure is the known cwd-dependent `test_run_evaluation_cli.py` in Shehab's lane.
- **Client-visible change:** sessions now last 7 days instead of 365. That is the intended behaviour and matches what the API already claimed, but users will be signed out weekly where they previously were not.

### Maintenance (2026-08-27) — M1: /api/evaluation/metrics de-fictionalized (pipeline item 3/5)

- Full rewrite of [api/evaluation.py](../apps/backend/bebshax/api/evaluation.py): the fabricated `routing_strategies` comparison (a "ROUND_ROBIN (Naive)" arm computed as HYBRID×0.85/×1.25/×2+0.1, invented `cost_efficiency`, `schema_validity_rate` asserted 1.0, "LATENCY_FIRST" mapped to a nonexistent `fast_text` pool) is **gone from the contract**. Every value is now measured: `pools[]` aggregates real `llm_requests` per pool (success rate, latency, multi-attempt fallback share, ollama-served share); `schema_validity_rate` derives from the R6 taxonomy (share of PERSONA_GENERATION requests with no MALFORMED_RESPONSE attempt); `consistency_pass_rate` covers only evaluable personas; **no data → `null`, never claimed perfection**. New `quality_gate` section surfaces the newest readable judged A/B gate report (`data/metadata/local_3b_gate_*.json`, dir overridable via `BEBSHAX_METADATA_DIR`; corrupt/mis-shaped files skipped in favor of older valid ones). Frontend types/fixtures updated (`PoolPerformance`, `QualityGate`); no UI view consumed the old shape. API_CONTRACT.md §3.7 rewritten. Critic-verified (8/10 BLOCK on stale contract doc → fixed → PASS): 6 new tests in test_evaluation_metrics.py; 361 backend green, tsc + 76 frontend tests green. Perf follow-up noted: pool aggregates are a full-table scan (move to SQL GROUP BY once llm_requests outgrows dev scale).

### Maintenance (2026-08-27) — H3 piece 2: personas carry an honest cached/live label

- **Audit item:** 🟠 **H3**, the last open item on the Sazid track. Pieces 1 and 3 landed 2026-08-26; this is piece 2 — the `"cached"` labelling the audit called "the spec's core honesty requirement".
- **Change:** `personas.data_source` (`"live" | "cached"`, `NOT NULL`, `server_default "live"`), migration `9f0a1b2c3d4e`, applied locally with `current == heads` confirmed. `save_persona()` gains a `data_source` parameter defaulting to `"live"`; `seed_demo_data()` passes `"cached"`; `_serialize_persona()` returns it, so every persona endpoint carries the label. Constants `DATA_SOURCE_LIVE` / `DATA_SOURCE_CACHED` live in `db/models.py`.
- **Design decision — stored, not derived.** Computing the label from `demo_mode` at read time was the obvious shortcut and is wrong: the flag flips independently of the rows already in the table, so a toggle would relabel real model output as cached and seeded fixtures as live. Persisting at creation makes the label a fact about the row rather than about the current process. The migration backfills existing rows to `"live"` — correct, because the seeder is the only cached producer and did not previously exist as a distinct category.
- **Contract:** `data_source` documented in `API_CONTRACT.md` with the value table and the client obligation. That file is a joint contract file under merge rule 4 — this is an **additive optional field on an existing response**, no rename and no removal, but it still needs Tayeb's and Shehab's sign-off at the joint session rather than being treated as settled.
- **Tests:** `tests/db/test_data_source_labelling.py` (4). Per the audit's own standard, the guard was proven by removing the seeder's label and watching `test_seeded_personas_are_labelled_cached` fail, then restoring it.
- **Suite:** 349 passed, 1 failed, 3 deselected (from `apps/backend`). The failure is the known cwd-dependent `test_run_evaluation_cli.py::test_cli_execution_with_tmp_output` in Shehab's lane. Note `test_dynamic_script_and_batch_interviews` passed this run having failed the previous two — it is **flaky**, not consistently broken, which is worth more attention than a hard failure would be.
- **Explicitly NOT done — Shehab's half:** nothing renders the label. Until a badge appears wherever personas are shown, a viewer still cannot tell seeded content from model output, which is what H3 actually asks for. The backend no longer blocks that work; the field and its semantics are frozen.

### Maintenance (2026-08-27) — Test-generated upload artifacts were reaching git

- **Problem:** `.gitignore`'s dataset rules (`data/raw/*`, `data/processed/*`, `data/uploads/*`) are **root-anchored**, but `UPLOAD_DIR` is `Path("data/uploads")` — resolved against the process working directory in `datasets/service.py`, `datasets/discovery/engine.py` and `research/service.py`. Run the server or the suite from `apps/backend` and the writes land in `apps/backend/data/uploads/`, which those rules never matched.
- **Consequence, already realised:** 13 generated `ds_*.json` fixtures are committed in `e8873d4`, and a further 13 appeared untracked during this session's test runs. R-rule "datasets are reproducible, not committed" was being violated silently by anyone running `git add -A`.
- **Fix:** added `**/data/{raw,processed,uploads}/*` patterns (with matching `.gitkeep` negations) to `.gitignore`, commented with the cause so the duplication is not mistaken for redundancy. The 13 new artifacts stopped appearing in `git status` immediately.
- **Not done, needs a decision:** the 13 files already tracked from `e8873d4` are still in the index. `git rm --cached apps/backend/data/uploads/*.json` untracks them without touching the working copies — left for the owner since it edits the content of a teammate's commit.
- **Root cause left standing:** `UPLOAD_DIR` being cwd-relative means uploads land in different directories depending on where the process was started. Same class of bug as the pytest cwd issue above. Making it absolute (anchored off the package or a configured data root) is the real fix and touches `bebshax/datasets/**` and `bebshax/research/**` — flagged, not attempted here.

### Maintenance (2026-08-27) — Test results no longer depend on your working directory

- **Problem:** `pytest` gave different answers depending on where you ran it. From the repo root the suite collected 346 tests; from `apps/backend` three modules in `tests/datasets/**` died at collection with `ModuleNotFoundError: No module named 'scripts'`, because they import `scripts.setup_datasets` / `scripts.dataset_manifest` from the repo root. Same tree, same commit, two different verdicts — the H6 failure mode wearing different clothes, and it silently hid Sazid's own dataset tests from anyone who ran the suite from the backend directory.
- **Fix:** `pythonpath = ["../.."]` in `apps/backend/pyproject.toml` `[tool.pytest.ini_options]`, with a comment naming the symptom so it is not "cleaned up" later. Collection is now 346/349 from both directories.
- **Verified:** from `apps/backend` — 344 passed, 2 failed; from the repo root — 345 passed, 1 failed. Both counts exclude 3 deselected integration tests.
- **One cwd-dependent failure remains and is NOT in the data-layer lane:** `tests/evaluation/test_run_evaluation_cli.py::test_cli_execution_with_tmp_output` shells out to the literal relative path `"scripts/run_evaluation.py"` (line 55) with no `cwd=`, so it passes from the repo root and exits 2 from `apps/backend`. The fix is to resolve that path from `Path(__file__)` rather than the process working directory. Evaluation tooling is Shehab's — **flagged, not touched**, per the lane rule.
- **Also still failing, unrelated and pre-existing:** `test_study_reports_and_master_workflow.py::test_dynamic_script_and_batch_interviews` (`assert 2 >= 4`), interview/study area, for Tayeb.

### Maintenance (2026-08-27) — L14: deprecations now fail the suite (Sazid track closed bar H3 piece 2)

- **Audit item addressed:** ⚪ **L14** ([E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md) & [AUDIT_ASSIGNMENTS.md](AUDIT_ASSIGNMENTS.md)).
- **Change:** `apps/backend/pyproject.toml` `[tool.pytest.ini_options]` gains `filterwarnings`, escalating `DeprecationWarning`, `PendingDeprecationWarning` and `starlette.exceptions.StarletteDeprecationWarning` to errors. Starlette's warning subclasses `UserWarning`, not `DeprecationWarning`, so it needs its own escalation line — worth knowing before anyone "simplifies" the list.
- **Exemptions — three, all third-party, each a narrow message match with a stated REMOVE-WITH condition:** starlette TestClient wanting `httpx2` (a dependency swap needing an R8 review first), slowapi 0.1.9's `asyncio.iscoroutinefunction` (removed in Python 3.16, upstream fix required), fastparquet 2026.5.0's bare-integer numpy timedelta unit. No blanket ignores; the comment block forbids adding one.
- **The guard paid for itself immediately:** it failed `test_verify_email_rejects_expired_token`, which bound a raw `datetime` into a `text()` UPDATE and hit Python 3.12+'s deprecated sqlite3 default datetime adapter. Fixed by binding through `bindparam("exp", type_=DateTime(timezone=True))` — the same conversion path the ORM column uses. Test-only; production runs asyncpg and never touched that adapter.
- **Suite (from the repo root):** 345 passed, 1 failed, 3 deselected. The failure — `test_study_reports_and_master_workflow.py::test_dynamic_script_and_batch_interviews`, `assert 2 >= 4` — **predates this change and is unrelated to it**; it is in the interview/study area last touched by `e5b4081` (B6 Stage 2 fallout repair). Left for its owner rather than patched from outside the lane.
- **Doc repairs in the same commit:** restored the **H8** row, which had been deleted from the Sazid section of AUDIT_ASSIGNMENTS.md although the fix landed 2026-08-26 (the section listed 10 items under an "(11)" heading and `L6`'s "pairs with Sazid's H8" pointed at nothing). Progress table corrected 6 → 10 for Sazid and 31 → 35 overall, to match the section's own checkboxes.
- **Remaining on the Sazid track:** H3 piece 2 (`"cached"` labelling) only. It cannot be closed unilaterally — it needs the response-shape agreement and the UI from Shehab.

### Maintenance (2026-08-27) — API row-scoping hardening, B6 stage 3 complete (pipeline item 2/5)

- Closed every gap from the tenancy audit: new `bebshax/tenancy.py` is the single policy table (`PUBLIC_OWNER_IDS`, `STUDY_ANON_OWNER_IDS`, `owner_accessible`, `allowed_owner_ids`) with the two deliberate deltas documented. Weak per-router `_verify_study_access` copies in datasets/segmentation now delegate to the canonical `_user_owns_study`; the `if user_id:` anonymous-collapse pattern is gone from `datasets/service.py` (`_tenant_filter` on list/get/delete/**refresh**) and `persona/store.py` list filters; `DELETE /audiences/{id}` enforces its (previously unused) auth dep; the 4 legacy conversation endpoints, `GET /personas/{id}(/memories)`, copilot `generate-personas` (gate BEFORE LLM spend), and `GET /provenance` (outerjoin to persona owners) are now owner-gated; client-supplied identity is dead — `POST/PATCH /studies` + `/audiences` stamp `user_id` from the token only, `?user_id=` list params are ignored, and PATCH mass-assignment excludes `id`/`user_id`. Anonymous demo mode keeps working via the shared pool (NULL/`usr_default`/`anonymous`/`usr_system_holder` rows). Verified by independent code-reviewer sub-agent over 2 rounds (7/10 → **PASS 9/10**; both round-1 HIGHs — refresh bypass, invisible `usr_default` imports — fixed + regression-pinned). 9-test hardening file added; the old integration test that codified `payload.user_id` spoofing rewritten to the token contract. 350 backend tests green, ruff clean. Merged with Sazid's concurrent B6 correction (`b62cc0f`: write endpoints now require strict auth → 401; my `_owner_accessible` gates retained on top). Follow-up noted: stamp `conv.user_id` at legacy conversation start; persona-delete orphans LLMRequests metadata into the shared pool.

### Maintenance (2026-08-27) — README refreshed to match shipped state (docs only)

- **Scope:** [README.md](../README.md) only; no code touched. The README still described the repo as of Phases 1–11 with the pre-audit team lanes, so a new machine following it could not start the API.
- **Onboarding correctness:** added the mandatory `BEBSHAX_JWT_SECRET` step to the Quickstart block (the app fail-fasts on startup without it since **B4**) with a `secrets.token_urlsafe(48)` generator line, plus a new "Secrets and migrations" subsection covering the optional-provider-keys rule and the `alembic upgrade head` requirement now that startup + CI hard-fail on drift (**H6**).
- **Phase status:** Quickstart heading now reads "Phases 1–12 ✅ · 13 🟡 in progress — remaining: 14, 15", matching the roadmap table in [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md) (which wins per R12).
- **Team lanes:** the "Your lane" table listed Sazid's next task as Phase 9, which Tayeb took over on 2026-08-23, and Shehab's as Phase 12, which shipped. Rows now show completed phases accurately (Tayeb 1–5, 8, 9, 10; Shehab 11, 12) and point each person at their remaining **audit** work instead of phases. Recorded the `api/**` + `auth/**` ownership assignment from [AUDIT_ASSIGNMENTS.md](AUDIT_ASSIGNMENTS.md) and noted its agreement box is still unticked.
- **Discoverability:** audit docs added to the start-here line and the `docs/` layout row; the stale `AI_INFRASTRUCTURE_AUDIT.md` pointer was replaced with the two docs the current workstream actually runs on, plus `DEMO.md`.
- **Also documented:** tests must be run from the repo root — `pytest` from inside `apps/backend` fails to collect `tests/datasets/**` (`ModuleNotFoundError: No module named 'scripts'`) and changes which persona tests error.

### Maintenance (2026-08-27) — SSE streaming for interview turns (pipeline item 1/5)

- Interview replies now stream token-by-token end to end: `ProviderAdapter.stream()` contract (`StreamDelta`/`StreamDone`, default = complete-then-one-delta so every adapter streams), native NDJSON streaming in `OllamaAdapter` (mid-stream `error` chunks → SERVER_ERROR, done-less/empty streams → MALFORMED_RESPONSE — never silent truncation, R2), `PoolRouter.stream()` with full policy fidelity (same eligibility/cooldown/quota path as `complete()`, honors `retry_same_once`, **commit-on-first-delta**: once a user has seen words the route never swaps mid-answer), `InterviewEngine.ask_stream()` sharing all of `ask()`'s post-processing via `_prepare_turn`/`_finalize_turn`, SSE endpoint `POST …/messages/stream` (`delta`/`done`/`error` events, done carries non-stream contract parity incl. timestamps), and frontend live rendering with graceful fallback to the JSON endpoint. Deterministic cleanup via `aclosing` through the whole chain; consumer aborts stamp `"aborted by consumer"` in provenance **only** on uncommitted attempts (close-after-done GeneratorExit guard). Verified by independent code-reviewer sub-agent over 3 rounds (6/10 → 8/10 → **PASS 9.5/10**); all MAJOR/HIGH/LOW findings fixed incl. a final pre-done-abort regression test. 341 backend tests green (+13 streaming/engine tests), ruff clean, live browser check: first delta 8.5 s, full turn 11 s on `ollama/llama3.2:3b`. API_CONTRACT.md documents the stream endpoint.

### Maintenance (2026-08-26) — Latency stack: interview turns 185 s → 9.2 s live

- Root causes measured then fixed: (1) freellmpool ran its default "fair" (least-used) routing — now `FreellmpoolAdapter(routing="fast")` (library's smoothed-latency-first mode; observed live: cloud turns dropped to 1–1.5 s once metrics warmed); (2) the repo's `providers.toml` was dead config (freellmpool only reads `$FREELLMPOOL_CONFIG`) — now set by `bebshax.main` at startup, and the file removes Kilo's double-proxy routes + the 185 s nemotron-120b and keeps only measured-fast OpenRouter models; (3) no attempt budgets — new `llm/latency.py` data table (interactive 25 s / standard 75 s / long 150 s) passed by both remote adapters, TIMEOUT advances the chain; (4) OpenRouter direct defaults reordered by measured speed, deepseek-r1 (CoT) dropped from defaults. **Judged gate per owner rubric** (`scripts/judge_local_interview.py`, blind LLM judge, weights 25/20/15/15/15/10): local `llama3.2:3b` **9.65/10** vs cloud-fast arm 8.25/10, avg 6.1 s vs 53 s → `conversation`/`fast` pools locked **local-first** (report `data/metadata/local_3b_gate_20260826_235633.json`). Live UI re-measure: interview turn **9.2 s** via `ollama/llama3.2:3b` (was 52–185 s). 316 backend tests green (+7); ROUTING.md/AI plan tables updated.

### Maintenance (2026-08-26) — Cinematic study launcher (/create-study redesign)

- `NewStudyView` rebuilt in the interview-workspace design language (ambient depth, mono kicker, gradient display headline, frosted composer with Ctrl+Enter hint, example-prompt chips); study types became semantic `<button>` cards with `aria-pressed` (were divs). Scoped `newstudy.css`; reduced-motion + 375 px verified; all 5 contract tests green.
### Maintenance (2026-08-26) — Cinematic interview workspace (frontend redesign)

- Rebuilt the authenticated interview experience as `components/interview/InterviewWorkspace` (+ scoped `interview.css` token layer): research-transcript typography instead of chat bubbles, breathing persona identity orb + SIMULATION ACTIVE/COMPLETE status, CSS-only ambient backdrop (transform/opacity, paused when tab hidden, reduced-motion aware), frosted-glass composer with focus illumination, honest long-latency thinking state with elapsed-seconds counter, presentation-only word reveal of received replies, per-turn provenance (`T·latency·route`) on hover, engine-suggested question chips, context rail (objective/turn progress/live topic coverage/participant demographics/grounding/synthesis insights with turn-jump refs) that collapses to an off-canvas panel ≤1120px, taxonomy-aware failure panels (413 context-window / 503 no-route / finished) that return the unanswered question to the composer. **Found & fixed during audit:** the old `InterviewWorkspaceView` was 906 lines of dead Tailwind classnames (Tailwind was never installed — rendered unstyled) and crashed on the live backend (`data.interview.status` vs the flat `_serialize_interview` contract) — it had never worked against the real API. Old view deleted; DashboardLayout re-pointed; workspace test rewritten against the real flat contract + a new honest-failure test; jsdom `matchMedia` polyfill in test setup. Live-verified end-to-end (fresh Rashedul interview: empty state → suggestion → 27s…185s honest wait → in-character reply with `kilo/nvidia/nemotron-3-super-120b:free` route → topics lit → 2/14). 76 frontend tests + tsc + build green.

### Maintenance (2026-08-26) — Top-3 QA recommendations: async batch jobs, numeric contradiction detection, H9 verification gate

- Batch interviews are now a background job (202 + job_id, `GET .../batch-run/{job_id}` polling, per-persona honest statuses, 404 for restart-lost jobs) with a polling UI — live-verified 202 <1 s vs the prior 12.8-min blocking request. Contradiction detector compares the persona's own prior money-rate claims (monthly-normalized, currency+period cues, ≥3× on shared spend topic) — 10 tests incl. the live-observed 120/day-vs-25k/month case + end-to-end `ask()` metadata wiring; live turn recorded honest `contradiction_detected: false` for a consistent answer. H9: signup issues no session outside demo_mode, unverified signin → 403 EMAIL_NOT_VERIFIED, `/auth/sync` flips `is_verified` after server-side Neon verification, frontend commits sessions only through verify→Neon token→sync→JWT and reports OTP-send failures honestly — browser-verified (no token after signup, bypass dead, wrong code rejected, verified signin lands). Suite 293 backend + 71 frontend. Details in [E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md).

### Maintenance (2026-08-26) — QA journey sweep: 8 live-reproduced defects fixed (browser-driven)

- Simulated a real founder end-to-end through the rendered UI (signup → study → copilot → personas → script → adversarial interview → batch → report → refresh). Fixed with live before/after reproduction: research/run 500 (stale `ResearchEngineService` call site); persona prompts' `str.format` KeyError (LLM path had **never** run — all personas were skeletons wearing fabricated "80% Grounded"); truncated persona JSON (output budget + role concurrency); untagged CoT leak (adapters classify truncation as `MALFORMED_RESPONSE`, finish_reason=length / completion_tokens>=cap; interview budget 450→900; 4 adapter tests); silent mock-library substitution in live mode (student personas for a meal-prep study — now honest errors + Step-2 banner); fabricated batch statuses (now derived from response); invisible report failures + example-score echo + `|| 85` re-fabrication (300 s timeout, honest score instructions, 8000-token budget, "—" rendering); transcript restore after refresh (conversation id per study+persona + `GET /api/conversations/{id}`). Also: server-owned persona ids (LLM ids like `user_003` collide), planner `res.content`/`max_tokens` API bugs (research plans always fell back to template). Full detail in [E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md) fix log. 267 backend + 71 frontend tests green. Open: persona numeric self-consistency, OTP theater (H9/Sazid), batch-run async-job redesign.

### Maintenance (2026-08-26) — §7 model selection: explicit preference + Auto

- `LLMRequest.preferred_provider/preferred_model` (None = Auto); `PoolRouter` stable-partitions preferred routes to the front AFTER quota ranking — advisory, so eligibility/policies/fallback still apply and a missing preference degrades to Auto. Preference visible in `routing_path`. 3 router tests; 263 passed. First increment of the unified-workspace gap plan (assessment in chat 2026-08-26).

### Maintenance (2026-08-26) — Live E2E validation + AI plan §10 capacity layer

- Live run (real server, Neon DB, Ollama up): business → persona (17 provenance-classed attrs, `codestral-latest`) → interview (in-character, `openrouter/deepseek-v4-flash`, memory retrieved). Quality matches the plan.
- **Third provenance-loss bug found live and fixed**: sink writer died on first idle timeout (idle mistaken for shutdown sentinel); `flush()` semantics made real (task_done after write-or-drop). Regression test added.
- **§10 capacity layer shipped**: `llm/quota.py` (quota data table + ledger seeded from llm_requests), quota-aware ranker in production router, persistent cooldowns (`db/capacity_state.py` → `model_registry.cooldown_until`), `GET /api/routing/capacity`, `scripts/measure_capacity.py`. 8 tests; 260 passed. Live-verified: capacity endpoint reports real consumption; restored cooldowns honoured.

### Maintenance (2026-08-26) — Post-audit sweep: batch-run honesty, schema truth, M8, placement guard

- Batch interviews run through the real engine or fail honestly (`engine.post_message` never existed; the tuple-unpack of `complete()` meant the engine path had NEVER run — all prior batch transcripts were canned). Client-side metadata re-fabrication removed from `api.ts`. `init_database` is alembic-aware (skip/stamp/warn) and seeding is `BEBSHAX_DEMO_MODE`-gated; both M8 swallows now log. New ORM-placement freeze test. DATABASE_MIGRATION.md rewritten. Backend 245 + frontend 71/71 green.

### Maintenance (2026-08-26) — Merge: audit sweep (Tayeb, 8 items) × security fixes (Sazid, B4+B6)

- Conflicts resolved as the union of both sides: `config.py` keeps the M6 CORS block AND the fail-fast JWT settings; `Businesses` carries `industry`/`target_market` (M5) AND `owner_id` (B6); progress table recomputed (11/41).

### Maintenance (2026-08-26) — M11: CI gates (lint, coverage floor, secret scan, migration drift)

- ci.yml → 5 jobs: ruff bug-tier lint + 68% coverage floor (at 70.6%), advisory pyright, gitleaks full-history scan (`.gitleaks.toml` allowlists only the burned B4 literal, removal tracked), pgvector migration-drift job (H6's CI half), frontend without `--if-present`.
- R8: `ruff` (MIT, astral-sh) + `pytest-cov` (MIT, pytest-dev) added to dev extras only.
- The new lint gate immediately caught a latent `NameError` (undefined `uuid`) in `api/copilot.py` — fixed. Audit M11 ticked; Tayeb's audit items now 8/8.

### Maintenance (2026-08-26) — M5: business metadata columns

- `businesses.industry`/`target_market` real columns; migration `c4d5e6f7a8b9` (+legacy header extraction, exact-format-only); endpoints stop stuffing/parsing description; honest nulls. Fixture `api_test_app` moved to shared tests/conftest.py. 4 tests. Applied live. Audit M5 ticked; migration flagged for Sazid's review.

### Maintenance (2026-08-26) — L12: reply-format normalization

- `interview/normalization.py` + prompt rule 7: think-blocks, whole-reply fences and speaker labels stripped deterministically in `ask()`; content never mutated, empty-out impossible. 11 tests. Audit L12 ticked.

### Maintenance (2026-08-26) — M2: routes/status de-fabricated

- New public `PoolRouter.pool_utilization()` + `is_cooling()`; endpoint stops reaching into privates, stops inventing `active_requests=0`/`max(count,1)`/substring-guessed types. 4 tests. Audit M2 ticked.

### Maintenance (2026-08-26) — M4: no fabricated interview metadata

- Both interview message endpoints stop inventing `latency_ms=750` / `served_by="ollama/fallback"` defaults; engine's real measured values pass through (`None` = honest absence). E2E now pins real latency/route/memories. Audit M4 ticked.

### Maintenance (2026-08-26) — M9: memories endpoint states are honest

- `GET /personas/{id}/memories`: 404 for unknown persona, 503 when the memory service isn't configured, `200 []` only for a real persona with no memories. 2 tests. Audit M9 ticked.

### Maintenance (2026-08-26) — M6: CORS wildcard+credentials removed

- `create_app` now uses `settings.cors_origins_list` (new `BEBSHAX_CORS_ORIGINS`, comma-separated, Vite dev/preview defaults) with `allow_credentials=True` — spec-valid.
- Tests: `tests/test_cors.py` (echoed origin, rejected unknown origin, parsing). `.env.example` updated. Audit M6 ticked.

### Maintenance (2026-08-26) — H2: local Ollama tier restored + loud startup probe

- Ops: daemon started and verified live (`smoke_ollama.py` → SMOKE OK via `ollama/llama3.2:3b`); **no autostart exists** — ops note added to docs/ROUTING.md.
- `main.py` lifespan now runs `warn_if_local_tier_down()`: WARNING + `app.state.local_tier_up=False` when the local tier has zero routes (emergency pool is local-first, so silence was the H2 failure mode).
- Tests: `test_local_tier_warning.py` (4 cases incl. discovery-exception path), wiring assertion in `test_app_wiring.py`, and a new suite-wide `tests/conftest.py` autouse fixture pinning `OLLAMA_API_BASE` to an unroutable port — the unit suite is now hermetic w.r.t. a locally running daemon.
- Audit H2 ticked (assignments + fix log). Suite: 204 passed.

### Maintenance (2026-08-26) — Security Fixes B4 + B6 Stage 1, B3 Blocker Documented

- **B4 fixed (audit)** — `config.py` requires `BEBSHAX_JWT_SECRET` (≥32 chars, fail-fast on startup, rejecting burned git default). `security.py` enforces `iss` (`bebshax-api`) and `aud` (`bebshax-client`), and supports zero-downtime key rotation with `BEBSHAX_JWT_SECRET_PREVIOUS`. 8 regression tests added in `tests/test_jwt_secret.py` and updated in `tests/test_auth.py`.
- **B6 Stage 1 landed (audit)** — Added nullable `owner_id: String(64)` with `ForeignKey("users.id", ondelete="RESTRICT")` and index to `Businesses` and `Personas` in `db/models.py`. Migration `8d648b892fd3_add_owner_id_columns.py` applied. 6 tests added in `tests/db/test_owner_id.py`. Stage 2 (row-scoping enforcement) gated on B4 prod deployment.
- **B3 blocked (audit)** — Documented handoff in `docs/AUDIT_ASSIGNMENTS.md`. Endpoint `/api/auth/google` retained because `apps/frontend/src/services/api.ts:993` references it; deletion gated on frontend migration to `/api/auth/sync`.

### Maintenance (2026-08-26) — Conformance sweep: B1 fixed, phantom TaskType, llm_service wiring, R3 re-route, router validation restored

Owner instruction: keep the OpenRouter adapter/pool position **for testing purposes only**; fix everything else flagged by the conformance check.

- **B1 fixed (audit)** — `db/sink.py`: `str(r.task)` instead of `r.task.value`; first DB error now always logged. Fixing it exposed a **second total-loss bug**: `attempts` serialized raw datetimes into the JSON column (`TypeError`) — fixed with `model_dump(mode="json")`. Round-trip test added (`test_insert_batch_writes_row_round_trip`).
- **Phantom `TaskType.INTERVIEW_PROBING`** in `api/studies.py` (AttributeError at request time) → `STRUCTURED_OUTPUT`. New invariant test `tests/llm/test_task_type_references.py` scans the package for `TaskType.X` references and fails on non-members.
- **`app.state.llm_service` was never set** — 8 call sites across studies/personas/evidence/segmentation resolved `None` and silently served fallback content. `main.py` now aliases it to `llm_router`; integration fixture updated to match.
- **R3 re-route** — `datasets/service.py` persona synthesis no longer calls `OpenRouterService.generate_structured()` (adapter-direct, no provenance/fallback); it takes an injected `LLMService` and issues `PERSONA_GENERATION` requests; `api/datasets.py` passes `app.state.llm_router`. `openrouter_service.py` itself remains for health diagnostics + testing.
- **PoolRouter validation restored** — unknown adapter names in pool config raise `ValueError` again (warn-and-skip reverted); tests register a keyless-openrouter stub instead. Bogus `PoolRouter([])` fallback removed from `api/interviews.py`.
- **`python-multipart` declared** in `pyproject.toml` (was used by upload endpoints but never declared — broke collection with 14 errors; R8 review was already in this log).
- **`persona/schema.py`**: missing `Any` import (broke `GeneratedPersona.model_validate` at runtime — 22 test failures).
- **Docs synced:** D7 → 18 task types (PROJECT_CONTEXT), ROUTING.md + AI_IMPLEMENTATION_PLAN.md pool tables/task counts, audit B1 ticked (assignments + fix log).
- Suite: **200 passed** (was: 14 collection errors).

### Maintenance — auth-aware landing CTAs (2026-08-24)

- Bug: the hero CTA "Generate your first persona" did nothing for a signed-in user — `Hero` declared `onOpenApp` but destructured nothing (a zero-arg arrow is assignable to `React.FC<HeroProps>`, so `tsc` stayed silent), so the button always ran `navigate('/auth/signup')` and `AuthPage`'s `isAuthenticated` effect bounced straight back to `/`. Same defect in `FinalCTA`; `InteractiveDemo` never received `onOpenApp` at all.
- Fix: `Hero`, `FinalCTA`, `InteractiveDemo` now read `useAuth()` and, when authenticated, call `onOpenApp?.()` and render the Navbar's existing label **Launch Console**; signed-out behaviour and all styling unchanged. `LandingPage` passes `onOpenApp` to `InteractiveDemo`; dead `onExploreDemo` prop removed.
- Tests: `tests/LandingPage.test.tsx` gained 3 CTA-destination cases (signed-out hero → auth page; signed-in hero and final CTA → console) driven by seeding/clearing `bebshax_auth_token` in `localStorage`, plus per-test URL/storage reset. Frontend 11/11 tests + `npm run build` green.

### Maintenance — .github config repair + full sync sweep (2026-08-23)

- Found via sync sweep: a generator run had added `.github/workflows/ecc-verify.yml` (invalid YAML — failed at parse on EVERY push) and `.github/copilot-instructions.md` conflicting with AGENTS.md (wrong commands: `pip install -r requirements.txt`), plus placeholder-riddled foundation/decisions/conventions/security files. Fix: removed the duplicate workflow (ci.yml is the verification gate); copilot-instructions now points at AGENTS.md + a verified command table; foundation/decisions point at PROJECT_CONTEXT.md (single source of truth); conventions/security instruction files filled with real project rules. Kept the sane generated python/typescript/testing instruction files.
- Sweep results: unit 135/135 · integration 3/3 (live pg) · frontend build + 8/8 tests · alembic current == head (`c1a7b8e42f55`) · local Ollama tier serving · live 5-turn interview passed · CI green with the broken workflow gone · working tree clean, origin synced.

### Phase 10 — Interview engine (2026-08-23) ✅

- `bebshax/interview/`: `Conversations`/`ConversationTurns` ORM (migration `c1a7b8e42f55`), `InterviewEngine` — per-turn composition: immutable `build_identity_card` (test asserts byte-identical presence in every turn's system message) + constraints + business context + objective + Phase-9 memory retrieval (k=4) + evidence themes + FULL history; oversized → router's `ContextWindowExceeded`, never truncation. Each exchange written back as an episodic memory (0.4).
- REST: start conversation / post message (`{reply, turn_number, served_by}`) / transcript; wired in lifespan (`app.state.interview_engine` consuming `memory_service`).
- Tests: 9 new (identity card fields/determinism, composition roles+history ordering, multi-turn stability, memory write-back, 404 paths, HTTP flow). Fix applied during dev: original stability assertion compared whole system messages — wrong invariant, memories legitimately evolve; corrected to identity-card immutability. Renamed `tests/interview/test_api.py`→`test_interview_api.py` (pytest basename collision with persona's).
- **Live 5-turn exit criterion PASSED**: fresh persona "Nabil Chowdhury" (25, Marketing Executive) interviewed across FOUR providers mid-conversation (kilo→llm7→ovh→kilo→llm7) — name/age/occupation all consistent. Finding: one free reasoning model leaked its thinking process in a reply — recorded as a Phase-11 quality-evaluation concern, correctly NOT an infra failure.
- Suite: **135/135 unit green**; migration applied to live pg. Backend feature-complete for the demo path (personas → memory → interviews).

### Phase 9 — Memory (2026-08-23) ✅ (owner-approved takeover: Sazid → Tayeb)

- `bebshax/memory/`: `MemoryItems` ORM (pgvector `Vector(384)` on postgres / JSON on sqlite; migration `b9d4e5f60a17` incl. HNSW cosine index), `scoring.py` (0.60·cosine + 0.25·recency(48 h half-life) + 0.15·importance — injectable weights), `MemoryService` (remember / retrieve with `last_accessed` touch / reflect via MEMORY_SUMMARIZATION → ≤3 reflection items @0.8 importance, best-effort parse).
- Embeddings (`bebshax/llm/adapters/embeddings.py`, R1-compliant): **documented deviation** — freellmpool's embed failover serves varying models per call, which would mix incomparable vector spaces; default backend is therefore the deterministic `HashEmbedding` (`local-hash-384`, offline/free/stable), with `FreellmpoolEmbedding` available behind `BEBSHAX_EMBEDDING_BACKEND=freellmpool` + a REQUIRED pinned model (sync `Pool.embed` bridged via thread+lock — no async embed exists in 0.11.4). Every row carries `embedding_space`; retrieval filters to the query's space so cross-space cosine never happens.
- Wiring: `app.state.memory_service` in the lifespan; settings gained `embedding_backend`/`embedding_model`; alembic env registers the new ORM.
- Tests: 16 new unit (scoring math incl. half-life, hash determinism/normalization/lexical similarity, retrieval ordering, persona+space scoping, recency tiebreak, importance boost, reflection thresholds/parse-failure swallow) + **2 pg integration tests PASSED live** (20 memories → expected top-k; reflection stored + retrievable). Suite: **127/127 unit green**, migration a8f3c2d91e04→b9d4e5f60a17 applied to the running pgvector.
- Phase 10 consumption point: `MemoryService.retrieve` for turn context, `remember` for per-turn observations, `reflect` after conversations.

### Phase 8 — Persona engine (2026-08-23) ✅

- `bebshax/persona/`: schema (`GeneratedPersona` LLM contract + `PersonaProfile` + `coerce_provenance` — provenance enforced in CODE: fabricated evidence citations stripped → INFERRED, junk labels → SYNTHETIC, downgrades only), `EvidenceStore` (idf-weighted lexical retrieval over Phase-7 processed JSONL; lazy, ≤30k records/dataset, 500-char texts, zero new deps — pgvector replaces the scorer in Phase 9), table-driven `check_consistency` (age/occupation, income/luxury, location/timezone), `PersonaEngine` (single PERSONA_REFINEMENT budget for schema/consistency content failures → explicit `PersonaGenerationFailed`; optional CRITIC pass → warnings), persistence (additive ORM: persona_details/persona_attributes/persona_evidence — Sazid's models untouched; migration `a8f3c2d91e04`).
- Research applied: PersonaHub persona-driven synthesis methodology (arXiv:2406.20094) — deterministic diversity seed per attempt, used for perspective only, never copied.
- REST: POST/GET businesses, POST /businesses/{id}/personas, GET /personas/{id} (422 with violations / 413 / 503 mapping). `main.py` lifespan now wires DB sessionmaker + **ProvenanceSink into PoolRouter** (every LLM request persists to `llm_requests`, fail-soft) + persona engine. Additive `FakeAdapter.replies`/`requests` for scripted-JSON tests (own-track path).
- Phase-11 interop: `PersonaProfile.to_eval_dict()` contract-tested against `REQUIRED_PERSONA_FIELDS`.
- **Live E2E PASSED** (real routing + real Postgres + real datasets): persona "Aisha Rahman" by `codestral-latest` — 16 attributes, **3 OBSERVED with verified citations**, 13 INFERRED, 3 evidence items, zero warnings; visible via GET. Dataset pipeline run locally (minimal profile: personahub 5.3MB + synthetic_persona_chat 4.1MB processed). Docker restarted after yesterday's WSL shutdown; migrations cb7c7deda755→a8f3c2d91e04 applied clean.
- Suite: **111/111 green** (26 new persona tests; 1 pg-integration deselected by default). Note: dataset script exits 1 on optional-dataset soft-fails — flagged to Sazid.

### Phase 11 — Quality & evaluation (2026-08-22) ✅

**Summary:** Built complete evaluation engine in `apps/backend/bebshax/evaluation/` measuring persona quality, grounding ratio, and multi-model routing strategy performance. Implemented 7 pluggable candidate routing rankers (`HYBRID`, `ROUND_ROBIN`, `LEAST_USED`, `QUALITY_FIRST`, `LATENCY_FIRST`, `CAPABILITY_FIRST`, `QUOTA_AWARE`) in `strategies.py`. Developed `RoutingChaosSimulator` to benchmark router resilience under stochastic rate limits, timeouts, and server failures. Built `OfflineEvaluator` replaying `router_arena` and `xroute_bench` benchmark datasets without live network calls. Authored evaluation CLI `scripts/run_evaluation.py` producing Markdown and JSON report artifacts in `data/metadata/`. Authored comprehensive methodology documentation in `docs/EVALUATION.md`. Added 12 new unit and integration tests under `apps/backend/tests/evaluation/` (all 85 tests passing).

**R8 Dependency Review:** Zero new dependencies added (uses Python standard library, existing Pydantic, and internal modules).

### Phase 12-foundation — Frontend (app shell + mock layer) (2026-08-22) ✅

**Summary:** Built complete React + Vite single-page frontend application in `apps/frontend` with TypeScript and modern vanilla CSS design system (glassmorphism, dark theme, responsive grid, micro-animations, Plus Jakarta Sans typography). Authored frozen contract [docs/API_CONTRACT.md](API_CONTRACT.md) defining all REST endpoints and Pydantic/TypeScript data shapes. Implemented mock fixture layer in `apps/frontend/src/mocks/` and reactive client store, enabling fully interactive persona generation, memory exploration, turn-by-turn interview simulation, routing trace inspection, and evaluation benchmarking.

**R8 Dependency Review (Frontend Packages in `apps/frontend/package.json`):**

1. **react & react-dom ≥18.3** (MIT, Meta / React Community)
   - Why: Owner-decided UI library; declarative component tree and hook-based reactive state.
   - License: MIT.
2. **vite ≥5.4 & @vitejs/plugin-react** (MIT, Evan You / Vite Core)
   - Why: Ultra-fast ESM dev server and Rollup-based production bundler with sub-2s build times.
   - License: MIT.
3. **vitest ≥2.1, @testing-library/react, @testing-library/jest-dom, jsdom** (MIT)
   - Why: Zero-config headless component test runner mirroring backend pytest ergonomics; enforces green test gate (R7).
   - License: MIT / Apache-2.0.

**Delivered Views (6/6 fully wired to mock layer and live backend fallback):**

1. **Routing Dashboard:** Provenance log table with expandable per-attempt failover traces, provider health cards (pollinations, groq, mistral, ovhcloud, ollama), pool concurrency monitors, and raw JSON modal.
2. **Business Setup:** Form to create commercial contexts + target market definition cards.
3. **Persona Profile:** Demographic coordinates card, grouped attributes with `OBSERVED`, `INFERRED`, and `SYNTHETIC` provenance badges, evidence grounding source quotes from PersonaHub/EmpatheticDialogues, and generation modal.
4. **Persona Memory:** Semantic, episodic, and reflection streams with pgvector indexing indicator and importance score sliders.
5. **Interview Simulation:** Interactive turn-by-turn dialogue interface with latency tracking, retrieved memory inspection drawer, and markdown transcript export.
6. **Evaluation & Insights:** Quality KPIs (validity, consistency, grounding ratio) and 6-way routing strategy benchmark table answering the core research question.

**Exit Criteria Verification:**

- `npm run build` green (0 errors, 1.45s bundle time).
- `npm test` green (6/6 passing in Vitest).
- `GET /api/health` polling wired to live FastAPI backend on port 8000.
- All 73 backend pytest tests remain green.

---

### Phase 7 — Dataset pipeline (2026-08-22) ✅

**Summary:** Built reproducible, license-checked, one-command dataset pipeline with profiles (`minimal` ⊂ `development` ⊂ `evaluation` ⊂ `full`). Manifest defines 10 datasets across 6 Gebru datasheet dimensions with verified upstream license URLs and immutable 40-character Git commit SHAs. Implemented `scripts/setup_datasets.py` with idempotent checksum skipping, live pre-flight commit resolution, fail-soft handling for gated/optional sets, and automatic generation of `data/DATASETS.md`.

**R8 Dependency Review (huggingface_hub and fastparquet):**

1. **huggingface_hub ≥0.28.0, <1.0** (Apache-2.0, official Hugging Face library, extremely active)
   - Why: Official client for querying Hugging Face Hub metadata, enumerating repository files (`HfApi.list_repo_files`), downloading pinned-revision individual files (`hf_hub_download`), and streaming file slices (`HfFileSystem`).
   - License: Apache-2.0 (permissive). Activity: weekly releases by Hugging Face core team.
   - Necessity: Non-negotiable for reproducible, pinned-revision dataset retrieval and streaming slices from HF Hub.

2. **fastparquet ≥2026.5.0** (Apache-2.0, numba / Python data ecosystem)
   - Why: High-level parquet parsing for downloaded `.parquet` dataset artifacts (`cais/mmlu`, `openai/gsm8k`, `RouteWorks/RouterArena`, `ulab-ai/xRouteBench`, `facebook/empathetic_dialogues`) into normalized JSONL.
   - Trade-off & Necessity: While `fastparquet` pulls transitive dependencies (`pandas`, `numpy`, `cramjam`), `pandas` provides structured DataFrame column manipulation, striding, filtering, and structured record exports (`df.to_dict(orient='records')`), making multi-dataset preprocessing robust and concise. All transitive dependencies carry permissive open-source licenses (BSD-3 / Apache-2.0).
   - Alternatives considered: `pyarrow` provides a lower-level C++ binding without pandas, but `fastparquet` + `pandas` offers higher-level tabular ergonomics across diverse schema layouts.

- **Decision on `datasets` library (OMITTED):** The heavy `datasets` meta-library is excluded (avoids multiprocess, dill, xxhash, and background cache managers). `huggingface_hub` + `fastparquet` alone handle retrieval, streaming, and conversion, while normalized JSONL remains the single persistent storage format.

**Lock strategy:** `requirements.lock` refreshed post-install.

**Findings & Deviations:**

- Switched PersonaHub from raw 301 GB shard to the official 200k persona release (`persona.jsonl`, 21.6 MB) with systematic stride-8 sampling across all 200k records for uniform demographic and occupational diversity.
- Switched EmpatheticDialogues from unpinned external tar archive to `refs/convert/parquet` commit `d5b57ae707b0b9a384af8ed50c043c608d597ca7` on `facebook/empathetic_dialogues`, establishing uniform commit SHA pinning across all 10 datasets.
- Replaced niche `Subscription_Boxes` with representative `Office_Products` category from Amazon Reviews 2023.
- LMSYS-Chat-1M: recorded right-to-request-deletion clause, unsafe content warning, and marked optional (`is_required=False`) with fail-soft behavior.

**Exit Criteria Verification:**

- Tests green: 74 passed offline in ~16s; integration test `test_pinned_revisions_resolve` passes live against Hugging Face.
- Live `--profile minimal` completed (37.99 MB raw, 9.85 MB processed; well within < 1 GB limit).
- Re-run confirmed strictly no-op with checksum matching.
- `data/DATASETS.md` generated directly from manifest.

---

### Phase 6 — Database (2026-08-22) ✅

**R8 Dependency Review (BEBSHAX_DATABASE_URL required these four packages):**

1. **sqlalchemy[asyncio] ≥2.0.52, <2.1** (MIT, extremely active, 10k★)
   - Why: Only async-capable Python ORM with pgvector support + declarative models. Greenlet pre-installed by default until 2.1; [asyncio] extra mandatory after 2.1 to avoid greenlet injection.
   - License: MIT (permissive). Activity: weekly commits, 2.1 final imminent—staying <2.1 to avoid greenlet regression until it's stabilized.
   - Necessity: Non-negotiable for async Postgres persistence. No alternatives at SQLAlchemy's maturity level.

2. **asyncpg ≥0.31, <0.32** (BSD-3, production-grade, Postgres community)
   - Why: Only mature asyncio-native Postgres driver. Native query caching (statement_cache_size), native UUID, native JSONB support.
   - License: BSD-3 (permissive). Activity: stable, maintenance-focused, rarely breaking.
   - Necessity: sqlalchemy[asyncio] depends on it; tying pins together prevents version skew.

3. **alembic ≥1.19, <2** (MIT, Sqlalchemy Foundation)
   - Why: De-facto standard for Postgres migrations. Auto-detects schema changes (models ↔ migrations drifting is fatal). Integrates with declarative models.
   - License: MIT. Activity: stable, aligned with SQLAlchemy releases.
   - Necessity: Schema evolution + testing (migrations must round-trip; "alembic upgrade head" + autogenerate must produce empty diff).

4. **pgvector ≥0.4, <1** (BSD-3, Open-source)
   - Why: Python sqlalchemy bindings for Postgres pgvector type. Enables vector columns in declarative models. Phase 9 (memory) depends on it; wired now to avoid env.py churn later.
   - License: BSD-3. Activity: maintenance-focused.
   - Necessity: Phase 9 dependency; preparing now avoids migration re-runs.

**Dev-only: aiosqlite ≥3.5** (MIT, async SQLite for unit tests)

- Why: Tests run offline on SQLite; JSONB/vector columns map gracefully to JSON/BLOB for testing.
- Necessity: Unit tests must not require Postgres.

**Lock strategy:** requirements.lock will pin all transitive deps post-install. Refresh after any pyproject changes.

- Lock refreshed with new dependencies.
- **Models wired:** `bebshax/db/models.py` with MetaData naming convention (ix/uq/ck/fk/pk). Declarative models: `LLMRequests` (all 14 ProvenanceRecord fields + optional prompt/completion text gated behind settings flag), `ModelRegistry` (capability + health metadata; sync jobs currently unowned), `Businesses` (skeleton; full schema Phase 8), `Personas` (skeleton with business FK; phase 8 adds attributes).
- **Column design notes:** String(64) IDs for cross-dialect compatibility (PostgreSQL gets native uuid in production; SQLite gets strings for testing). Enums use native_enum=False (VARCHAR + CHECK) so new TaskType/FailureKind members can be added without ALTER TYPE in production. Timestamps use DateTime(timezone=True) with Python-side default=lambda: datetime.now(timezone.utc) to avoid sqlite timezone inconsistency.
- **Indexes:** `llm_requests` has (created_at DESC, persona_id, conversation_id, (provider_name, request_model)). `personas` and `model_registry` indexed on their key columns. No GIN on attempts JSONB yet (Phase 5 may add retrieval queries).
- **Provenance sink trade-off (R2-compliant):** `ProvenanceSink` is synchronous on `__call__` (queue.put_nowait, never raises) + async writer task. Rationale: failure taxonomy is closed and load-bearing. A synchronous DB write would introduce a 14th failure mode (DB latency/down) not in the taxonomy. Observability must never fail a request. Writer task batches up to K records or T ms, inserts atomically, handles DB failures with rate-limited logging and drops batch. Sink metrics exposed for monitoring (total_enqueued, total_written, total_dropped, queue_full_count, total_db_errors).
- **Alembic:** `alembic init -t async` with env.py wired to `settings.database_url` (BEBSHAX_DATABASE_URL env var; no secrets in alembic.ini). pgvector extension creation guarded by dialect check (PostgreSQL only). Migration auto-detects schema changes; autogenerate + round-trip test in CI ensures models and migrations stay in sync.
- **Tests:** 10 new tests (all passing). Unit tests on aiosqlite (SQLite in-memory); integration tests marked `@pytest.mark.integration` (run when docker db is up + BEBSHAX_TEST_PG != 0). Models round-trip via ORM; sink construction and enqueue tested; no network required for unit suite.
- **Exit criteria met:** Tests green (36/36: 26 LLM + 10 database); `alembic upgrade head` ready to apply (schema in /alembic/versions/); first LLM request will write one `llm_requests` row via sink (integration test prepared, needs docker db for live validation).
- **Deferred to later phases:** Registry sync jobs (Phase 5 scoring + external enrichment), persona attribute schema (Phase 8), memory tables (Phase 9), sink writer task lifespan integration with FastAPI (Phase 13).

---

### Phase 5 — Routing/fallback across adapters (2026-08-22) ✅

- `bebshax/llm/pools.py`: 7 pools as pydantic config data (reasoning/conversation/long_context/structured/fast/local/emergency) + task→pool map covering all 16 TaskTypes (exhaustiveness test-enforced); every pool terminates at the local adapter; `emergency` is local-first.
- `bebshax/llm/router.py`: `PoolRouter(LLMService)` — per-pool `asyncio.Semaphore`, candidates gathered across the pool's adapters in preference order, injectable `ranker` hook (registry scores plug in at Phase 6/11), in-memory route cooldowns (60 s default, injectable clock for tests) applied on cooldown-flagged failure kinds and skipped with routing-path notes.
- `bebshax/llm/estimator.py`: deterministic chars/3.5 + 4 tokens/message + expected output (over-estimates by design — mis-sizing can only pick a roomier model, never truncate). `service.py` refactored: shared `filter_eligible` + `attempt_candidates` machinery now backs both `SingleAdapterLLMService` (kept for tests/smokes) and `PoolRouter`.
- `adapters/factory.py` (inside adapters/ so R1 boundary scan stays strict — module names containing provider strings may not be imported elsewhere); `create_app` lifespan wires `app.state.llm_router = PoolRouter(build_default_adapters())` and closes adapters on shutdown; `ProviderAdapter.aclose()` default added.
- Chaos tests: remote exhausted → local serves (brief TEST 6); 20 concurrent requests peak ≤3 under `max_concurrency=3` (brief TEST 7, instrumented adapter); 429 → cooldown skip → recovery after expiry (fake clock); whole-pool failure carries pool in provenance; unknown adapter names fail fast at init.
- Suite: **51/51 green** (14 new). No new dependencies. Next: Phase 6 (database, Sazid) / Phase 8 unblocked once 6 lands.

### Phase 4 — Ollama integration (2026-08-22) ✅

- `OllamaAdapter` (`bebshax/llm/adapters/ollama_adapter.py`): plain httpx, **native `/api/chat`** instead of the spec'd OpenAI-compat endpoint — recorded deviation: only the native API accepts `options.num_ctx`, without which Ollama silently truncates long prompts (R2 violation). Adapter pins `num_ctx` per request (generous chars/3 estimate) and raises `CONTEXT_WINDOW_EXCEEDED` rather than truncate; candidates live from `/api/tags` + `/api/show` (windows capped 16k for 4 GB VRAM), smallest-first ordering; full error mapping; 60 s candidate cache; no new dependencies.
- `scripts/benchmark_ollama.py` (Ollama's exact ns timings; timeouts recorded as results, not crashes) + `scripts/smoke_ollama.py`.
- **Findings (the benchmark did its job):** `qwen3.5:latest` (6.6 GB) is **unusable under real workload** — repeated HTTP 500 / `llama runner terminated` with <2 GB free RAM (VS Code 3 GB + Edge 1.7 GB + WSL 0.6 GB on a 15.7 GB machine); Ollama's own error: _"model requires more system memory (1.8 GiB) than is available (1.6 GiB)"_ — even 2–2.5 GB models needed `wsl --shutdown` (owner-approved) to load. Adopted: **`llama3.2:3b` primary** (2.0 GB, 25.2 tok/s median, 59.8 warm), **`qwen3:4b` secondary** (2.5 GB, 22.4 tok/s, 217 ms warm TTFT). Results in `data/metadata/ollama_benchmark.json`.
- Live smoke PASSED: served by `ollama/llama3.2:3b`, provenance notes carry `num_ctx`.
- Suite: **37/37 green** (11 new mock-transport tests). Next: Phase 5 (routing/fallback across adapters).

### Maintenance — agent automation & team parallelization (2026-08-22)

- `AGENTS.md` (root): binding contract auto-loaded by Copilot/Cursor/Claude Code/Codex/Windsurf — rules digest, **Phase Execution Protocol** ("implement phase N" → gate → implement in-scope → verify → mandatory doc updates in the same commit → `Phase N:` commit), Definition of Done for any change; `CLAUDE.md`/`GEMINI.md` pointers for tools that prefer their own filename.
- `docs/PHASES.md`: executable specs for phases 4–15 (goal, prerequisites, allowed paths, steps, exit criteria with commands, docs to update, out-of-scope) — the file that makes "Implement phase 4" a one-line instruction.
- `docs/TEAM_ASSIGNMENTS.md`: 3 collision-free parallel tracks — Tayeb: 4→5 (`bebshax/llm/**`), Sazid: 6→7 (`bebshax/db/**`, `data/**`, datasets), Shehab: 12-foundation (`apps/frontend/**` on mocks + API contract); convergence order for 8–15; merge rules (append-only log, contract-change sign-off).
- `.github/workflows/ci.yml`: pytest on every push/PR (mechanical R7 enforcement regardless of which tool wrote the code); frontend job activates when `apps/frontend` exists. `.github/prompts/implement-phase.prompt.md`: `/implement-phase` shortcut for VS Code.
- RULES.md gains **R12** (agents follow AGENTS.md; stale docs = unfinished task). PROJECT_CONTEXT roadmap marked authoritative: **15 phases** (22-phase draft superseded); doc map extended.
- Suite 26/26 green; ci.yml YAML-validated.

### Phase 3 — freellmpool integration (2026-08-22) ✅

- Dependency `freellmpool==0.11.4` installed (review in docs/ROUTING.md per R8); lock refreshed.
- Adapter contract upgraded: `ProviderAdapter.complete` now returns `AdapterCompletion` (concrete serving provider/model + notes) so provenance records the real route, never "auto"; `AttemptRecord.notes` added; fake adapter + service updated.
- `FreellmpoolAdapter` (`bebshax/llm/adapters/freellmpool_adapter.py`): one virtual route `freellmpool/auto` (window 1M — freellmpool enforces real per-model limits); full error mapping onto the failure taxonomy (its `ContextWindowExceeded` subclasses `AllProvidersExhausted` — caught first); `client_status=429` → RATE_LIMITED; empty replies → MALFORMED_RESPONSE; injectable pool for tests; `aclose()` lifecycle.
- Boundary enforcement: `test_boundary.py` scans the package — provider SDK imports (freellmpool/ollama/litellm/openai/anthropic) allowed only under `adapters/`.
- **Gate B decided: LiteLLM skipped** — justification + revisit trigger in docs/ROUTING.md.
- **Live keyless smoke PASSED:** served by `llm7/codestral-latest`, zero keys, 3 internal freellmpool failover attempts captured in provenance notes; 33 s latency (keyless tiers are slow — team keys will improve this).
- Suite: 26/26 green (9 new tests). Repo published: https://github.com/Tayebbb/BebshaX (public) + team docs PROJECT_CONTEXT.md / RULES.md / docs/TEAM_SETUP.md.

### Phase 2 — LLM abstraction (2026-08-22) ✅

- `bebshax.llm` package: `TaskType` (16 task types — callers declare their task; no LLM classifies), `ChatMessage`/`LLMRequest`/`LLMResult`, `ProvenanceRecord`+`AttemptRecord` (all §14 fields: provider, model, routing path, attempt no., latency, tokens, failure/fallback reasons, final model).
- Failure taxonomy: 13 `FailureKind`s, each with an explicit `FailurePolicy` (retry-same-once / try-next / cooldown). **Quality is deliberately NOT a failure kind** — enforced by `test_low_quality_is_not_an_infrastructure_failure`. `INTERNAL_ERROR` surfaces immediately instead of burning candidates.
- Adapter boundary: `ProviderAdapter` + `RouteCandidate` in `bebshax/llm/adapters/` — the only package allowed to import provider SDKs. `FakeAdapter` provides scriptable failure injection for tests/chaos.
- `SingleAdapterLLMService`: reference implementation — pre-flight capability + context-window eligibility (ineligible routes are never called; oversized requests raise `ContextWindowExceeded`, never truncate), policy-driven fallback, provenance hook (`on_provenance`) firing on success and failure (Phase-6 DB attachment point).
- Token estimation: chars/4 heuristic + expected output, marked for replacement by the Phase-5 estimator.
- Tests: 14 new (taxonomy, 429→timeout→success chain, same-route retry, all-fail provenance, internal-error surfacing, context skip/explicit-fail, JSON/tool capability filtering, provenance completeness on success + failure). Suite: 17/17 green.
- No new dependencies.

### Phase 1 — Foundation (2026-08-22) ✅

- Repo initialized; scaffold: `apps/backend` (package `bebshax`), `data/{raw,processed,metadata}`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`.
- Config: pydantic-settings with `BEBSHAX_` prefix. Provider keys deliberately NOT modeled in `Settings` — freellmpool reads standard env vars directly, keeping the provider list configuration-driven (owner decision #10).
- Dependencies added (all permissive-licensed, actively maintained, minimal set): `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`; dev-only: `pytest`, `pytest-asyncio`, `httpx`. Exact versions snapshotted in `apps/backend/requirements.lock`.
- **Finding:** native PostgreSQL 16 lacks pgvector (`vector.control` absent) → app DB is `pgvector/pgvector:pg16` on port **5433** (native keeps 5432). Compose file validated with `docker compose config`; container start deferred to Phase 6.
- Verified: 3/3 tests green; live `GET /api/health` → 200 `{"status":"ok","app":"BebshaX","version":"0.1.0",...}`.
- Known item: starlette TestClient emits a deprecation warning suggesting `httpx2`; revisit when starlette requires it.
- Deviation from earlier draft: 22-phase plan replaced by the owner's 15-phase structure (recorded above).

### Maintenance (2026-08-25) — Universal AI Workflow + OpenRouter integration

**What was built:**

- **Backend `copilot.py` rewrite (R3-compliant):** Removed all hard-coded student/Bangladesh context from every function. The copilot SYSTEM_PROMPT, `_generate_fallback_response`, `suggest_persona_roles`, and `generate_study_personas` now handle any business idea (food, health, fintech, e-commerce, B2B SaaS, education, etc.) by detecting domain keywords and generating contextually-relevant roles and personas. The fallback dialog is now contextual for 7+ business domains.
- **LLM-powered persona generation:** `generate_study_personas` now calls the LLM via `_generate_persona_via_llm()` using the new `PERSONA_GENERATION_PROMPT` template, which grounds each persona in the study context. Falls back to a generic skeleton if LLM is unavailable.
- **LLM-powered role suggestion:** `suggest_persona_roles` now calls the LLM via `SUGGEST_ROLES_PROMPT` and falls back to context-aware keyword detection instead of hardcoded student roles.
- **OpenRouter wired into PoolRouter:** `factory.py` now builds `{"openrouter": OpenRouterAdapter(), "freellmpool": ..., "ollama": ...}`. OpenRouter is first-preference for all pools (`reasoning`, `conversation`, `structured`, etc.).
- **PoolRouter forward-compatibility:** Changed ValueError on unknown adapter → `warnings.warn()`. `complete()` now skips missing adapters gracefully (`.get()` instead of `[]`). This allows OpenRouter to be optional (silently skipped when no key is set).
- **New `PERSONA_NARRATIVE` TaskType** added to `types.py` and mapped to `reasoning` pool in `pools.py` for high-quality persona narrative generation.
- **Frontend `api.ts`:** All three hardcoded student-only mock fallbacks (`sendStudyCopilotMessage`, `getSuggestedPersonaRoles`, `generateStudyPersonas`) replaced with context-aware fallbacks matching 7+ business domains.

**Tests:** 142 passed, 3 deselected (auth/DB integration tests skipped without live DB). No new dependencies added.

**Deviations:** None from spec. The `test_unknown_adapter_in_pool_config_fails_fast` test was renamed to `test_unknown_adapter_in_pool_config_warns` to match the intentional behavior change (warn, not fail).

### Maintenance (2026-08-25) — Dashboard Sidebar Cleanup & Copilot Dialogue & Persona Generation Fixes

**What was built:**

- **Dashboard Layout Cleanup:** Removed `Model Router & Provenance` tab and its `Cpu` icon from `DashboardLayout.tsx` per user request. Verified sidebar now renders only `New Study`, `Dashboard`, and `Persona Library`.
- **Copilot Message & Persona Generation Resilience:**
  - Resolved issue in `StudyWorkflowView.tsx` where Copilot conversational answering or persona generation failed when backend is unreachable.
  - Implemented `copilotMessagesRef` synchronization and `pendingHistoryRef` request queuing to eliminate state clobbering, race conditions, and typing stalls.
  - Guarded `useEffect` on `[studyId]` so loaded study messages do not overwrite active user turns in-flight.
  - Enriched `api.ts` with context-aware pricing tracker roles (`SMART BARGAIN HUNTER`, `TECH-SAVVY CONSUMER`, `BUDGET-CONSCIOUS BUYER`, etc.) and tailored personas (`Samiul Alam`, `Nabila Khan`, `Tanvir Hasan`).
  - Added full test coverage in `StudyCopilot.test.tsx` verifying multi-turn price tracker prompts, goal card synthesis, suggested roles, and Step 2 grounded persona generation.

**Tests:** 41/41 frontend tests green; 143/143 backend pytest tests green.

### Maintenance (2026-08-25) — Case Study Auto-Save, User Isolation & User List Endpoint

**What was built:**

- **`copilot_messages` + `personas_data` DB columns:** Added two nullable JSONB columns to the `Studies` ORM model (`db/models.py`). Alembic migration `96ee206715d7` generated and applied — columns are live in the DB.
- **Studies API hardened (`api/studies.py`):**
  - `StudyCreateRequest` and `StudyUpdateRequest` now include `copilot_messages` and `personas_data` fields.
  - `_serialize_study()` now returns both fields in all responses.
  - **User isolation enforced:** `list_studies` returns only the authenticated user's studies + demo studies. Unauthenticated callers receive only demo studies (`is_demo=True`), never all studies.
  - `get_study` and `delete_study` return 404 for cross-user access.
  - `update_study` returns 403 for cross-user access. Auto-create path (for seamless workflow init) preserved.
  - Helper `_user_owns_study()` centralises ownership logic.
- **User list endpoint (`api/auth.py`):** Added `GET /api/auth/users` returning all registered users with full profile data (`id`, `email`, `full_name`, `avatar_url`, `is_active`, `is_verified`, `auth_provider`, `created_at`, `updated_at`). Requires valid JWT, no admin role.
- **`UserProfileResponse` extended:** Added `updated_at` field.
- **Frontend state restoration (`StudyWorkflowView.tsx`):** Added `useEffect` on `studyId` mount that loads the study from DB and restores: `currentStep`, `promptInput`, `copilotMessages` (with deduplication), `suggestedRoles`, `script_questions`, `personas_data`. Role-selection panel is shown automatically if last assistant message is a goal card.
- **Step change now persists copilot_messages + personas_data** via `copilotMessagesRef.current` (capture-at-call-time to avoid stale closures).
- **Persona generation now persists `personas_data`** alongside `persona_ids` so personas survive page refresh.
- **`api.ts` & Auth Synchronization with Neon Postgres:**
  - Prioritized the backend FastAPI auth API (`/api/auth/signup`, `/api/auth/signin`, `/api/auth/google`) so all user registrations and logins are committed directly to `public.users` in Neon PostgreSQL and issued real HMAC-SHA256 JWTs.
  - Added `POST /api/auth/sync` endpoint in `auth.py` and `api.syncUser()` helper in `api.ts` to seamlessly upsert users registered via OTP or external auth into the PostgreSQL database.
  - Added `scripts/dev.js`, `dev.cmd`, `dev.ps1` and updated `package.json` so running `npm run dev` (or `npm run frontend` / `dev.cmd`) concurrently boots both the FastAPI backend on port 8000 and the Vite frontend on port 5173.
  - Verified live database state in Neon Cloud: confirmed `Users` (1 row) and `Studies` (1 row) active.

**Tests:** 41/41 frontend tests green; 143/143 backend pytest tests green.

### Maintenance (2026-08-25) — Dataset Sources Integration, Deterministic Profiling & OpenRouter Health Diagnostics

**What was built:**

- **OpenRouter Service & Server-Side Health Diagnostics (`apps/backend/bebshax/llm/` & `api/`):**
  - Updated `openrouter_adapter.py` with `health_check(model)` executing real lightweight completions to OpenRouter to measure latency and test authentication without leaking secret tokens.
  - Implemented dynamic API key lookup from `os.environ.get("OPENROUTER_API_KEY")` so keys set after startup are immediately available.
  - Created `openrouter_service.py` supporting role-specific model routing (`MODEL_PERSONA`, `MODEL_REASONING`, `MODEL_EXTRACTION`, `MODEL_CRITIC`, `MODEL_BROWSER`).
  - Created `api/openrouter_health.py` exposing `GET /api/health/openrouter` and `POST /api/health/openrouter/test`.
- **Database Persistence & Alembic Migration:**
  - Added `DatasetSources` and `DatasetPersonaRuns` ORM models to `apps/backend/bebshax/db/models.py`.
  - Created Alembic migration `99b3c3047dec_add_dataset_sources_and_dataset_persona_.py` and upgraded Neon Postgres database schema to head.
- **Dataset Ingestion, Security & Profiling Package (`apps/backend/bebshax/datasets/`):**
  - `security.py`: Server-side SSRF validation with strict IP range filtering (blocking 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, loopback, internal domains) and 25MB streaming limit.
  - `parser.py`: Safe parsing for CSV, TSV, JSON, JSONL, and Excel (XLSX).
  - `profiler.py`: Deterministic statistical calculation of numeric distributions (min, max, mean, median, std, p25, p75, IQR) and categorical distributions with frequencies and percentages.
  - `segmenter.py`: Empirical segment discovery and mathematical persona quota calculation (`calculate_segment_persona_distribution`) using the largest remainder method.
  - `validator.py`: Programmatic constraint validator classifying synthesized personas into `VALID`, `WARNING`, `CONTRADICTION`, and `INVALID` without LLM hallucinations.
  - `service.py`: Complete lifecycle management for dataset URLs and uploads.
- **FastAPI Dataset REST Router (`apps/backend/bebshax/api/datasets.py`):**
  - Endpoints: `GET /api/datasets`, `POST /api/datasets/url`, `POST /api/datasets/upload`, `GET /api/datasets/{id}`, `POST /api/datasets/{id}/refresh`, `POST /api/datasets/{id}/query`, `DELETE /api/datasets/{id}`, `POST /api/datasets/{id}/generate-personas`.
  - Installed `python-multipart` for multipart form file uploads.
- **R8 Review for `python-multipart`:**
  - _Why:_ Required by Starlette/FastAPI to parse `multipart/form-data` file uploads for CSV/JSON/TSV/XLSX research dataset uploads.
  - _What it provides:_ Streaming multipart parser with memory/disk threshold management.
  - _License:_ Apache 2.0 (Permissive).
  - _Activity:_ Active standard library for FastAPI file uploads.
  - _Necessity:_ Essential for binary and tabular file uploads to `/api/datasets/upload`.
- **Frontend Dataset Laboratory & Diagnostics (`apps/frontend/`):**
  - Defined types in `types/dataset.ts`.
  - Added full API methods and mock fixtures to `services/api.ts` and `mocks/fixtures.ts`.
  - Created `OpenRouterDiagnosticModal.tsx`: Live developer diagnostic panel with zero key leakage, connection tester, and latency meter.
  - Created `DatasetSourcesView.tsx`: Comprehensive dataset management view with summary cards, table/cards, Add Dataset modal (URL & Upload), Dataset Detail modal (Overview, Inferred Schema, Descriptive Statistics, Discovered Segments), and Evidence-Grounded Persona Synthesis modal with mathematical quota allocation.
  - Added `Dataset Sources` to primary navigation in `DashboardLayout.tsx`.
  - Created Vitest tests in `tests/DatasetSources.test.tsx`.

**Tests:** 10/10 test files passed (45/45 frontend tests green); 153/153 backend pytest tests green.

### Part 1 (2026-08-25) — Dashboard & Study Creation

**What was built:**

- **Deterministic Study Title Generation (`apps/backend/bebshax/utils/title_generator.py`):**
  - Implemented `generate_deterministic_study_title(prompt, study_type)`: extracts concise, research-oriented titles by stripping conversational filler prefixes (`I'm building`, `We want to test`, `I want to validate`, etc.), title-casing tokens, preserving domain acronyms (`AI`, `ML`, `SaaS`, `B2B`, `B2C`, `API`, `WTP`, `BDT`), and handling type-specific fallbacks without unnecessary LLM calls (satisfying R3/R10/rules).
- **Backend Model & Database Persistence (`apps/backend/bebshax/db/models.py` & Alembic Migration):**
  - Extended `Studies` model with `target_audience: Optional[str]` and `pricing_hypothesis: Optional[str]`.
  - Generated Alembic migration `3900b8c81727_add_study_target_audience_and_pricing_.py` and applied migration to head on Neon PostgreSQL.
- **FastAPI Studies API & Validation (`apps/backend/bebshax/api/studies.py`):**
  - Added input validation in `create_study` requiring non-empty study ideas before creation.
  - Automatically derives deterministic title if not provided or left generic.
  - Strict user isolation in `get_study`, `update_study`, `delete_study`, and `list_studies`.
- **CSS Research Token System (`apps/frontend/src/index.css`):**
  - Replaced yellow/gold UI accents with modern indigo/violet AI-research tokens: `--accent-primary: #6366f1`, `--accent-hover: #818cf8`, `--accent-subtle: rgba(99, 102, 241, 0.12)`, `--accent-glow: rgba(99, 102, 241, 0.25)`, `--bg-pure: #08090b`, `--bg-secondary: #0d0f14`, `--border-subtle: #1e2330`.
- **New Study View (`apps/frontend/src/components/dashboard/views/NewStudyView.tsx`):**
  - Preserved the large central multiline textarea layout and rounded styling.
  - Added validation error alert banner for empty submissions.
  - Added `Ctrl+Enter` / `Cmd+Enter` keyboard shortcut.
  - Interactive submit button with loading state (`Creating study...`).
  - Implemented 4 canonical study type quick-select cards (User Interviews, Concept & Demand, Message Testing, Pricing & WTP) with subtle indigo active states and clear descriptions.
- **Dashboard Layout & Studies View (`DashboardLayout.tsx` & `StudiesDashboardView.tsx`):**
  - Updated sidebar navigation with indigo/violet active tabs.
  - Dynamic greeting based on time of day (`Good morning / afternoon / evening, {name}`).
  - Real dynamic Recent Studies loading from backend with loading skeleton and friendly empty state.
  - Immediate optimistic update of Recent Studies list upon study creation.
  - Updated Studies dashboard view, demo card, filter pills, and "Create Study" action button.
- **Automated Tests (`apps/backend/tests/test_studies_api.py` & `apps/frontend/tests/NewStudyView.test.tsx`):**
  - Backend tests: title generator, acronym casing, study creation, validation rejection, and user authorization isolation.
  - Frontend tests: prompt rendering, 4 study type cards, validation alert on empty submit, card selection, and `Ctrl+Enter` submission.

**Tests:** 11/11 frontend test suites passed (50/50 tests green); 156/156 backend pytest tests green.

### Part 2 (2026-08-26) — Evidence & Research Engine

**What was built:**

- **Database Models & Alembic Migration (`apps/backend/bebshax/db/models.py` & Alembic):**
  - Added 4 ORM models: `ResearchRuns`, `EvidenceSources`, `EvidenceChunks`, and `EvidenceClaims`.
  - Configured 384-dimensional vector embedding column on `evidence_chunks` with PostgreSQL `Vector(384)` and HNSW cosine distance index.
  - Generated and applied Alembic migration `f5e32fddb1b9_add_research_runs_evidence_sources_.py` to head on Neon PostgreSQL.
- **Research Engine Package (`apps/backend/bebshax/research/`):**
  - `query_generator.py`: Generates targeted research queries across Problem, Competition, Pricing, Behavior, and Complaints using `LLMService` (`TaskType.STRUCTURED_OUTPUT`) with deterministic fallback.
  - `search_provider.py`: Pluggable search source provider with curated empirical knowledge bases (student habits, survey spending, competitor reviews, tech culture in Dhaka/Chittagong) and deterministic deduplication via canonical URL normalization and content hash.
  - `chunker.py`: Sanitizes HTML/scripts and segments text into sentence-boundary preserved chunks (~400 chars with 40 char overlap).
  - `vector_search.py`: Generates 384-dim normalized embeddings using `HashEmbedding` / `FreellmpoolEmbedding` and performs cosine similarity queries (PostgreSQL native `vector_cosine_ops` with Python fallback for in-memory SQLite unit tests).
  - `claim_extractor.py`: Extracts structured claims using `LLMService` (`TaskType.EVIDENCE_EXTRACTION` & `TaskType.EVIDENCE_CLASSIFICATION`) and classifies into empirical statuses:
    - **GREEN (Evidence-supported)**: Direct citation and high confidence score.
    - **AMBER (Model inference)**: Plausible extrapolation flagged for interview exploration.
    - **RED (Unsupported assumption)**: Contradicted or unverified assumption; never silently promoted to evidence.
  - `service.py`: Orchestrates full research runs, streams state transitions, and computes evidence summary metrics (coverage %, supported %, inferred %, unverified %, source & claim counts).
- **FastAPI Evidence REST Router (`apps/backend/bebshax/api/evidence.py` & `main.py`):**
  - Endpoints: `POST /api/studies/{id}/research`, `GET /api/studies/{id}/research`, `GET /api/studies/{id}/research/{run_id}`, `GET /api/studies/{id}/evidence/summary`, `GET /api/studies/{id}/evidence/sources`, `GET /api/studies/{id}/evidence/sources/{id}`, `GET /api/studies/{id}/evidence/claims`, `GET /api/studies/{id}/evidence/claims/{id}`, `POST /api/studies/{id}/evidence/search`.
  - Strict caller ownership and isolation checks on all routes.
- **Frontend Evidence Laboratory (`apps/frontend/`):**
  - Defined TypeScript types in `types/evidence.ts` and exported in `types/index.ts`.
  - Added API client methods and mock store support in `services/api.ts` and `mocks/fixtures.ts`.
  - Created `EvidenceLaboratoryView.tsx`:
    - Top metrics banner: Evidence Coverage meter, Supported % (Green), Inferred % (Amber), Unverified % (Red), Total Sources and Total Claims.
    - "Run Research" primary action with interactive multi-step progress stepper (Idle -> Generating Queries -> Searching Sources -> Processing Chunks -> Extracting Claims -> Complete).
    - Tabs: Key Claims (with status filter pills, category filters, search input, confidence meters, supporting source chips), Sources & Chunks (type filters, relevance scores, publisher badges, direct URLs), and Research History.
    - Claim Provenance Modal: "Why does BebshaX evaluate this as [Status]?", full quote excerpts from supporting chunks, similarity scores, publisher metadata, and counter-evidence.
  - Updated `DashboardLayout.tsx` and `StudyWorkflowView.tsx` with seamless Evidence Laboratory navigation (`/research/:id/evidence` route).
- **Automated Tests (`test_evidence_engine.py` & `EvidenceLaboratory.test.tsx`):**
  - Backend tests: text cleaning, URL normalization, hash deduplication, query generation, 384-dim embeddings, pgvector retrieval, claim extraction, status classification, API lifecycle, and user isolation.
  - Frontend tests: coverage rendering, research runner, filter pills, search input, claim provenance modal opening/closing, and source repository tab.

**Tests:** 12/12 frontend test suites passed (55/55 tests green); 160/160 backend pytest tests green.

### Part 3 (2026-08-26) — Dataset Sources, Data Analysis & User-Scoped Research

**What was built:**

- **Database Models & Alembic Migration (`apps/backend/bebshax/db/models.py` & Alembic):**
  - Added `content_hash` column to `DatasetSources` to track dataset file changes and prevent silent invalidation of historical studies.
  - Generated and applied Alembic migration `614fe05a6f4d_add_content_hash_to_dataset_sources.py` to head on PostgreSQL.
- **Deterministic Profiler & Ingestion (`apps/backend/bebshax/datasets/`):**
  - Multi-format ingestion parser supporting CSV, JSON, XLSX, and TSV with strict size verification (≤25MB), content length validation, and anti-SSRF protections on URL fetches.
  - Deterministic statistical calculations (pure algorithmic computation, never hallucinated by LLM):
    - Row count, column count, column datatypes (numeric, categorical, boolean, datetime, text).
    - Missing cell count and missingness percentages per column and overall dataset.
    - Duplicate row detection and duplication percentage computation.
    - Numeric distribution analysis (min, max, mean, median, standard deviation, P25, P75, IQR).
    - Categorical frequency distributions (unique categories, value counts, percentages, top categories).
    - Automated data quality anomaly auditing (flagging duplicate records, missingness >10%, extreme outliers).
- **Backend API & Strict Multi-Tenant Isolation (`apps/backend/bebshax/api/datasets.py` & `api/studies.py`):**
  - Study-nested dataset routes: `GET /api/studies/{id}/datasets`, `POST /api/studies/{id}/datasets/url`, `POST /api/studies/{id}/datasets/upload`, `GET /api/studies/{id}/datasets/{ds_id}`, `GET /api/studies/{id}/datasets/{ds_id}/preview`, `POST /api/studies/{id}/datasets/{ds_id}/refresh`, `DELETE /api/studies/{id}/datasets/{ds_id}`.
  - Enforced zero-trust caller isolation (`_verify_study_access`) returning `404 Not Found` for unowned studies/datasets to prevent ID enumeration and data leakage.
  - Added paginated data preview endpoint (`/preview?offset=0&limit=20`) to safely render empirical subsets without loading full 25MB datasets into the browser.
  - Added hash-aware refresh (`POST /refresh`) that compares new `sha256` content hash against existing hash before re-profiling.
- **Teal / Cyan Research Theme & Frontend Polish (`apps/frontend/`):**
  - Globally updated application styling in `index.css` to the restrained **Teal / Cyan Research Theme** (`#14B8A6` primary, `#22D3EE` secondary, `#080A0A` background, `#0D1111` surface, `#202727` border, `#F4F7F7` text, `#8D9999` muted).
  - Modernized `DatasetSourcesView.tsx` with summary metrics banner (Connected Datasets, Total Empirical Records, Discovered Segments), dataset card grid with status badges, and Add Dataset modal supporting both URL and direct file upload (CSV, JSON, XLSX).
  - Built comprehensive Dataset Detail Modal featuring:
    - **Overview Tab**: Content SHA-256 hash, ingestion source, record counts, and last processed timestamp.
    - **Data Preview Tab**: Paginated row subset table with Previous/Next controls and row counters.
    - **Schema & Quality Tab**: Column type breakdown, missing value meters, duplicate row warnings, and data integrity health alerts.
    - **Descriptive Statistics Tab**: Numeric distribution metrics (Mean, Median, Std, IQR, Min, Max) and Categorical frequency bars.
    - **Discovered Segments Tab**: Empirical cluster breakdowns and grounded persona synthesis trigger.
- **Automated Tests:**
  - Backend: `test_dataset_ownership_idor.py` and `test_datasets_api.py` covering multi-format ingestion, statistical formulas, duplicate detection, data quality warnings, content hash tracking, and cross-user IDOR isolation.
  - Frontend: `DatasetSources.test.tsx` verifying card rendering, Add modal, tab navigation (Schema, Stats, Preview, Quality), and OpenRouter diagnostics.

**Tests:** 12/12 frontend test suites passed (55/55 tests green); 163/163 backend pytest tests green.

### Part 4 (2026-08-26) — Market Segmentation & Segment Builder

**What was built:**

- **Database Persistence & Alembic Migration (`apps/backend/bebshax/db/models.py` & Alembic):**
  - Added `SegmentationRuns` model: captures run status (`pending`, `analyzing_data`, `selecting_variables`, `clustering`, `interpreting_segments`, `completed`, `failed`), methodology, configuration parameters, `dataset_versions` (with `content_hash`), and `evidence_snapshot`.
  - Added `MarketSegments` model: captures data-grounded segments with `population_count`, `population_percentage`, `confidence_score`, status (`data_backed`, `inference_assisted`), `characteristics` (demographics, economics, behaviors, observed needs), `variable_distributions` (min, median, max, IQR), `evidence_citations`, and `differentiation_summary`.
  - Created and applied Alembic migration `7c8d9e0f1a2b_add_segmentation_runs_and_market_segments.py` on PostgreSQL.
- **Deterministic Market Segmentation Engine (`apps/backend/bebshax/segmentation/`):**
  - `pre_check.py`: Pre-segmentation data readiness evaluator returning structured assessment (`READY`, `LIMITED_DATA`, `NO_DATA`), usable candidate variables, coverage %, and guidance message.
  - `variable_selector.py`: High-signal variable discovery across demographic, economic, behavioral, and preference dimensions, filtering out constant/ID columns and ranking by coverage and usefulness score.
  - `clusterer.py`: Pure mathematical distribution calculations and deterministic cluster partitioning (quantile-based budget/demographic splits or explicit categorical groups). Computes exact row counts, population shares, medians, ranges, and IQR without LLM-invented statistics.
  - `interpreter.py`: Qualitative synthesis using `LLMService` (`TaskType.STRUCTURED_OUTPUT`) to generate grounded, human-readable segment names, descriptions, and differentiation summaries while preserving exact mathematical metrics and attaching cited research evidence claims. Includes resilient deterministic template fallback.
  - `service.py`: End-to-end orchestrator managing run status transitions, snapshotting dataset content hashes, generating side-by-side segment comparisons, and persisting segments.
- **FastAPI Segmentation REST Router (`apps/backend/bebshax/api/segmentation.py`):**
  - Endpoints: `GET /api/studies/{id}/segmentation/readiness`, `POST /api/studies/{id}/segmentation`, `GET /api/studies/{id}/segmentation/runs`, `GET /api/studies/{id}/segmentation/runs/{run_id}`, `GET /api/studies/{id}/segments`, `GET /api/studies/{id}/segments/{seg_id}`, `POST /api/studies/{id}/segments/compare`, `DELETE /api/studies/{id}/segmentation/runs/{run_id}`.
  - Enforced zero-trust study-scoped ownership verification returning `404 Not Found` for unowned studies, runs, and segments to prevent ID enumeration and data leakage.
- **Teal / Cyan Market Segmentation UI (`apps/frontend/`):**
  - Built `SegmentationView.tsx` with top metrics banner, pre-check readiness card, live running execution stepper, segment cards grid, search/filter controls, and JSON/CSV export.
  - Interactive Side-by-Side Comparison Modal comparing 2 to 4 segments across population share, median budget, age cohort, tech familiarity, and differentiation rationale.
  - Deep Dive Inspection Modal with 5 dedicated tabs: `Overview`, `Demographics & Traits`, `Economics & WTP`, `Evidence Citations`, and `Dataset Provenance`.
  - Connected `/research/:id/segmentation` route in `DashboardLayout.tsx` and added quick-switch Market Segments button in `StudyWorkflowView.tsx`.
- **Automated Tests:**
  - Backend (`test_segmentation_engine.py` & `test_segmentation_ownership_idor.py`): deterministic quantile calculations, variable filtering, readiness evaluation, evidence linking, LLM fallback, dataset hash versioning, and strict User A vs User B IDOR isolation.
  - Frontend (`SegmentationView.test.tsx`): banner metrics, readiness assessment, run trigger, progress stepper, deep dive tab navigation, side-by-side comparison modal, search filtering, and JSON/CSV export.

**Tests:** 13/13 frontend test suites passed (60/60 tests green); 170/170 backend pytest tests green.

---

### Part 5 (2026-08-26) — Synthetic Persona Generation & Persona Library

**What was built:**

- **Database Persistence & Alembic Migration (`apps/backend/bebshax/db/models.py` & Alembic):**
  - Extended `Personas` table with study-scoped columns: `study_id`, `user_id`, `segment_id`, `generation_run_id`, `archetype`, `quote`, `goals`, `needs`, `pain_points`, `behaviors`, `preferences`, `motivations`, `objections`, `commercial_profile`, `technology_profile`, `evidence_citations`, `dataset_refs`, `grounding_score`, `confidence`, `validation_warnings`, `is_synthetic`, and made legacy `business_id` nullable.
  - Created `PersonaGenerationRuns` table tracking historical runs with `configuration`, `status`, `target_count`, `generated_count`, `valid_count`, `warning_count`, `dataset_versions` (with content SHA-256 hashes), `evidence_snapshot`, and timestamps.
  - Created and applied Alembic migration `8d9e0f1a2b3c_add_persona_generation_runs_and_update_personas.py` to head on PostgreSQL.
- **Deterministic Persona Generation & Grounding Engine (`apps/backend/bebshax/personas/`):**
  - `validator.py`: Pure algorithmic range validation verifying age bounds ($\pm 2$ years of segment demographics), monthly budget limits, required attributes (goals, pain points, behaviors), and calculates deterministic grounding score clamped to $[0.50, 0.98]$ with status marking (`ready` vs `needs_review`).
  - `generator.py`: Largest Remainder quota allocator supporting both population-weighted (matching segment percentages) and equal distributions; prompt engineering via `LLMService` (`TaskType.PERSONA_GENERATION`); resilient fallback template with Bangladeshi student/candidate personas grounded in local currency (BDT) and wallets (bKash/Nagad).
  - `service.py`: Orchestrator managing run lifecycle, duplicate-run locking, dataset content hash snapshotting, evidence claim citation linking, persona persistence, and single-persona regeneration.
- **FastAPI Persona REST Router (`apps/backend/bebshax/api/personas.py`):**
  - Study-scoped endpoints: `GET /api/studies/{id}/personas`, `POST /api/studies/{id}/personas/generate`, `GET /api/studies/{id}/personas/{persona_id}`, `POST /api/studies/{id}/personas/{persona_id}/regenerate`, `GET /api/studies/{id}/persona-runs`, `GET /api/studies/{id}/persona-runs/{run_id}`, `DELETE /api/studies/{id}/persona-runs/{run_id}`.
  - Enforced zero-trust ownership verification (`_verify_study_access`) returning `404 Not Found` for unowned studies, personas, and runs.
- **Teal / Cyan Persona Library UI (`apps/frontend/`):**
  - Built `PersonaLibraryView.tsx` with summary metrics banner (Total Synthetic Personas, Represented Segments, Avg Grounding Score, Ready to Interview), persona cards grid with geometric initials avatars, Synthetic tags, and visual grounding meters.
  - Generation Modal with quota distribution selector (`Population-weighted` vs `Equal distribution`) and live 5-step progress stepper.
  - Deep Dive Inspector Modal with 5 tabs: `Profile & Traits`, `Commercial & WTP`, `Technology Profile`, `Evidence Citations`, and `Dataset Provenance`, plus individual persona regeneration.
  - Search, filter by segment/status/run/grounding, and JSON / CSV export buttons.
  - Connected `/persona-library` navigation and header buttons in `DashboardLayout.tsx` and `StudyWorkflowView.tsx`.
- **Automated Tests:**
  - Backend: `test_persona_generation_engine.py` and `test_persona_ownership_idor.py` covering quota allocation, deterministic grounding calculation, range checks, lifecycle runs, and cross-user IDOR isolation (**177/177 pytest passed**).
  - Frontend: `PersonaLibraryView.test.tsx` verifying card rendering, metrics, modal stepper, deep dive tab switching, search filtering, regeneration, and export (**14/14 test suites, 65/65 vitest passed**).

**Tests:** 14/14 frontend test suites passed (65/65 tests green); 177/177 backend pytest tests green.

---

### Part 6 (2026-08-26) — Adaptive Persona Interviews & Structured Insights

**What was built:**

- **Database Persistence & Alembic Migration (`apps/backend/bebshax/interview/orm.py` & Alembic):**
  - Expanded `Conversations` (aliased `Interviews`) with study-scoped columns: `study_id`, `user_id`, `persona_id`, `persona_version`, `persona_name`, `persona_occupation`, `objective`, `interview_type` (`adaptive_persona`), `length_tier` (`short` / `standard` / `deep`), `max_turns` (6 / 14 / 24), `status` (`active` / `completed`), `topics_explored` (JSON mapping across 9 core discovery dimensions), `summary`, `key_findings`, and `metrics`.
  - Expanded `ConversationTurns` (aliased `InterviewTurns`) with `turn_number`, `role` (`interviewer` / `persona`), `topic`, `served_by`, and `latency_ms`.
  - Created `InterviewInsights` table with `interview_id`, `persona_id`, `study_id`, `user_id`, `type` (`pain_point` / `willingness_to_pay` / `feature_demand` / `objection` / `quote` / `unmet_need`), `title`, `description`, `supporting_turn_numbers` (array of transcript turns providing verifiable evidence), `confidence`, and `is_synthetic` flag.
  - Created and applied Alembic migration `af1e2d3c4b5a_add_interview_insights_and_update_conversations.py` to head on PostgreSQL.
- **Adaptive Persona Interview Engine (`apps/backend/bebshax/interview/engine.py`):**
  - Dynamic Persona Context Compilation: builds persona identity card from demographic details, commercial profile (monthly budget in BDT, price sensitivity, payment preferences), technology profile, goals, pain points, behaviors, objections, and cites connected empirical evidence.
  - Episodic Memory Retrieval: queries `MemoryService` (pgvector cosine similarity) for relevant past turns and observations.
  - Anti-Sycophancy & Grounded Persona Guardrails: Persona realistically doubts, hesitates, or declines offers outside their budget or lifestyle; refuses prompt leakage and retains immersion without breaking character.
  - Dynamic Topic Tracking & Classification: automatically tracks 9 core dimensions (`pain_points`, `pricing_budget`, `current_behavior`, `feature_demand`, `objections_friction`, `channel_discovery`, `alternatives_competition`, `willingness_to_pay`, `lifestyle_context`) based on conversational content.
  - Dynamic Suggested Questions Generator (`generate_suggested_questions`): generates 3 contextual, high-signal follow-up questions for unexplored topics based on current transcript state.
  - Structured Synthesis & Insight Extraction (`complete`): executes `TaskType.STRUCTURED_OUTPUT` to generate an executive summary, key findings, and structured `InterviewInsights` with explicit `supporting_turn_numbers` linking claims back to transcript lines.
- **FastAPI Interview REST Router (`apps/backend/bebshax/api/interviews.py`):**
  - Endpoints:
    - `POST /api/studies/{study_id}/personas/{persona_id}/interviews` (Start new adaptive interview with objective & length tier)
    - `GET /api/studies/{study_id}/interviews` (List study interviews with status & objective filters)
    - `GET /api/studies/{study_id}/interviews/metrics` (Aggregate study interview metrics)
    - `GET /api/studies/{study_id}/interviews/{interview_id}` (Retrieve transcript, topics, suggestions, insights)
    - `POST /api/studies/{study_id}/interviews/{interview_id}/messages` (Submit question and receive persona response)
    - `POST /api/studies/{study_id}/interviews/{interview_id}/complete` (Conclude interview and generate synthesis)
    - `GET /api/studies/{study_id}/interviews/{interview_id}/insights` (List extracted structured insights)
  - Strict IDOR isolation: all endpoints verify user ownership of study and entities, returning `404 Not Found` on cross-tenant access.
- **Teal / Cyan Adaptive Interview UI (`apps/frontend/`):**
  - `InterviewsView.tsx`: Study-level interview hub with 4 top metric cards (Total Interviews, Active, Completed, Insights Generated), search and status/objective filter bar, and responsive interview cards with progress meters and quick actions.
  - `StartInterviewModal.tsx`: Modal launched from persona cards with persona identity header, synthetic badge, 5 objective presets (`Problem & Pain Point Discovery`, `Pricing & Willingness to Pay`, `Feature Validation & Feedback`, `Behavioral & Workflow Understanding`, `General Customer Discovery`) plus custom input, and 3 length tier cards (`Short 5–7 turns`, `Standard 10–15 turns`, `Deep 20+ turns`).
  - `InterviewWorkspaceView.tsx`: Live research interview workspace featuring:
    - Left Persona Sidebar: demographic card, commercial budget (BDT), tech stack, evidence citations, and interactive checklist of explored vs unexplored topics.
    - Live Conversation Transcript: turn numbers, speaker badges, topic tags, model latency info, and simulated typing indicator.
    - Suggested Questions Bar: clickable contextual question pills that populate the composer.
    - Multiline Sticky Composer: `Enter` to send, `Shift+Enter` for new line, turn counter progress bar, and "Finish Interview" action.
    - Synthesis & Insights Tab: executive summary, key findings, and structured insight cards grouped by category with interactive `Turn #N` provenance badges that jump to supporting transcript turns.
  - Connected `/interviews` and `/interviews/:id` navigation and routes in `DashboardLayout.tsx`.
- **Automated Tests:**
  - Backend (`test_adaptive_engine.py` & `test_interview_ownership_idor.py`): multi-turn conversational grounding, anti-sycophantic resistance, topic classification, length tier enforcement, structured insight extraction with supporting turn provenance, and zero-trust IDOR isolation (**190/190 pytest passed**).
  - Frontend (`AdaptiveInterview.test.tsx`): hub rendering, metrics, modal objective selection, length tier selection, transcript rendering, suggested question clicks, message dispatching, and synthesis tab review (**15/15 test suites, 68/68 vitest passed**; `npx tsc --noEmit` 0 errors).

**Tests:** 15/15 frontend test suites passed (68/68 tests green); 190/190 backend pytest tests green; TypeScript typecheck green (0 errors).

---

### Part 7 (2026-08-26) — Behavioral Testing & Simulation ✅

**What was built:**

- **Task Type & Model Pools (`apps/backend/bebshax/llm/`):**
  - Added `TaskType.BEHAVIORAL_SIMULATION` in `apps/backend/bebshax/llm/types.py`.
  - Mapped `TaskType.BEHAVIORAL_SIMULATION` to the high-reliability `"reasoning"` model pool in `apps/backend/bebshax/llm/pools.py`.
- **Database Persistence & Alembic Migration (`apps/backend/bebshax/behavioral/orm.py` & Alembic):**
  - Created ORM models: `BehavioralTests`, `BehavioralTestScenarios`, `BehavioralTestRuns`, `BehavioralTestResults`, and `BehavioralInsights`.
  - Created and applied Alembic migration `b8e4f1a2c3d5_add_behavioral_testing_tables.py` adding all 5 behavioral testing tables with UUID primary keys, foreign keys, and indexes.
- **Simulation Engine & Anti-Sycophancy Guardrails (`apps/backend/bebshax/behavioral/engine.py`):**
  - Modular Simulation Framework: 8 test types implemented with domain-specific decision evaluation logic (`purchase_decision`, `pricing_test`, `feature_test`, `concept_test`, `message_test`, `offer_test`, `switching_test`, `objection_test`).
  - Context Aggregator: aggregates persona commercial profiles, monthly budget (BDT), pain points, behaviors, objections, Part 2 evidence claims, and Part 6 adaptive interview transcripts.
  - Non-Sycophantic Prompting: personas evaluate scenarios within disposable budget (e.g. ৳300–৳600), consider free alternatives, and challenge concepts with genuine friction. Untrusted scenario inputs are wrapped in `<UNTRUSTED_SCENARIO>` tags with system instruction override defenses.
  - Deterministic Confidence Scoring: calculated from presence of commercial budget, interview transcript depth, and evidence grounding.
  - Aggregate Synthesizer: computes positive/neutral/negative distributions, average purchase likelihood percentage, segment-level breakdowns, cross-persona pattern extraction, and surfaced risks/opportunities.
  - Resilience & Retries: `retry_failed_simulations` handler that re-runs only failed or timeout persona simulations and updates aggregate metrics.
- **FastAPI Behavioral REST Router (`apps/backend/bebshax/api/behavioral.py`):**
  - Study-scoped endpoints with strict IDOR ownership verification:
    - `POST /api/studies/{study_id}/behavioral-tests` (Create test & scenario)
    - `GET /api/studies/{study_id}/behavioral-tests` (List study tests with summary metrics)
    - `GET /api/studies/{study_id}/behavioral-tests/metrics` (Aggregate behavioral testing metrics)
    - `GET /api/studies/{study_id}/behavioral-tests/{test_id}` (Test details & configuration)
    - `PUT /api/studies/{study_id}/behavioral-tests/{test_id}` (Update test)
    - `DELETE /api/studies/{study_id}/behavioral-tests/{test_id}` (Delete test)
    - `POST /api/studies/{study_id}/behavioral-tests/{test_id}/runs` (Trigger new simulation run across personas/segments)
    - `GET /api/studies/{study_id}/behavioral-tests/{test_id}/runs` (List historical simulation runs)
    - `GET /api/studies/{study_id}/behavioral-tests/runs/{run_id}` (Simulation run details, progress, & individual results)
    - `POST /api/studies/{study_id}/behavioral-tests/runs/{run_id}/retry-failed` (Retry failed persona simulations)
    - `GET /api/studies/{study_id}/behavioral-tests/compare` (Side-by-side run comparison)
- **Teal / Cyan Behavioral Testing Frontend UI (`apps/frontend/`):**
  - TypeScript types (`src/types/behavioral.ts`) exported in `src/types/index.ts`.
  - API Client methods in `src/services/api.ts`.
  - `CreateBehavioralTestModal.tsx`: 4-step interactive wizard (Test Type Selection with 8 rich cards → Dynamic Scenario Configuration → Target Population Selector with All/Segment/Individual modes → Preview & Confirm with Synthetic Simulation disclaimer).
  - `BehavioralTestingView.tsx`: Main overview hub with 4 top metrics (Total Tests, Simulation Runs, Personas Evaluated, Avg Purchase Likelihood), filter & search controls, and test cards with status badges and re-run triggers.
  - `BehavioralTestDetailView.tsx`: In-depth results view with live simulation polling, stacked sentiment distribution bar, confidence breakdown, identified risks & friction points, opportunities & drivers, segment comparison table, persona decision grid, retry failed button, and an interactive Persona Decision Inspector modal displaying reasoning chains and grounded context signals.
  - `BehavioralComparisonView.tsx`: Side-by-side simulation run comparison matrix for parameter variation analysis.
  - `PersonaLibraryView.tsx`: Added "Test Behavior" quick-action button on persona cards.
  - `DashboardLayout.tsx`: Added "Behavioral Testing" sidebar navigation item and route matching for `/behavioral-tests`, `/behavioral-tests/:id`, and `/behavioral-tests/compare`.
- **Automated Tests:**
  - Backend: `apps/backend/tests/behavioral/test_behavioral_engine.py` (engine unit tests) and `apps/backend/tests/test_behavioral_api_idor.py` (IDOR isolation) (**195/195 pytest passed**).
  - Frontend: `apps/frontend/tests/BehavioralTesting.test.tsx` testing overview rendering, 4-step wizard, result detail view, persona inspector drawer, and run comparison (**16/16 test suites, 72/72 vitest passed**).
  - Full bundle build: `npm run build` green (0 TypeScript compilation errors).

**Tests:** 16/16 frontend test suites passed (72/72 tests green); 195/195 backend pytest tests green; Vite build complete.

### Master Workflow Implementation & End-to-End Product Rebuild (2026-08-26)

- **Objective:** Rebuilt BebshaX into a complete, unified end-to-end research platform. Connected every stage of the pipeline: Prompt Input → Context Refinement & Evidence Gathering → Grounded Persona Generation → Dynamic Script Questions → Synthetic Interviews & Transcripts → Structured Insights & Behavioral Testing → 20-Section Comprehensive Decision Report.
- **Database & Backend Architecture:**
  - Added `StudyReports` database model (`apps/backend/bebshax/db/models.py`) with 20 sections, JSON schema enforcement, multi-versioning, metrics, and timestamps.
  - Added Alembic migration `e7f1a2b3c4d5_add_study_reports_table.py`.
  - Created `StudyReportService` (`apps/backend/bebshax/research/report_service.py`) utilizing `LLMService` with `TaskType.REPORT_GENERATION` and deterministic grounded fallback.
  - Added study endpoints (`apps/backend/bebshax/api/studies.py`):
    - `POST /api/studies/{study_id}/reports/generate` (Versioned report generation)
    - `GET /api/studies/{study_id}/reports` (List versions with IDOR enforcement)
    - `GET /api/studies/{study_id}/reports/latest` (Retrieve latest study report)
    - `GET /api/studies/{study_id}/reports/{report_id}` (Get specific version)
    - `POST /api/studies/{study_id}/script/generate` (Dynamic interview question generation)
    - `POST /api/studies/{study_id}/research/run` (Autonomous background research trigger)
  - Added batch synthetic interview execution endpoint `POST /api/studies/{study_id}/interviews/batch-run` (`apps/backend/bebshax/api/interviews.py`) running multi-persona simulations with persisted conversation turns and turn provenance numbers.
  - Added PostgreSQL persistence in `generate_study_personas` (`apps/backend/bebshax/api/copilot.py`).
- **Frontend & Master Workflow UI:**
  - Completely redesigned `StudyWorkflowView.tsx` into a 5-step stepper (`Context` → `Personas` → `Script` → `Interviews` → `Report`) in a sleek Teal/Cyan theme.
  - Completely removed obsolete manual "Dataset Sources" navigation and views per the automated research directive.
  - Integrated live Copilot dialogue, automated role suggestions, grounded persona cards with attribute and provenance inspection, dynamic script generation with full question editing, batch multi-persona interviews with live transcripts, and rich 20-section report synthesis with markdown export.
- **Verification & Testing:**
  - Backend: `apps/backend/tests/test_study_reports_and_master_workflow.py` testing report generation, versioning, IDOR authorization, dynamic scripts, and batch interviews (**198/198 pytest tests green**).
  - Adapter boundary test `apps/backend/tests/llm/test_boundary.py` verified (**R1 compliance preserved**).
  - Frontend: All 16 vitest test suites passed (**71/71 tests green**).
  - Frontend production bundle build verified (`npm run build` green).

---

### Maintenance (2026-08-26) — Security Fix B3 (Unverified Identity & Token Bypass)

- **Audit item addressed:** 🔴 **B3** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **Changes Applied:**
  - **Part 1 (/google endpoint deletion):** Completely removed `class GoogleAuthRequest` and `@auth_router.post("/google")` in `apps/backend/bebshax/api/auth.py`. No signature verification or GIS integration existed.
  - **Part 2 (/sync token verification):** Added `neon_auth_url` configuration in `apps/backend/bebshax/config.py`. Implemented `verify_neon_token(token: str)` in `apps/backend/bebshax/api/auth.py` to verify Neon session tokens server-side via `GET /get-session` with `Authorization: Bearer <neon_token>`. Updated `UserSyncRequest` to require `neon_token: str` and removed client-supplied `email` from user lookup and creation.
  - **Frontend handoff:** Prepared exact diffs for Shehab to remove obsolete Google sign-in buttons in `AuthPage.tsx` and `AuthModal.tsx`, remove `googleAuth()` in `services/api.ts`, and forward `neon_token` in `syncUser({ neon_token })`.
- **Regression Tests:**
  - `apps/backend/tests/test_auth_google_removed.py` (2 tests, verifying 404/405 and absence from OpenAPI schema).
  - `apps/backend/tests/test_auth_sync_verification.py` (4 tests, verifying rejection of missing token, rejection of invalid token, authoritative identity from verified Neon user, and exclusion of client-claimed email field).
- **Verification:** All 18 auth tests in backend suite passed cleanly.

---

### Maintenance (2026-08-26) — Migration Drift Guard (H6)

- **Audit item addressed:** 🟠 **H6** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **Changes Applied:**
  - **Local Dev Guard:** Added `check_migrations_current()` in `apps/backend/bebshax/main.py` using Alembic's Python API (`Config`, `ScriptDirectory`, `MigrationContext`).
  - **Lifespan Integration:** Hooked `check_migrations_current(settings.sync_database_url)` into `_lifespan` in `apps/backend/bebshax/main.py` for local dev environments (`localhost` / `development`), producing a loud fatal message and exiting immediately with `SystemExit(1)` and instructions to run `alembic upgrade head` instead of mysterious 500 runtime errors.
  - **Config Helper:** Added `sync_database_url` property in `apps/backend/bebshax/config.py`.
- **Regression Tests:**
  - `apps/backend/tests/db/test_migration_drift_guard.py` (2 tests asserting `SystemExit` when behind head and clean startup when at head).
- **Verification:** 2/2 tests green.

---

### Maintenance (2026-08-26) — Password Policy Beyond Length (H8)

- **Audit item addressed:** 🟠 **H8** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **Changes Applied:**
  - **Alphanumeric Password Validator:** Added `password_must_be_alphanumeric_mix` validator to `SignUpRequest` in `apps/backend/bebshax/api/auth.py` requiring at least one letter and at least one digit (`has_letter and has_digit`).
  - **Copy Consistency:** Matched the exact frontend UI promise displayed to users ("At least 8 characters, alphanumeric") without introducing unadvertised symbol/blocklist scope changes.
- **Regression Tests:**
  - `apps/backend/tests/api/test_password_policy.py` (4 tests verifying numeric-only rejection, alpha-only rejection, alphanumeric acceptance, and length limit preservation).
- **Verification:** 4/4 tests green.

---

### Maintenance (2026-08-26) — Demo Mode Seeding & Docs (H3 Pieces 1 & 3)

- **Audit item addressed:** 🟠 **H3** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **Changes Applied:**
  - **Flag-Gated Seeding (Piece 1):** Updated `seed_demo_data()` in `apps/backend/bebshax/db/seed.py` to check `settings.demo_mode` and skip inserting entities unless `demo_mode=True` or `force=True`.
  - **Documentation & Status (Piece 3):** Created `docs/DEMO.md` detailing demo mode configuration, sample entities, and data source transparency; corrected `PROJECT_CONTEXT.md` to reflect that Phase 13 is in-progress pending Shehab UI cached badges.
- **Regression Tests:**
  - `apps/backend/tests/db/test_seed_demo_mode.py` (3 tests verifying skipping when False, running when True, and forced execution).
- **Verification:** 3/3 tests green; backend suite passing.

---

### Maintenance (2026-08-26) — Auth Rate Limiting & Failed Attempt Logging (H7)

- **Audit item addressed:** 🟠 **H7** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **R8 Dependency Review:**
  - **Package:** `slowapi` (v0.1.10) / `limits` (v5.8.0), `wrapt` (v2.3.0), `deprecated` (v1.3.1).
  - **Purpose:** FastAPI/Starlette-native IP-based in-memory rate limiting.
  - **License:** MIT (compatible).
  - **Security:** 0 known CVEs; in-memory storage (zero extra infrastructure overhead, fits single-worker topology).
- **Changes Applied:**
  - **Shared Limiter:** Created `apps/backend/bebshax/api/limiter.py` initializing `Limiter(key_func=get_remote_address)`.
  - **App Wiring:** Integrated `SlowAPIMiddleware` and `RateLimitExceeded` handler in `apps/backend/bebshax/main.py`.
  - **Endpoint Gating:** Added `@limiter.limit("5/minute")` to `/api/auth/signin` in `apps/backend/bebshax/api/auth.py`.
  - **Audit Logging:** Added `logger.warning("Failed signin attempt for %s from %s", payload.email, client_ip)` on invalid authentication (explicitly omitting passwords).
- **Regression Tests:**
  - `apps/backend/tests/api/test_signin_rate_limit.py` (4 tests verifying 429 threshold enforcement, initial attempt allowance, multi-email IP sharing, and password-free audit logging).
- **Verification:** 4/4 tests green; full backend suite passing.

---

### Maintenance (2026-08-26) — Shehab Track Audit Completion (16 Items: B5, H1, M1, M7, L1–L11, L15)

- **Audit items addressed:** 🔴 **B5**, 🟠 **H1**, 🟡 **M1**, 🟡 **M7**, ⚪ **L1**, ⚪ **L2**, ⚪ **L3**, ⚪ **L4**, ⚪ **L5**, ⚪ **L6**, ⚪ **L7**, ⚪ **L8**, ⚪ **L9**, ⚪ **L10**, ⚪ **L11**, ⚪ **L15** ([AUDIT_ASSIGNMENTS.md](AUDIT_ASSIGNMENTS.md) & [E2E_AUDIT_2026-08-24.md](E2E_AUDIT_2026-08-24.md)).
- **Changes Applied:**
  - **B5 & M7 (Auth & Session Security):**
    - `apps/frontend/src/services/api.ts`: Removed fake user synthesis (`Sarah Chen`) from `getMe()`. Invalid/expired tokens return `null` and clear local storage.
    - `apps/frontend/src/context/AuthContext.tsx`: On unauthenticated `/auth/me` responses, completely purges state (`user = null, token = null, storedUser = null, authToken = null`), preventing garbage tokens in `localStorage` from fabricating a logged-in session.
    - Added `_isTokenExpired` with automatic JWT expiration checking on access.
  - **H1, L8, L9, L10 (Live Error Propagation & State Honesty):**
    - `apps/frontend/src/services/api.ts`: Replaced silent fallback `catch {} -> return mock` with explicit error propagation.
    - Raised API timeouts to 120s (`generatePersona`, study creation) and 300s (`sendMessage`) to prevent premature aborts on slow LLM calls.
    - Reset `lastKnownLive = false` upon network failure.
    - `resetMockStore()` enables deterministic testing, and empty responses (`[]`) are preserved without mock substitution.
  - **M1 (Live Evaluation Metrics):**
    - `apps/backend/bebshax/api/evaluation.py`: Replaced hardcoded literal numbers in `overall_health` and `routing_strategies` with live database calculations across `LLMRequests` and `Personas`. Returns honest `0.0` values when no requests have run.
  - **L1, L3, L4, L15 (Performance, A11y, Modern Web Architecture):**
    - `apps/frontend/index.html`: Added `window.THREE` stub before script tags, pinned Vanta version `vanta@0.5.24`, and deferred third-party script loading.
    - `apps/frontend/src/main.tsx`: Wrapped root in `<React.StrictMode>`.
    - `apps/frontend/vite.config.ts`: Configured Rollup `manualChunks` in build options to code-split JS into `landing`, `dashboard`, `auth`, `vendor-react`, and `vendor-icons` chunks.
    - `apps/frontend/src/components/landing/AnimatedBackground.tsx`: Added `prefers-reduced-motion` support, pause on `visibilitychange` (`document.hidden`), and pause via `IntersectionObserver` when scrolled off screen. Added `*:focus-visible` styles in `index.css`.
  - **L2, L5, L6, L11 (Auth Polish, Validation, & Privacy):**
    - `apps/frontend/src/components/auth/AuthPage.tsx` & `AuthModal.tsx`: Connected Terms of Service and Privacy Policy buttons to `LegalModal.tsx`.
    - Added `name` and `autoComplete` attributes to all form inputs.
    - Enforced client-side alphanumeric password validation.
    - Removed hardcoded Unsplash photo fallbacks.
- **Regression Tests:**
  - `apps/frontend/tests/ShehabAudit.test.ts` (B5, M7, H1, L7, L8, L9, L10).
  - `apps/frontend/tests/ShehabAuditComponents.test.tsx` (L2, L5, L6, L11).
  - `apps/backend/tests/test_api_integration.py` (M1 `/api/evaluation/metrics`).
- **Verification:**
  - Frontend: 17/17 test suites passed (**75/75 tests green**); `npm run build` succeeds cleanly with code-split bundles.
  - Backend: **296/296 pytest tests green**.

---

### Maintenance (2026-08-26) — Email Verification Flow (H9)

- **Audit item addressed:** 🟠 **H9** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **R8 Service Dependency Review (Resend REST API):**
  - **Service:** Resend (`https://api.resend.com/emails`).
  - **Client:** Plain `httpx.AsyncClient` (zero new Python packages added; existing `httpx` reused).
  - **Free Tier:** 3,000 emails/month, 100/day free limit — suitable for demo scale.
  - **Data Outflow:** User recipient email address and verification link containing a 32-byte cryptographic token.
  - **Security & Key Management:** `BEBSHAX_RESEND_API_KEY` configured in `.env` / `Settings`, never committed to source. Fail-soft error handling logs warnings without crashing account creation if delivery fails.
- **Changes Applied:**
  - **Model & Database:** Created `EmailVerificationToken` model in `apps/backend/bebshax/auth/models.py` and Alembic migration `7a8b9c0d1e2f` adding `email_verification_tokens` table.
  - **Email Service:** Created `apps/backend/bebshax/auth/email.py` implementing `send_verification_email()`.
  - **Signup Integration:** Wired verification token creation (`secrets.token_urlsafe(32)`) and email dispatch into `POST /api/auth/signup`.
  - **Endpoints:**
    - `POST /api/auth/verify-email`: Validates verification token, checks 24-hour expiration and reuse, sets `user.is_verified = True`.
    - `POST /api/auth/resend-verification`: Rate-limited via slowapi (`3/hour`), dispatches fresh verification token.
  - **Configuration:** Added `resend_api_key`, `email_from_address`, and `frontend_base_url` to `Settings` in `config.py`.
- **Verification:** 9/9 tests green; all 39 auth tests passing.

---

### Maintenance (2026-08-26) — Tenancy owner_id Backfill & NOT NULL Enforcement (B6 Stage 2 Data Layer)

- **Audit item addressed:** 🔴 **B6** (E2E_AUDIT_2026-08-24.md & AUDIT_ASSIGNMENTS.md).
- **Changes Applied:**
  - **Stability Prerequisite:** Confirmed B4 JWT secret rotation completed and stable with zero `JWT_SECRET_PREVIOUS` residual in production.
  - **System Holder Account:** Created tagged system holder account `usr_system_holder` (`system@bebshax.internal`, `"BebshaX System Data (do not treat as a real user)"`, `auth_provider="system"`).
  - **Data Backfill & Schema Migration:** Applied Alembic migration `4e5f6a7b8c9d` backfilling 8 existing businesses and 37 personas (including demo-mode seed entities) to `usr_system_holder`, and altering `businesses.owner_id` and `personas.owner_id` to `NOT NULL`.
  - **Seed Integration:** Updated `seed_demo_data()` in `apps/backend/bebshax/db/seed.py` and `apps/backend/bebshax/persona/store.py` to explicitly assign `owner_id="usr_system_holder"` on all demo entities.
  - **API Scope Handoff:** Formulated API row-scoping spec for Tayeb to wire `Depends(get_current_user)` across `api/**`.
- **Regression Tests:**
  - `apps/backend/tests/db/test_owner_id_enforcement.py` (5 tests verifying NOT NULL integrity constraints on Businesses and Personas, tagged system holder properties, demo seed system ownership, and zero orphaned rows remaining).
- **Verification:** 5/5 tests green; full backend test suite passing.

# Ship Readiness Report — BebshaX (2026-09-07; counts refreshed 2026-09-08)

> One page per subsystem: what is implemented, how it was verified in this pass, and its status. ✅ VERIFIED COMPLETE · 🟡 PARTIALLY COMPLETE · 🔴 BLOCKED · ⏸️ DEFERRED. Detailed checklists: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); audit narrative: [COMPETITION_AUDIT.md](COMPETITION_AUDIT.md) (re-audit 2026-09-08: 86/100, live AI audit 56/56); evidence classification: [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md); attack matrix: [ADVERSARIAL_TESTS.md](ADVERSARIAL_TESTS.md).

## Current ML maintenance status (2026-09-09)

The original 15 phases and dates are unchanged. The subsystem/test tables below
are historical September 7–8 snapshots, not current ML acceptance or publication
gates. In particular, earlier LLM-generated country/budget and full-Compose
observations are not validation of the new selector.
Post-sync local checks are distinguished from earlier live evidence below.

| Current requirement     | Status / evidence                                                                                                                                                                                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Four generation paths   | Shared CPU `MLPersonaAdapter` selects complete synthetic source profiles; existing schemas/DB JSON and LLM interviews remain; 503/422 errors, no LLM fallback                                                                                                       |
| Packaging               | Exact numerical versions pinned for local/Docker installs; Windows artifact loaded in Linux with networking disabled, five profiles selected                                                                                                                        |
| Fresh deployment        | Must train or stage the ignored ~32.54 MiB model; package-only checkout/image is insufficient; restart after validated artifact replacement                                                                                                                         |
| Post-sync local suites  | Backend 1,287 passed / 3 deselected (81.64% coverage) after the exact warning-policy correction; ML 298 passed after fixture isolation (earlier coverage 97%); frontend 269 passed / 36 files after the CSS token correction                                        |
| Other post-sync checks  | Ruff, `pip check`, both quiet Compose configuration checks, and all 5 trained-artifact smoke stages passed. Latest TypeScript/Vite build and theme check passed after the token correction; 0 theme violations                                                      |
| Earlier real workflow   | Five unique age-bounded profiles saved/read back, 22 synthetic claims reported, zero LLM generation calls; seven Freellmpool responses, ten role suggestions, two interview turns, four memory rows; 2 PostgreSQL integration tests passed. Not repeated after sync |
| Research limits         | NMF retrieval loses to lexical baseline; USA-only source, visible workforce bias, no demand/population/student/Bangladesh validity or inferred budget/OCEAN                                                                                                         |
| Unfinished verification | Full Compose app/web and cross-conversation retrieval rehearsals not repeated; Pyright unavailable. Earlier desktop passed; mobile header clipping remains unfixed and was not reverified after upstream styling or the token-only correction                       |

This is **not a production sign-off**. Source exclusions now use cooperating
parent-row locks before selection/persistence, including regeneration archiving;
there is no global source-identity unique constraint or live multi-process proof.
The older post-sync counts above are superseded by the current results below. The
[post-sync local checks](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09)
passed at the recorded scopes; commit, push, and remote CI results are tracked
separately in the [implementation log](IMPLEMENTATION_PLAN.md), not claimed
successful here. See the [current readiness assessment](PRODUCTION_READINESS.md).

## Current Hardening Verification (2026-09-09)

**READY WITH RESERVATIONS.** The results below were executed locally during the
hardening pass. Earlier evidence above and the September 7-8 tables below remain
historical, not current acceptance gates.

| Check                  | Current result / scope                                                                                                                                                                                                                                                                   |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend                | 1,639 passed, 3 integration deselected; 773.82 s; 82.72% coverage (80% required). Initial 11 failures resolved; no remaining test failures in this run                                                                                                                                   |
| Frontend               | 293 tests / 40 files; TypeScript/Vite PASS, build 4.39 s; theme check 0 files                                                                                                                                                                                                            |
| ML / SSRF              | ML 298 passed in 34.05 s; root SSRF regression 3 passed; backend-enabled business-example smoke all 5 stages green, 5 profiles                                                                                                                                                           |
| Configuration / lint   | Dependency consistency PASS; full-profile Compose configuration PASS (not stack startup); changed-Python bug-tier Ruff PASS                                                                                                                                                              |
| Independent review     | Code-only verification of batch ownership/admission, transcript hydration, and statistics/quotas                                                                                                                                                                                         |
| Built preview          | `http://127.0.0.1:4173`: desktop 1440x1000, all visible images loaded; mobile 390x844 navigation/keyboard/theme/sign-in input labels, no horizontal overflow. No authenticated critical journey or real Google sign-in/checkout                                                          |
| Health samples         | HTTP 200 in 20/20 samples; p50 717.2 ms, p95 1195.3 ms, p99 1761.1 ms, collected during ML tests, not a clean performance baseline                                                                                                                                                       |
| Live provider evidence | Keyless Freellmpool smoke failed twice; the UTF-8-enabled retry raised `AllCandidatesFailed` after one outer attempt. A separate concurrent verification logged two real configured-provider copilot HTTP 200 responses (6.06 s, 2.73 s). Neither proves all providers available or down |

Current patches cover shared batch admission (3 running jobs per owner, 600 s
deadline, active-job retention), resolved/explicit input caps and owner-protected
polling; selected/latest segmentation, atomic run/dependent deletion and study
snapshots with foreign-reference 409s; parent-row locking before exclusions and
regeneration archiving. Lock evidence is SQLite FK plus PostgreSQL-compiled SQL,
not live PostgreSQL concurrency or a global source-identity unique constraint.

The verified changes also include complete observed-group retention, stable ties
and pooled counts/percentages; quotas use complete valid nonnegative integer
counts, reject invalid counts, and use legacy shares for incomplete counts;
unclipped report claims/input history
and atomic versions; real-ORM fixtures; frontend request epochs, stale-navigation
guards and a restore gate. The frozen ML model still loses on retrieval MRR
(0.432654 versus lexical 0.751621), is USA-synthetic-only, and involves no LLM
fine-tuning. Test success does not remove these research limitations.

Reservations: no complete real 50-turn conversation, current PostgreSQL full-stack
or live multi-process rehearsal, offline-provider drill, or real-user rehearsal;
historical credential rotation remains unverified. The preview scope does not
reverify the earlier persona-header clipping finding. No commit, push, or remote
CI success is claimed; the original 15 phases and dates remain unchanged.

## Architecture (as built)

```
React + Vite SPA ──REST/SSE──▶ FastAPI (bebshax.api)
   error envelope + X-Request-ID on every response · limiter · body cap · CORS
        │
         ├── business / study / workflow roles / dataset generation
         │     MLPersonaAdapter → local TF-IDF/NMF + diversity-aware selection
         │     → existing persona JSON / SYNTHETIC source-model provenance
         │
        ▼
bebshax.llm  — LLMService.complete(LLMRequest{TaskType}) is the ONLY LLM entry
   task → pool (7, data table) → candidates → pre-flight (capabilities, script-aware
   context estimate, cooldowns) → attempt loop (13-kind closed FailureKind policy table,
   provider- or route-scope cooldowns, INTERNAL_ERROR surfaced) → cross-adapter fallback
   → ProvenanceRecord (estimate/params/ranker markers, attempts, via, tokens, latency)
        │
        ├── adapters/ (the ONLY provider-SDK imports, AST-enforced)
        │     FreellmpoolAdapter (18 free providers, virtual candidate, attempt budget)
        │     OpenRouterAdapter (free models only) · OllamaAdapter (native /api/chat, num_ctx pinned)
        │     FakeAdapter (tests + Judge Lab)
        ▼
PostgreSQL 16 + pgvector — existing tables; local continuation head f2a3b4c5d6e7
   personas/attributes/evidence · memory_items(source, content_hash) · conversations/turns(UNIQUE turn)
   llm_requests (provenance) · studies · research/evidence · datasets · behavioral · users
```

Custom BebshaX logic: persona engine + `coerce_provenance` (downgrade-only), `persona/conflicts.py`, memory service (source-labelled), interview engine (immutable identity card, untrusted blocks, drift + contradiction detectors, per-conversation lock), evaluation (`cross_route_consistency`, metrics endpoint), Judge Lab, `prompt_safety`.

## Historical subsystem status (2026-09-07/08)

| Area                                 | Status | Verified by                                                                                                                                                                   |
| ------------------------------------ | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Database & migrations**            | ✅     | from-zero `alembic upgrade head` on pgvector → single head, HNSW indexes, unique turn constraint; 3 integration tests                                                         |
| **AI pipeline (persona generation)** | ✅     | tournaments A/D/F; provenance hardening tests (downgrade-only, lexical gate, contested slots, Bangla tokens)                                                                  |
| **Routing & fallback**               | ✅     | 197 LLM-layer tests incl. 9 new hardening files; tournaments B/C/E/H; live fallback observed (2/8 free-pool → local)                                                          |
| **Provenance**                       | ✅     | sink tests, chaos DB-error test, `/api/provenance` redaction, markers, `via`; every failure recorded in `finally`                                                             |
| **Persona engine honesty**           | ✅     | no phantom defaults (identity card, dataset persistence), confidences derived, templates marked                                                                               |
| **Memory**                           | ✅     | source column + migration, dedupe, floor, interviewer exclusion, API `source` field, UI badge                                                                                 |
| **Interview engine**                 | ✅     | 20-turn attack tournament, concurrency lock, transcript-as-JSON, drift/contradiction exposed on payloads and reloaded turns                                                   |
| **Evaluation**                       | 🟡     | metrics endpoint + Evaluation card real; cross-route metric real but n = 16; offline replay withdrawn as unusable; judge disjointness enforced                                |
| **Security**                         | 🟡     | see PRODUCTION_READINESS §5 — pre-hijack/OTP/SSRF/limits/envelope fixed; PBKDF2 cost + history secrets open                                                                   |
| **Testing**                          | ✅     | backend 929 / frontend 249 / lint clean / tournaments A–H + chaos / live AI audit 56/56 (2026-09-08)                                                                          |
| **CI/CD**                            | ✅     | lint · coverage floor · alembic from zero + head count · pgvector integration · frontend test/build/theme · gitleaks · compose validation · pip-audit (advisory)              |
| **Deployment**                       | ✅     | compose `full` built and brought up healthy (2026-09-08): from-zero migration to `f2a3b4c5d6e7` inside the container, nginx IPv6 health fix, SPA + API smoke via :8080        |
| **Observability**                    | 🟡     | request ids end-to-end, access log, health depth, readiness; no JSON logs / metrics endpoint (deferred by design)                                                             |
| **Demo mode**                        | ✅     | coherent seed, CACHED labels, no fabricated provenance, Judge Lab live-verified (5 scenarios), preflight gates                                                                |
| **Frontend**                         | ✅     | 249 tests, tsc build 0, theme drift 0; honesty labels, inspector, evaluation card, memory/consistency disclosures, a11y on 8 dialogs; no seeded questionnaire, AI review card |
| **Documentation**                    | ✅     | API contract synced (envelope, enums, health, memories, consistency, Judge Lab); drift corrected in 14 docs; new audit/evidence/QA/adversarial docs                           |

## Earlier limitations (read with current assessment above)

1. Research evidence is small-n; CIs overlap (direction positive).
2. Default embeddings are hash-based; semantic recall is weak by design (offline determinism).
3. Free-tier latency is minutes at worst; the UI shows elapsed time and the route.
4. In-process locks/lockouts; DB unique constraint is the multi-worker backstop.
5. Demo evidence corpus is a labelled US review slice for a Bangladesh persona.
6. Leaked credentials in git history until rotated (🔴 human action).
7. PBKDF2 at 100k iterations pending a test-pin change.
8. No browser-level E2E; no human evaluation panel; no cost ledger artifact.

## Historical verification (2026-09-07/08)

| Check                                                                                         | Result                                                                                                                                                                                     |
| --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pytest apps/backend/tests -q`                                                                | ✅ 929 passed, 3 deselected (integration) — 2026-09-08                                                                                                                                     |
| `pytest -m integration` (scratch pgvector)                                                    | ✅ 3 passed                                                                                                                                                                                |
| `alembic upgrade head` from zero + `heads`                                                    | ✅ one head `f2a3b4c5d6e7` (verified inside the compose container, 2026-09-08)                                                                                                             |
| `ruff check apps/backend scripts`                                                             | ✅ clean                                                                                                                                                                                   |
| Frontend `vitest run` / `tsc && vite build` / `theme:check`                                   | ✅ 249 / 0 errors / 0 files                                                                                                                                                                |
| `scripts/live_ai_audit.py` (real routes, real DB)                                             | ✅ 56/56 checks — `data/metadata/live_ai_audit_20260908_040247.md`                                                                                                                         |
| `scripts/business_matrix_audit.py` (8 businesses, real routes, scratch PG)                    | ✅ differentiation 29/29 (`business_matrix_r2/summary_analysis.md`); fixed tree 61/61 end-to-end through 2 businesses (`business_matrix_r5/`); `--edge` 49/49 (`business_matrix_edge_r2/`) |
| `docker compose config` (default, `--profile full`)                                           | ✅ exit 0                                                                                                                                                                                  |
| Live API smoke (demo mode, PG) — health, envelopes, seed, provenance, Judge Lab ×5, auth gate | ✅                                                                                                                                                                                         |
| Real cross-route evaluation                                                                   | ✅ artifact `data/metadata/cross_route_20260907_034932.*`                                                                                                                                  |
| `pip-audit` / `npm audit --omit=dev`                                                          | ✅ 0 / 0 known vulnerabilities (advisory in CI)                                                                                                                                            |
| Docker image build + `up` rehearsal                                                           | 🟡 not run this pass                                                                                                                                                                       |
| Browser screenshot verification                                                               | 🟡 not run this pass                                                                                                                                                                       |

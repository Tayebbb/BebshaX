# Ship Readiness Report — BebshaX (2026-09-07; counts refreshed 2026-09-08)

> One page per subsystem: what is implemented, how it was verified in this pass, and its status. ✅ VERIFIED COMPLETE · 🟡 PARTIALLY COMPLETE · 🔴 BLOCKED · ⏸️ DEFERRED. Detailed checklists: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); audit narrative: [COMPETITION_AUDIT.md](COMPETITION_AUDIT.md) (re-audit 2026-09-08: 86/100, live AI audit 56/56); evidence classification: [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md); attack matrix: [ADVERSARIAL_TESTS.md](ADVERSARIAL_TESTS.md).

## Current authenticated E2E verification (2026-09-09)

**READY WITH RESERVATIONS: core journey exercised; regeneration remains provider-dependent.** Live-run evidence uses
a newly registered synthetic test account, real authentication, real Neon DB,
and real LLMs, not mocks. Report job `job_1d6f6ef7fea5` failed after the free-pool
attempt timed out at 151.05 seconds. The recorded full-context estimate was
35,593 tokens; OpenRouter was quota-limited and local 16,384-token routes were
ineligible. One normal UI retry succeeded in 128.8 seconds via
`llm7/codestral-latest`, without clearing quotas or truncating input. Report v1
`rep_e91cea576f964b32` persisted, the study became completed at step 5, and
refresh restored its summary and enabled export. The export action generated
1,434 characters of Markdown with summary and recommendations; the embedded
browser did not expose a download-completion event, so filesystem download
completion is not certified. The UI displayed failure, restored retry, and kept
export disabled before a report existed. This section supersedes
earlier readiness wording, not the historical phase records.

Final consistency check found v1's `metrics.total_personas=2` counted an unused
archived profile although the active study had one persona. Report selection
now excludes unused archived profiles while retaining any archived persona
referenced by that study's interviews or behavioral results. Five regression
cases failed before the fix; 31 report tests passed afterward, and independent
review approved the scope. An attempted v2 using the corrected code failed on
provider exhaustion after 156.7 seconds. V1 remained unchanged and readable;
its historical count was not rewritten. Live verification of the corrected
count in a newly generated report remains outstanding.

| Check | Result / scope |
| ----- | -------------- |
| Signup / study | Signup 201; automatic resend 500 during stale database authentication. Initial create saved before a post-commit refresh raised `InvalidPassword`/500. Pre-commit flush/refresh/serialization plus rollback now avoids that failure path; dashboard checks avoid duplicate creation. Fresh appendix study `study_cf3fad6503b34b40` returned 201. Real OTP delivery is unverified; development email was nonblocking. |
| Sign-in / report recovery | Synthetic-account wrong password 401, valid sign-in 200, resulting `/auth/me` 200. Report v1 recovered through a normal UI retry; summary, three findings and three recommendations persisted, scores remained null. Failed v2 preserved v1 and completed study status. |
| Main study / persona | `study_2dce227cb3544449`, title `E2e Verification: a Meal-Planning and Grocery-List App`. Explicit ages 25-45 previously yielded age 71; description/target age parsing now intersects structured bounds and rejects invalid ranges with 422. Regenerated Cecelia, age 25, occupation `cook`, persona `per_af0775501759`, saved/read back; generation returned in 4.418 s. |
| Cache / provenance | Live/mock cache namespaces and user-filtered stored metadata; dashboard recents owner-scoped with explicit public demos. Step 1/2 badges distinguish ML sources from observed evidence. Reported regressions: cache 15 new plus 32 neighboring passes; labels 22 plus evidence 4; age 122 focused passes including 42 new. These counts overlap broader suites and are not additive. |
| Discovery | CKAN geography up to 256 characters exceeded a varchar(128) field. Invalid metadata now retains raw values and field-length diagnostics with `import_failed`; valid batch candidates continue. Manual import rejects `metadata_errors` with 422 `invalid_metadata` before download. |
| Interview / memory | Two blocking HTTP 200 replies: 22.337 s / 22.185 s, `ollama/llama3.2:3b`; Cecelia's name/age and Sunday planning/Wednesday groceries stayed consistent; 1 then 2 recalled memories. Third SSE HTTP 200: 24.371 s; six unique persisted turn numbers 1-6; canonical reply exactly matched the UI. Detail reads 1.959 s / 2.532 s, versus earlier LLM-on-read 35-60 s. GET now reads saved suggestions without LLM calls; writes bound optional suggestions to 3 s before atomic persistence. |
| Completion / mobile | Completion and synthesis succeeded; actual UI showed read-only transcript, summary, and insight. Only the interview actions row wrap changed. After cold reload, main left edge was 0; at viewport 390, context toggle right edge 366 and verification dismiss right edge 163, no overflow. JavaScript resize artifacts were not reproduced after cold reload; this is not an entire accessibility audit. |
| Appendix / negative paths | CSV upload 201, 6 rows: `weekly_spend` 10,20,30,40,50,60; mean/median 35; two three-person categories 50% each. New study plus upload: 4,218 ms. Duplicate-header CSV rejected with 400. Empty create 400; unauthenticated study read 404 and transcript read 403. |
| Current checks | Frontend 355 passed / 44 files, 61.29 s; TypeScript/Vite PASS, 4.94 s; theme 0; dashboard chunk 690.39 KB warning. Combined affected backend 210 passed, 52.08 s, **not a full backend rerun**. Changed-backend Ruff PASS; no editor errors reported. Independent age/cache/study atomicity/discovery/manual-import/interview suggestion read-write reviews reported no remaining P1/P2 findings. |

The earlier 1,639-test backend run and coverage are historical, not rerun evidence.
Transient API pool 5+5 starvation during concurrent research recovered; no root
fix is claimed. Provider-specific 404/402/429 responses do not establish global
route failure. Interview routines are hypothetical model output, not observed
evidence or population/hallucination validation. ML weights remain frozen; no
LLM fine-tuning, new dependencies, schema/weights/environment changes, commits,
or pushes in this pass. Payment, Google sign-in, 50-turn conversations, full
Compose, cross-process concurrency, and entire accessibility coverage were not
tested. The core journey reached a saved report, but long-context free-provider
reliability and live v2 cohort-count verification remain reservations.

## Earlier ML maintenance status (2026-09-09)

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

## Earlier Hardening Verification (2026-09-09)

**Historical verdict: READY WITH RESERVATIONS.** The results below were executed
locally during the earlier hardening pass. They are not the current E2E verdict;
the authenticated run above remains **PENDING** full report.

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

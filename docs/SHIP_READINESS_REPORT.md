# Ship Readiness Report — BebshaX (2026-09-07; counts refreshed 2026-09-08)

> One page per subsystem: what is implemented, how it was verified in this pass, and its status. ✅ VERIFIED COMPLETE · 🟡 PARTIALLY COMPLETE · 🔴 BLOCKED · ⏸️ DEFERRED. Detailed checklists: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md); audit narrative: [COMPETITION_AUDIT.md](COMPETITION_AUDIT.md) (re-audit 2026-09-08: 86/100, live AI audit 56/56); evidence classification: [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md); attack matrix: [ADVERSARIAL_TESTS.md](ADVERSARIAL_TESTS.md).

## Architecture (as built)

```
React + Vite SPA ──REST/SSE──▶ FastAPI (bebshax.api)
   error envelope + X-Request-ID on every response · limiter · body cap · CORS
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
PostgreSQL 16 + pgvector — 33 tables, alembic head e1f2a3b4c5d6
   personas/attributes/evidence · memory_items(source, content_hash) · conversations/turns(UNIQUE turn)
   llm_requests (provenance) · studies · research/evidence · datasets · behavioral · users
```

Custom BebshaX logic: persona engine + `coerce_provenance` (downgrade-only), `persona/conflicts.py`, memory service (source-labelled), interview engine (immutable identity card, untrusted blocks, drift + contradiction detectors, per-conversation lock), evaluation (`cross_route_consistency`, metrics endpoint), Judge Lab, `prompt_safety`.

## Subsystem status

| Area                                 | Status | Verified by                                                                                                                                                      |
| ------------------------------------ | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Database & migrations**            | ✅     | from-zero `alembic upgrade head` on pgvector → single head, HNSW indexes, unique turn constraint; 3 integration tests                                            |
| **AI pipeline (persona generation)** | ✅     | tournaments A/D/F; provenance hardening tests (downgrade-only, lexical gate, contested slots, Bangla tokens)                                                     |
| **Routing & fallback**               | ✅     | 197 LLM-layer tests incl. 9 new hardening files; tournaments B/C/E/H; live fallback observed (2/8 free-pool → local)                                             |
| **Provenance**                       | ✅     | sink tests, chaos DB-error test, `/api/provenance` redaction, markers, `via`; every failure recorded in `finally`                                                |
| **Persona engine honesty**           | ✅     | no phantom defaults (identity card, dataset persistence), confidences derived, templates marked                                                                  |
| **Memory**                           | ✅     | source column + migration, dedupe, floor, interviewer exclusion, API `source` field, UI badge                                                                    |
| **Interview engine**                 | ✅     | 20-turn attack tournament, concurrency lock, transcript-as-JSON, drift/contradiction exposed on payloads and reloaded turns                                      |
| **Evaluation**                       | 🟡     | metrics endpoint + Evaluation card real; cross-route metric real but n = 16; offline replay withdrawn as unusable; judge disjointness enforced                   |
| **Security**                         | 🟡     | see PRODUCTION_READINESS §5 — pre-hijack/OTP/SSRF/limits/envelope fixed; PBKDF2 cost + history secrets open                                                      |
| **Testing**                          | ✅     | backend 929 / frontend 249 / lint clean / tournaments A–H + chaos / live AI audit 56/56 (2026-09-08)                                                           |
| **CI/CD**                            | ✅     | lint · coverage floor · alembic from zero + head count · pgvector integration · frontend test/build/theme · gitleaks · compose validation · pip-audit (advisory) |
| **Deployment**                       | ✅     | compose `full` built and brought up healthy (2026-09-08): from-zero migration to `f2a3b4c5d6e7` inside the container, nginx IPv6 health fix, SPA + API smoke via :8080 |
| **Observability**                    | 🟡     | request ids end-to-end, access log, health depth, readiness; no JSON logs / metrics endpoint (deferred by design)                                                |
| **Demo mode**                        | ✅     | coherent seed, CACHED labels, no fabricated provenance, Judge Lab live-verified (5 scenarios), preflight gates                                                   |
| **Frontend**                         | ✅     | 249 tests, tsc build 0, theme drift 0; honesty labels, inspector, evaluation card, memory/consistency disclosures, a11y on 8 dialogs; no seeded questionnaire, AI review card |
| **Documentation**                    | ✅     | API contract synced (envelope, enums, health, memories, consistency, Judge Lab); drift corrected in 14 docs; new audit/evidence/QA/adversarial docs              |

## Known limitations (stated, not hidden)

1. Research evidence is small-n; CIs overlap (direction positive).
2. Default embeddings are hash-based; semantic recall is weak by design (offline determinism).
3. Free-tier latency is minutes at worst; the UI shows elapsed time and the route.
4. In-process locks/lockouts; DB unique constraint is the multi-worker backstop.
5. Demo evidence corpus is a labelled US review slice for a Bangladesh persona.
6. Leaked credentials in git history until rotated (🔴 human action).
7. PBKDF2 at 100k iterations pending a test-pin change.
8. No browser-level E2E; no human evaluation panel; no cost ledger artifact.

## Final verification (this pass)

| Check                                                                                         | Result                                                                             |
| --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `pytest apps/backend/tests -q`                                                                | ✅ 929 passed, 3 deselected (integration) — 2026-09-08 |
| `pytest -m integration` (scratch pgvector)                                                    | ✅ 3 passed                                                                        |
| `alembic upgrade head` from zero + `heads`                                                    | ✅ one head `f2a3b4c5d6e7` (verified inside the compose container, 2026-09-08)      |
| `ruff check apps/backend scripts`                                                             | ✅ clean                                                                           |
| Frontend `vitest run` / `tsc && vite build` / `theme:check`                                   | ✅ 249 / 0 errors / 0 files                                                        |
| `scripts/live_ai_audit.py` (real routes, real DB)                                            | ✅ 56/56 checks — `data/metadata/live_ai_audit_20260908_040247.md`                 |
| `docker compose config` (default, `--profile full`)                                           | ✅ exit 0                                                                          |
| Live API smoke (demo mode, PG) — health, envelopes, seed, provenance, Judge Lab ×5, auth gate | ✅                                                                                 |
| Real cross-route evaluation                                                                   | ✅ artifact `data/metadata/cross_route_20260907_034932.*`                          |
| `pip-audit` / `npm audit --omit=dev`                                                          | ✅ 0 / 0 known vulnerabilities (advisory in CI)                                    |
| Docker image build + `up` rehearsal                                                           | 🟡 not run this pass                                                               |
| Browser screenshot verification                                                               | 🟡 not run this pass                                                               |

# Session Handoff: BebshaX Modernization

**Handle:** `BEBSHAX-MODERNIZATION-2026-09-10`
**Date:** 2026-09-10. **State:** implementation in progress, not released.
**Git checkpoint:** `main` at `73eab0d`, tracking `origin/main` without divergence at inspection; 249 tracked files changed (+17,402/-7,544), plus new untracked files. Counts exclude untracked additions and may change during other sessions. No Git writes in this handoff.
**Goal:** finish the approved 82-item modernization and latency/quality contract using disjoint implementation agents and independent reviewers.

## Read First

- [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md): implementation is already approved. Do not restart planning or request blanket approval again.
- [POST_PRESENTATION_ROADMAP.md](POST_PRESENTATION_ROADMAP.md): full requirements and acceptance matrix; old plan-only wording is superseded by the owner's explicit implementation request.
- [MODERNIZATION_EXECUTION.md](MODERNIZATION_EXECUTION.md): assignment table and empty completed-evidence section are stale, not proof that the code is absent.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), [DATABASE_MIGRATION.md](DATABASE_MIGRATION.md), [DEPENDENCY_REVIEWS.md](DEPENDENCY_REVIEWS.md): detailed current workstream evidence. Earlier chat progress and empty code blocks are not tool receipts.

## State

- **Verified in this handoff pass:** context approval, stale ledger, Git state, and current factory/policy wiring. The actual factory is `build_embedding_backend(..., provider_config=..., processing_policy=...)`; [main.py](../apps/backend/bebshax/main.py) passes the shared default-deny policy to the router and remote embeddings. Those former mismatches are fixed. No application tests were rerun.
- **Data work, previously reported:** private memory attribution/backfill, typed dataset lineage, immutable persona versions and scoped source reservations. Source-ledger revision `e7a9c1d3f205` follows `d4e6f8a0b219`; `c6f8a2d4e901` was explicitly confirmed never applied before its correction. Never generalize that permission to other migrations. See the latest data log entry for 268 scoped passes, overlapping 77-test ledger run, 13 dataset lifecycle cases and the fresh-process ML import guard; these are not a new combined backend pass.
- **Frontend/tooling, saved receipts inspected:** baseline at 2026-09-10 06:28:11 UTC is **472/473, one failure, no skips, exit 1**, with 5/7 runtime assertions passing. The failing signed-in hero CTA test in [LandingPage.test.tsx](../apps/frontend/tests/LandingPage.test.tsx) waits for console content during lazy-dashboard Suspense; timing/contention is an unproven hypothesis. Saved build/type/theme/graph/mock-browser checks pass on OLD tooling. Evidence: [baseline-result.json](../apps/frontend/.tsupgrader/runtime-validation/baseline-result.json), [frontend-tests.json](../apps/frontend/.tsupgrader/runtime-validation/frontend-tests.json), [eval-plan.json](../apps/frontend/.tsupgrader/runtime-validation/eval-plan.json). No tests rerun here.
- **ML candidate, documented not promoted:** schema-3 lexical bundle at `data/processed/ml_persona/experiment-20260909-w1-w7-1823/model`; [MODEL_CARD.md](../ml_persona/MODEL_CARD.md) keeps NMF as the documented default and MiniLM untested. Do not infer the configured serving bundle without checking safely; preserve the frozen baseline and do not retune on the inspected test set.
- **In progress:** combined startup, jobs, tenant/auth, domain and ML integration; full-suite reconciliation; database concurrency/migration rehearsal; active documentation sync; latency measurements and release checks. Existing source changes must be preserved and verified, not overwritten or counted complete from their presence alone.
- **Not established:** production deployment/readiness, real PostgreSQL multi-process correctness, full authenticated live journeys, actual page/AI latency budgets, backup restore, fresh human business-relevance model evaluation, provider policy/capacity, real email/OAuth and historical credential rotation.

## Key Decisions

- Keep the modular monolith: React/Vite, FastAPI, PostgreSQL/pgvector, CPU persona package. Remove local AND cloud Ollama; use Freellmpool primary and independent OpenRouter secondary, excluding nested OpenRouter routes. Hash embeddings are not Ollama.
- Preserve full identity/history/memory/evidence, output limits, validation, tenant boundaries and durable provenance. Never weaken AI output, conceal fallback, reset quotas or treat low answer quality as infrastructure failure. Private data is not training material; no LLM fine-tuning.
- Default-deny remote processing is intentional; pass reviewed configuration consistently to routing and embeddings, never unblock tests by enabling all destinations. Keep billing disabled until its complete gates pass.
- Proposed p95 budgets: feedback 100 ms, valid cached page 200 ms, fresh bounded non-AI view 1 second, server CRUD 300 ms. First genuine AI text and validated persisted completion are separate; skeletons and fast errors do not meet content-readiness targets.
- Preserve existing data, artifacts, secrets and all uncommitted work. No commit, branch, push, production migration, secret rotation or deployment is implied by the implementation authorization.

## Blockers And Dead Ends

- **Tooling upgrade did not happen.** Actual selected versions remain Vite 5.4.21, Vitest 2.1.9, plugin-react 4.7.0, TypeScript 5.9.3. Approved targets are Vite 7.3.6, Vitest 4.1.11 and plugin-react 5.2.0, without React/TypeScript major changes. The official MCP accepts package names only; `name@version` returned success-like text but performed no upgrade. Do not repeat it or silently choose Vite 8/Vitest 5/plugin 6. Read the official upgrade skill and the full dependency review before deciding the bounded method.
- JSTS session `24dc0bd9-5f33-49c1-8d60-8e050e9e4dca` already called its summary tool once; do not repeat that terminal workflow action. Its parser once falsely reported PASS with exit 1/collection failures: require exit status AND full JSON test counts. Required DOM Testing Library peer 10.4.1 was reviewed and installed; preserve it.
- **Two concrete parent-lifecycle gaps:** [main.py](../apps/backend/bebshax/main.py#L369) marks readiness without `initialize_jobs(app)`/`startup_jobs(app)`, so boot recovery and periodic lease-expiry maintenance never start. Jobs already register `JobRuntime.aclose()` lazily: do not report total lack of shutdown wiring. If `RuntimeTaskRegistry.aclose()` raises for cancellation-resistant tasks, the surrounding exit stack still disposes dependencies. Add composed-startup/teardown regressions before changing that failure path; see [jobs-modernization.md](jobs-modernization.md).
- Root npm workspace/lock is authoritative; do not run nested competing installs. Isolated Playwright/runtime files under the frontend `.tsupgrader` are not application dependencies. The upgrade-only mock server on 5217 was reported stopped; recheck current listeners, not old terminal IDs.
- Windows terminal output can mix with another agent's commands. Serialize heavy checks, use unique output receipts with actual exit codes, `mode=sync`, no polling/sleeps, no concurrent dependency installs or overlapping full suites. Use E: scratch space when C: is full. `_env_file=None` does not remove process environment overrides; earlier backend directory-test failures were verifier-induced.

## Next Session: Start Here

1. Read the contract and current Git status; preserve the dirty worktree. Reconcile this handoff with current files before editing; do not rerun the full architecture audit.
2. Assign non-overlapping read/repair scopes: routing/startup; auth/privacy; data/migrations; jobs/domain; frontend; ML; operations. One integrator owns `main.py`, shared settings/contracts and migration-head coordination. Reviewers remain read-only.
3. Reproduce the frontend failure from the root with process-local `BEBSHAX_FRONTEND_VERIFY=1`: `npm run test:frontend -- tests/LandingPage.test.tsx`. Inspect lazy readiness without weakening the assertion. The [runtime unit wrapper](../apps/frontend/.tsupgrader/runtime-validation/run-unit-tests.mjs) sets isolation itself; root scripts do not. Resolve the bounded upgrade capability/method without ignoring version constraints; then use `npm run test:frontend`, `npm run build`, `npm run theme:check` separately with exit receipts.
4. Fix the two parent-lifecycle gaps above, starting in [test_runtime_modernization_lifespan.py](../apps/backend/tests/test_runtime_modernization_lifespan.py): `.venv/Scripts/python.exe -B -m pytest apps/backend/tests/test_runtime_modernization_lifespan.py -q --no-cov -p no:cacheprovider`. Neighboring [job recovery](../apps/backend/tests/jobs/test_job_runtime_recovery.py) and [job memory](../apps/backend/tests/jobs/test_job_memory_contract.py) tests cover helper behavior, not composed app shutdown. Use isolated fixtures, add failing regression first, run focused validation immediately, then independent review. Do not redo the repaired factory-policy forwarding.
5. Reconcile M2-M9 migration/domain coverage, then run one corrected combined backend suite, ML suite, frontend tests/build/theme and dependency checks. Use disposable PostgreSQL for schema/constraint/concurrency tests, never the configured user database. Follow with isolated proxy/browser/latency/recovery gates and update the execution ledger from receipts.

## Verification Snapshot

**This pass:** source/document inspection only; no fresh application build, test, latency or live-service verdict. **Latest reported frontend:** 472 passed / 1 failed; build PASS on old tooling. **Backend/ML:** scoped workstream results only, combined current gate outstanding. **Release:** blocked; unsupported success claims must not carry forward.

# Modernization Execution

Owner authorization: 2026-09-09, end-to-end implementation of
[POST_PRESENTATION_ROADMAP.md](POST_PRESENTATION_ROADMAP.md), including its
latency and AI-quality contract, using multi-agent implementation and review.

Status: **IN PROGRESS; NOT RELEASED.** Existing work, data, credentials and
historical evidence are preserved. No commit, push or production deployment is
implied by implementation authorization. Database verification uses disposable
environments, not the configured user database.

## Resume Checkpoint (2026-09-10)

Handle: `BEBSHAX-MODERNIZATION-2026-09-10`.
Read [MODERNIZATION_HANDOFF.md](MODERNIZATION_HANDOFF.md) to continue.
Implementation is already approved. The assignment table below and the original
completed-evidence placeholder are historical coordination state, not current
implementation or test results. Do not repeat the audit or assume an old agent
is still working from an Assigned label.

The handoff verifies current policy/factory forwarding and identifies two
remaining composed job-lifecycle gaps. Saved frontend receipts show 472/473
tests, one failure, on the old tooling; the bounded upgrade did not apply.
Data-work results are recorded in the latest implementation log. No application
tests were rerun to create this handoff; a current combined gate is outstanding.
Preserve the substantial uncommitted worktree and use isolated checks before
resuming implementation. No production-readiness, commit or deployment claim.

## Active Batches

| Batch | Scope                                                                         | Status   | Verification                                                                |
| ----- | ----------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------- |
| 1A    | Interview cancellation, stale responses and synthesis locking                 | Assigned | Existing eight failing frontend regressions are the first gate.             |
| 1B    | Verified DB TLS, vector comparator, migration parity and test isolation       | Assigned | Focused offline regressions, then isolated PostgreSQL.                      |
| 1C    | Upload resource bounds and error redaction                                    | Assigned | Adversarial bounded-input and sensitive-sentinel regressions.               |
| 1D    | Remote-only provider adapters and governed routing                            | Assigned | Fake-provider and injected-transport tests; no local/cloud Ollama routes.   |
| 1E    | Genuine lexical ML baseline and current-serving safeguards                    | Assigned | No-NMF lexical regression, artifact compatibility and full-record fidelity. |
| 2     | Tenant/authentication, durable execution and canonical lineage                | Pending  | Scoped security/transaction/recovery checks before integration.             |
| 3     | Every-page latency, client contracts, truthful exports and dependency release | Pending  | Production build, route-level browser measurements, no quality regressions. |
| 4     | Independent integration, security, ML and operations verification             | Pending  | Full suites, isolated PG, browser/proxy and recovery evidence.              |

## Execution Rules

- One editor owns each shared file; independent agents own disjoint scopes.
- Each change starts from a concrete failure or testable local hypothesis,
  then a failing regression, minimal repair and immediate focused validation.
- Reviewers check wiring and behavior, not just the presence of code.
- Required checks run without real provider calls unless explicitly identified
  as synthetic, policy-approved live canaries. No quota resets or limit evasion.
- No context truncation, hidden weak-model fallback, fabricated output, private
  training data, or LLM fine-tuning is permitted to satisfy performance targets.
- Preserve the frozen model and old artifacts while evaluating challengers;
  do not invent human relevance labels or claim a new model won without data.
- Record exact tests/results and residual risks below; pending work is not done.

## Baseline

The roadmap records 1,723 backend passes plus two runner-induced directory
test failures, 347 frontend passes plus eight real interview-workspace
failures, and 298 passing ML JUnit outcomes with incomplete launcher evidence.
This baseline is not a current full-suite pass or production certification.

## External Release Gates

Real credential rotation, approved processor terms, actual OAuth/email delivery,
fresh independently judged business-relevance data, deployment credentials,
contractual hosting budgets and target-production backup restoration cannot be
inferred from source changes. Unexercised capabilities remain explicitly gated
or limited. Free inference is not an uptime guarantee; page responsiveness
cannot be claimed from skeleton rendering or faster failure alone.

## Completed Evidence

Implementation results will be recorded here as each batch passes its checks.

### 2026-09-12/13 — Live end-to-end sweep and guardrails (disposable stack: SQLite + demo seed, real free-tier LLM routes)

Every view and primary journey was driven in a real browser against a
disposable backend (`.tmp/e2e/stack.ps1`; never the configured cloud
database). Each defect below was fixed with a regression test in the same
change; live re-verification followed each fix.

- **P0 — every LLM call failed in ~45 ms (503 "all routes failed"):**
  default-deny remote-processing policy + packaged provider catalog with no
  context/JSON metadata + provider keys that never reached `os.environ`.
  Fixed via a derived default policy (`factory.default_processing_policy`,
  `main.effective_processing_policy`, exposed on `/api/health`),
  `config.export_provider_credentials`, verified `providers.toml` metadata,
  and an honest 503 detail when zero attempts were made.
- **Session robustness:** bearer sessions expired after 15 min (refresh
  credential now tab-persisted, 401→refresh→replay once, proactive refresh);
  a same-account sign-in in another tab signed out the first tab; another
  tab *losing* its session signed out every tab (now each tab re-verifies
  its own tab-scoped credentials; only a deliberate sign-out broadcasts on
  `bebshax_signout_broadcast`); a session-epoch abort mid-rotation could
  discard a committed refresh and later trip the server's strict reuse
  detection (rotation now uses a non-abortable fetch and retires an
  unwanted fresh generation). Server-side reuse detection is unchanged.
- **Study workflow:** stale summaries (now derived from real state), prompt
  overwritten by chat transcript, goal-card fields never persisted, queued
  PATCH racing generation (409 `write_conflict` + safe rebase), batch
  interviews lost on reload (auto-resume + status hydration), report score
  formatting, "after N chats persona generation dies" (ML research context
  is now chunked, never truncated; refusal reason surfaced).
- **Interviews:** an interview closed without synthesis crashed the decoder;
  the honest contract (`summary: null`, `source: "unavailable"`) is now
  decoded and rendered with a retry (workspace, list badge "Synthesis
  pending"); turn-capped interviews read "Ready to synthesize".
- **Evidence Laboratory:** a 202-accepted research run was treated as
  complete (stale QUEUED forever); it is now polled to a terminal state with
  step labels and the recorded failure reason.
- **Audience Segments:** dataset upload was impossible from the UI and the
  client sent `Content-Type: application/json` with `FormData` (422
  "Malformed multipart"); an upload panel (CSV/JSON ≤ 25 MB) now feeds
  readiness → segmentation (live: 24 rows → 3 data-backed segments).
- **Shell:** study scope survives workspace-level views; sidebar recent list
  follows create/delete (`bebshax:studies-changed`); developer-only
  diagnostics render a notice, not an outage; behavioral-test wizard requires
  its scenario fields and no longer prefills an unrelated product.
- **Auth:** local signup dead-ended without a mail transport; in
  `development` the backend now prints the one-time code (never the
  recipient). Verified: signup → code → verified → signed in; wrong code
  rejected; second-user isolation (all foreign study routes 403/404, no
  leaks); logout revokes server-side and cleans storage.
- **Gate (2026-09-13):** frontend typecheck 0 / build 0 / theme 0 /
  Vitest **1039 passed, 0 failed, 64 files**; backend targeted suites green
  (email/verification 30, session 36, evidence 16, interviews 74); full
  backend suite **2938 passed, 0 failed, 1 skipped, coverage 85.96%**
  (receipt `full-backend-2.{log,exit}`). Environment note: the integrated browser tab is
  occluded (`document.hidden = true`), so `pauseWhenHidden` polling and
  keyboard events were exercised via DOM dispatch; the mobile drawer relies
  on its unit tests.

### 2026-09-12 — Backend regression closure (receipts in `.tmp/resume-20260910/receipts/`)

- **Startup lifecycle:** `initialize_jobs(app)` now runs before `core_ready` in
  `main.py`; boot recovery and periodic lease expiry start with the app
  (`tests/test_runtime_modernization_lifespan.py`, `tests/jobs/`).
- **Shared-app cache staleness (root cause of the "passes alone, fails in
  sequence" cluster):** two `app.state` caches stayed bound to a superseded
  `db_sessionmaker`. `api/jobs.py::job_runtime()` now rebuilds the
  `SQLJobStore`/`JobRuntime` (cancelling the stale runtime's recovery and job
  tasks) and `api/datasets.py::_get_dataset_service()` rebuilds the
  `DatasetService` when its factory differs. The stale service fenced job
  leases against the wrong database → `LeaseLost` → upload 400.
- **Contract alignments:** persona generation checks owner before engine
  availability (503 when unwired); batch interview jobs classify
  post-deadline cancellation as `timed_out`; `/api/evaluation/metrics` is
  developer-only, so `local_serve_rate` is `None` for other callers.
- **Receipts:** 36-module retest 427 passed / 2 failed (before the
  `DatasetService` fix) → IDOR sequence + `tests/jobs` + `tests/datasets`
  332 passed, exit 0; `ml_persona/tests` 379 passed, exit 0; full backend
  suite: see `full-backend.log` / `full-backend-junit.xml` (result recorded in
  IMPLEMENTATION_PLAN.md).
- **SEC-02 check:** `POST /api/audiences` requires `get_current_user`; anonymous
  rejection covered by `tests/api/test_security_regressions.py`.
- **Frontend:** last owned green run 513/513 with typecheck/build/theme exit 0
  (Vite 8.2.2 / Vitest 5.0.0). A concurrent session was editing
  `apps/frontend` tests during this pass; its in-flight state (typecheck
  exit 2, 3 failing tests) is not part of this evidence and must be re-gated.

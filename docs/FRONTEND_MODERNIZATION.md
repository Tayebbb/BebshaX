# Frontend Modernization

## Current Integration Record (2026-09-10)

This record supersedes the historical verification notes below. This workstream
owns only `apps/frontend/src/**`, `apps/frontend/tests/**`, and this document.
Existing uncommitted frontend work was retained. No manifests, locks, Vite or
TypeScript configuration, backend code, root documents, execution ledger, git
history, or remote design artifacts were changed. No dependencies were installed,
and no application server was started. The existing tokens, icons, layout, and
dialog behavior were reused.

### Implemented And Preserved

| Roadmap | Current frontend behavior |
| --- | --- |
| FE-01 / auth | Local verification and password-reset payloads match the inspected auth API/service. URL bearer login remains removed. Live profile failures no longer authorize cached identities. Cookie profiles are validated; cookie bootstrap and refresh requests coalesce only within their session epoch. Expired bearer recovery/logout use the server refresh credential. Cross-tab invalidation clears old tab credentials without erasing another tab's shared identity. |
| FE-02 | Existing owner/study-scoped library data, independent primary-persona loading, and A-B-A mutation guards retained. |
| FE-03 | Existing pathname/search ownership, exact aliases, comparison `run_ids`, explicit step 1, Back/Forward, and safe auth-return navigation retained and exercised by the suite. |
| FE-04 / FE-10 | Caller/session cancellation and synthesis locks retained. Detail, reply, synthesis, and SSE now have bounded transport budgets. Received buffered replies render immediately, without a word-reveal timer. The workspace consumes the validated flat DTO, rejects unknown failure labels, and does not call a database 503 a model-capacity failure. |
| FE-05 | Existing serialized revision-aware writes and draft recovery retained. A stale PATCH acknowledgement is rejected before it enters saved storage. Missing/unavailable studies never expose an editable phantom workflow. Initial prompts wait for saved history. A failed transcript restore preserves its handle and requires retry before new turns. |
| FE-06 / FE-07 | Routing/provenance and evidence summary/claims/sources/history settle independently. Optional failure cannot hide successful primary reads. Unknown measurements remain unknown. Evidence reads are scope-cancellable and bounded. Existing segmentation, behavioral, report, and metrics ownership/error behavior retained. |
| FE-08 | Existing serial polling, overall/idle bounds, finite transient retries, auth-failure termination, and accepted-job GET resume retained. Stopping observation never claims server cancellation. |
| FE-09 | Existing mobile navigation inert/focus handling retained. The interview's separate mobile context rail is now inert while closed and focus-managed while open. Evidence tabs support arrows/Home/End and linked panels. Existing modal, filter, and keyboard interview-card tests retained. |
| FE-11 | No active component Ollama/local-cloud fallback or always-online runtime claims were found in the final scoped scan. Routing labels use actual `streaming_mode`, observed availability, and nullable model counts. No provider picker or paid-entitlement shortcut was introduced. Historical provenance and explicit sample-data labeling remain intact. |
| FE-12 | Shared formula/quote-safe CSV and complete stored-report Markdown retained, including synthetic status, version, limitations, citations, source identity, provenance, and unknown future fields. |
| FE-13 | Existing lazy feature boundaries, two-at-a-time intent prefetch, and owner-keyed coalescing retained. Coalesced study readers now receive independent deep snapshots. Opt-in timing includes cold navigation, navigation/operation IDs, and separate content/empty/error/abandoned counters. Generation placeholders and transcript restoration do not count as primary content. |

The implementation changes were driven by observed failing tests. Two old auth
expectations that authorized cached users after failed server verification were
updated to require errors while preserving retry credentials. Workflow tests now
create their study fixtures and await hydration instead of relying on editing a
nonexistent record. The old transcript-failure expectation that discarded history
was replaced by retained-handle/retry assertions. No tests were skipped or removed.

### Verification

| Final check | Observed result |
| --- | --- |
| Full frontend suite | 473 passed, 0 failed, 0 skipped, 54 files; exit 0; 83.310 seconds. |
| Added regression cases | 42 cases beyond the retained 431-test worktree baseline; existing assertions were preserved except the explicitly documented contract corrections. |
| TypeScript | `tsc --noEmit --project apps/frontend/tsconfig.json` passed, exit 0, no compiler output. |
| Editor diagnostics | No errors in touched source, tests, or this document. |
| Documentation links | Checked local Markdown link targets; no missing targets. |
| Build and browser | Not run by this owner; reserved for ops/parent integration. |

The final full-suite artifact is
`apps/frontend/.tmp/test-1789016766809-32ec256a.json`, with the verifier summary in
`apps/frontend/.tmp/last-test.json`. These are ignored, local execution evidence.
Temporary result files created under `apps/frontend/tests/` were removed.

Earlier integration run: 460 passed, 7 failed, 0 skipped, 54 files; all seven
failures were missing-study/pre-hydration fixtures in CopilotHonesty and Dashboard.
Those two files subsequently passed all 16 tests. Coverage is not configured in
the installed frontend test setup; no coverage percentage or delta is claimed.
No Vite build was run by this owner because builds/configuration belong to ops.

All test invocations use `--maxWorkers=1 --no-file-parallelism`; Vitest 2 also
receives `--minWorkers=1`. A dedicated verification worker was used because the
shared sync terminal intermittently returned other workstreams' output. Empty,
zero-test, and interrupted runs were not counted as successful verification.

### Timing API And Counters

Implementation and exports: [routeTiming.ts](../apps/frontend/src/performance/routeTiming.ts).

- Before page bootstrap, set `window.__bebshaxMeasureRoutes = true` (for example
  with Playwright `addInitScript`). The first measurement begins at navigation
  time zero, including module transfer and startup. Instrumentation defaults off.
- At runtime, `window.__bebshaxTiming.enable(true)` enables warm measurements;
  `read()` returns copied samples; `counters()` returns copied route counters;
  `clear()` clears samples/counters and the active visit. Enable after mount is
  supported, but its duration is not a cold-load measurement.
- Named exports: `setRouteTimingEnabled`, `startRouteTiming`, `useRouteReady`,
  `beginOperationTiming`, `readRouteTimings`, `readRouteTimingCounters`, and
  `clearRouteTimings`. Optional `startRouteTiming(path, startedAtMs)` is for an
  explicitly captured navigation start, not a synthetic performance target.
- Samples carry `navigationId`, optional `operationId`, `route`, `stage`,
  `durationMs`, `outcome`, and `mode`. At most 200 samples are retained locally.
  No resource IDs, query strings, prompts, credentials, or telemetry uploads are
  included. IDs are monotonic within the loaded module and are not reset by clear.
- Route groups are `landing`, `auth`, `new-study`, `dashboard`, `personas`,
  `router`, `evidence`, `segmentation`, `interviews`, `interview-workspace`,
  `behavioral-tests`, `behavioral-test-detail`, `behavioral-compare`, and
  `workflow-1` through `workflow-5` (`workflow-saved` for an omitted URL step).
- Each visit increments `started`; the first settled primary state increments
  exactly one of `content`, `empty`, or `error`. Leaving an unsettled visit
  increments `abandoned`. A currently pending visit has no terminal count.
  `content + empty + error + abandoned` must never exceed `started`.
- Primary readiness records after two animation frames and cancels pending marks
  when readiness changes. This observes a render opportunity, not a browser
  screenshot assertion. Optional metrics do not block the primary list; spinner
  visibility alone is not readiness. A sign-in boundary at a protected URL is an
  error outcome for that visit, never successful private content. Each URL visit
  records its first settled outcome only.
- Operation stages are `ai-first-text`, `canonical-response`, and
  `saved-completion`. AI-first-text means received application text, not proven
  provider-native TTFT; reported buffered/native capability remains separate.
  Canonical response is not durable save. Report readback owns saved-completion.
  Late operation marks from an abandoned navigation are ignored.

### Parent Integration Gates

- Verify real cookie delivery, credentialed CORS, HTTPS, CSRF, `/auth/session`
  origin policy, access expiry, refresh rotation, revocation, cross-tab behavior,
  local mail/OTP recovery, and federated Google return against the final backend.
  JavaScript cannot manufacture the browser-controlled `Origin` header.
- Confirm canonical study `revision`, `If-Match`/`expected_revision`, conflict
  envelopes, accepted-job status/ownership/resume, report ID/version readback,
  and full transcript/provenance persistence with the deployed API/database.
- Routing diagnostics must return their current nullable counts, actual
  `streaming_mode`, `recent_success`, and status vocabulary. Configured is not
  proof of availability. A disabled diagnostics endpoint is an explicit error.
- Ops owns the build and dependency convergence. Parent owns independent code
  and security review, real-browser mobile/desktop checks, built-network traces,
  each route's latency/heap budgets, and native/buffered AI timing. No browser
  performance target, real-provider reliability, or production readiness is
  established by this frontend unit/integration test work.

## Historical Worktree Record (2026-09-09)

Date: 2026-09-09. Scope: `apps/frontend/**` and this document plus `UI_PERFORMANCE.md`.
Status: frontend implementation locally verified; dependency and browser integration
gates remain blocked. This is not full-roadmap completion or production sign-off.
No backend, deployment, CI, root/global documentation, environment file, or cloud resource was modified.

## Preserved Baseline

The first reliable run of `AdaptiveInterview.test.tsx` and
`ExhibitionInterviewLifecycle.test.tsx` passed 24 tests. All eight previously
reported failures were already fixed in the operator's worktree. Their source
and tests were preserved and extended rather than reimplemented.
Existing persona-library partial-load work and navigation regression tests were
also preserved. Navigation's four supplied tests initially failed and now pass.

## Delivered Areas

| Area | Behavior and verification |
| --- | --- |
| FE-01 / SEC-04/05/10 | URL bearer login removed; safe query parameters retained. Session epochs abort stale API work. Cross-tab auth events invalidate identity. Local verification/reset endpoints replace fabricated verification and mixed password authorities. |
| Session transport | HTTPS auth requests negotiate cookie transport. CSRF material remains in memory; cookie credentials remain HttpOnly. HTTP development bearer credentials use tab storage, with legacy localStorage compatibility. Refresh uses the current cookie/CSRF or in-memory refresh credential. |
| FE-02 | Study switches clear persona/segment rows. Primary persona results do not wait for segment metadata. Mutation ownership survives A-B-A navigation. |
| FE-03 | Exact aliases, separate pathname/search, comparison run IDs, duplicate-history protection, explicit versus omitted workflow steps, and safe same-origin auth return destinations. |
| FE-04 / FE-10 | Detail, stream, fallback, synthesis cancellation; stale callbacks rejected; composer entry points locked. Flat interview DTO, JSON/delta/terminal validation, first-terminal-wins behavior, UTF-8/CRLF support, frame bounds with explicit failure rather than truncation. |
| FE-05 | Per-session serialized study writes with `If-Match` and `expected_revision`. Editable-field allowlist excludes derived persona state/status/findings. Conflicts stop queued overwrites and retain full drafts in tab storage with visible unsaved state. |
| FE-06/07 | Evidence, segmentation, routing, behavioral detail/list/comparison request ownership; separate metrics; unknown coverage; report/plan failures remain errors, not invented empty state. |
| FE-08 | Serial cancellable polling with wall/idle/error bounds, immediate auth failure, private accepted report/persona/batch handles, and GET-based resume without duplicate submission. Pausing observation does not claim to cancel server work. |
| FE-09 | Closed mobile drawer inert/hidden, open drawer focus containment/restoration, named filters, keyboard interview cards. |
| FE-11 | Active local-inference fallback claims and mock routes removed; historical provenance rendering preserved. Paid offers/checkout fail closed unless the server explicitly returns `billing_enabled: true`; URL query parameters confer no entitlement. |
| FE-12 | Shared quote/formula-safe CSV; full Markdown with limitations, citations, source identity, provenance, and complete stored record; saved report version selection. |
| FE-13 | Lazy dashboard views/dialogs, two-at-a-time intent-only module prefetch, nonblocking anonymous auth, independent metrics, bounded saved-study cache, and opt-in primary-content/AI/readback timing. |

## R8 Dependency Review Before Installation

Public npm registry queried at 2026-09-09T19:13:31Z using Node 24.11.1.
No packages were installed during this workstream.

| Package | Installed / requested | License | Registry evidence and necessity |
| --- | --- | --- | --- |
| Vite | 5.4.21 / 7.3.5 | MIT | 7.3.5 published 2026-06-01, not deprecated; latest registry major is 8.2.2. Requested compatible security maintenance target, not a framework replacement. Requires Node ^20.19 or >=22.12. |
| Vitest | 2.1.9 / 4.1.11 | MIT | 4.1.11 published 2026-08-18, not deprecated; latest is 5.0.0. Its Vite peers include ^7.0.0. Requires Node ^20, ^22 or >=24. Existing regression framework retained. |
| React Vite plugin | existing 4.x / candidate 5.2.0 | MIT | 5.2.0 published 2026-03-12; Vite peer supports 4 through 8. Needed to preserve React compilation/HMR compatibility with the requested upgrade. |
| TypeScript | installed 5.9.3 | Apache-2.0 | Installed compiler verified. No compiler upgrade performed. `baseUrl` removed and aliases made relative; no deprecation suppression. Exact compiler/editor pin remains an integration task. |

**Installation blocker:** the mandatory TypeScript dependency-upgrade skill is
only available outside this repository. Remote-engineer mode forbids reads or
execution outside the working directory. No workspace-local copy was found.
The required deferred-tool loader is also unavailable in this session.
Therefore no upgrade engine, package install, manifest version bump, or lockfile
rewrite was attempted. The old vulnerable toolchain remains a release blocker.

**Ops handoff:** the root already declares `apps/frontend` as an npm workspace
and root Neon config/env dependencies. Root and frontend lockfiles both exist;
neonctl is currently declared in the frontend. These were not blindly removed
or moved. Load the required skill in an authorized session, update the reviewed
targets using the root workspace installation, preserve the root-required Neon
CLI, and converge on one root lock graph together with container install paths.
This workstream changed only frontend scripts in its package manifest.
The verification runner automatically omits Vitest 2's `minWorkers` flag on 4+.

## Final Verification Results

| Check | Actual result |
| --- | --- |
| Original known-eight suites before edits | 24 passed / 0 failed; all eight were already repaired in the operator's worktree. |
| Final original suite names | AdaptiveInterview 4/4; ExhibitionInterviewLifecycle 22/22; no failures. |
| Stream transport | ExhibitionStreamTransport 20/20; malformed frames, cancellation, UTF-8, EOF, duplicate terminal, JSON and HTTP errors. |
| Complete frontend suite | 431 passed / 0 failed / 0 skipped in 54 files; 72.386 seconds; exit 0. |
| Production TypeScript + Vite build | PASS, exit 0, 11.859 seconds on the final metadata update. |
| Theme check | PASS, exit 0, 0.986 seconds. |
| Scoped diff check | PASS, no whitespace errors. |
| MOCK HTTP smoke | `/`, `/auth/signin`, `/dashboard`, and requested entry/service modules returned 200; `/api/health` intentionally returned 503 from the mock boundary. |
| Browser and real integration | NOT RUN. No authorized browser/deferred-tool loading path was available; no real auth, paid provider, or deployment call. |

The first full run was 417 passed / 13 failed. Ten failures came from old API
mocks missing the new job/draft readers, two from old preserve-cache/resolve-late
assertions, and one from obsolete batch-failure wording. Those fixtures/assertions
were updated to the approved behavior and their focused scope passed 36 tests
before the final full run. No failing test was skipped or removed.

Exact local final artifacts (ignored):
`apps/frontend/.tmp/test-1788982415957-3dc9f8f6.json`,
`apps/frontend/.tmp/build-1788982567554-a7850543.log`, and
`apps/frontend/.tmp/bundle-measurement.json`.
The build runner captured no text in the final build log; exit code, duration,
fresh emitted assets, gzip sizes and static import relationships were checked
separately. The editor still showed an inconsistent missing `readCache` module
diagnostic although both the CLI compiler and production bundler resolved it.

## Changed File Map

| Paths under apps/frontend | Purpose |
| --- | --- |
| `src/services/api.ts`, `session.ts`, `studyPersistence.ts`, `readCache.ts`, `polling.ts`, `interviewProtocol.ts`, `researchApi.ts`, `neonAuth.ts` | Session/transport contracts, validation, persistence, cache and polling. |
| `src/context/AuthContext.tsx`, `NavigationContext.tsx`, `src/utils/dashboardRoute.ts`, `src/App.tsx` | Auth epochs, exact routes and safe return paths. |
| `src/components/interview/InterviewWorkspace.tsx`, `src/components/dashboard/DashboardLayout.tsx`, `routeModules.ts` | Cancellation, private tree lifecycle, focus handling and lazy views. |
| `src/components/dashboard/views/{StudyWorkflowView,PersonaLibraryView,EvidenceLaboratoryView,SegmentationView,ModelRouterView,InterviewsView,BehavioralTestingView,BehavioralTestDetailView,BehavioralComparisonView,StudiesDashboardView,NewStudyView}.tsx` | Scoped primary loading, saved state, honest errors and instrumentation. |
| `src/components/dashboard/views/workflow/{Step1Context,Step4Interviews,Step5Report}.tsx`, `src/components/auth/AuthPage.tsx` | Composer locks, report versions, limitations and auth destinations. |
| `src/performance/routeTiming.ts`, `src/utils/{exports,useRequestScope}.ts`, `src/motion/useViewMotion.ts` | Explicit timing, faithful exports, request ownership and immediate controls. |
| `src/components/landing/{Comparison,FAQ,FeatureGrid,Footer,HeroDashboardPreview,IntelligenceSection,InteractiveDemo,LandingPage,Pricing,TrustMetrics,UseCases}.tsx`, `src/mocks/fixtures.ts`, `index.html` | Correct remote-only/CPU/billing claims and mock data. |
| `src/types/{auth,index,interview,study}.ts`, `tsconfig.json`, `vite.config.ts` | Contracts, relative aliases and verification environment isolation. |
| `scripts/{verify-frontend,verification-worker,mock-preview}.mjs`, `package.json`, `.gitignore` | Repeatable one-worker verification, isolated preview, script commands and ignored artifacts. |
| `tests/Frontend{SessionBoundary,StudyPersistence,ViewOwnership,PrimaryContent,Accessibility,Performance}.test.tsx`, `Frontend{Exports,Polling}.test.ts` | New behavioral regressions. |
| `tests/{AdaptiveInterview,ExhibitionInterviewLifecycle,StudyCopilot,DemoReadOnly,RoleCountCap,MemoryVisibility}.test.tsx`, `{AuthApiHonesty,ExhibitionStreamTransport,E2eStudyCacheIsolation}.test.ts` | Extended coverage and updated contract fixtures/assertions. |

The supplied `NewModernizationNavigation.test.tsx` and
`NewModernizationPersonaLibrary.test.tsx` were reused, not newly authored.
Their existing result file was left untouched. Root package files and both
lockfiles were unchanged. No commit, push, or deployment was performed.

## Parent Integration Gates

- Cookie auth requires HTTPS and compatible CORS. `/auth/session` requires an
  Origin header even on GET; same-origin browser GETs may omit Origin. Verify or
  adjust that policy in the backend workstream without weakening CSRF/origin
  checks. This frontend must not pretend forbidden headers can be set by JS.
- A cookie session is bootstrapped from `/auth/session`; test real cookie
  delivery, refresh races, access expiry, replay after logout/reset, and cross-tab
  behavior against the auth agent's final contract. No real-user authentication
  was exercised here.
- Google return uses a one-use local state binding and server `/auth/sync`.
  Provider-managed OAuth state/PKCE and real mail delivery remain external gates.
- Billing stays off because the inspected backend subscription DTO does not
  explicitly advertise `billing_enabled`. No payment/provider calls were made.
- Revision conflicts never retry a stale full-history overwrite. Users can
  inspect the retained draft and explicitly discard/reload the server version;
  automatic merging is intentionally not implemented.
- Browser cancellation stops observation/transport, not necessarily server
  inference. Report readback confirms matching persisted report ID/version;
  backend durable provenance and multi-process recovery remain parent gates.
- Existing API lineage handles and immutable source fields are retained; the
  frontend does not fabricate backend parent records or migrate stored data.
- Browser route p50/p95, mobile rendering, real auth, and provider latency are
  not established by jsdom tests. See `UI_PERFORMANCE.md` for actual scope.

## Verification Commands

Run from the repository root:

```text
node apps/frontend/scripts/verify-frontend.mjs test tests/AdaptiveInterview.test.tsx tests/ExhibitionInterviewLifecycle.test.tsx
node apps/frontend/scripts/verify-frontend.mjs typecheck
node apps/frontend/scripts/verify-frontend.mjs test
node apps/frontend/scripts/verify-frontend.mjs build
node apps/frontend/scripts/verify-frontend.mjs theme:check
```

The runner invokes the project npm scripts, uses one worker and no file
parallelism, disables environment-file loading, and writes unique artifacts
under ignored `apps/frontend/.tmp/`. A persistent verification worker avoids
other workstreams interrupting the shared terminal. No commit or push is made.
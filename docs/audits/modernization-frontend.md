# Frontend Continuation Audit

Date: 2026-09-10. Status: **frontend continuation locally verified; release
reservations remain**.
Owned changes: frontend source/tests/tooling, root npm workspace files when
needed, this audit, and the dependency review entry. Existing frontend work,
including concurrent StudioTheme edits, is preserved. No backend, ML, live API,
database, deployment, Git history, or global toolchain operation is part of this
continuation.

## Startup Regression

The handoff's final baseline is **472 passed / 1 failed**, not the older
473-pass ledger. Two shared-terminal invocations returned unrelated Python/Git
output and produced no requested JSON receipt; they are not verification.

The existing detached frontend verifier reproduced the signed-in hero CTA
failure: **5 passed / 1 failed / 0 skipped**, exit **1**, 7.512 s. The expected
new-study heading was missing while the dashboard Suspense fallback rendered.
Receipt: `apps/frontend/.tmp/test-1789036656487-68d9e2cd.json`.

Dashboard module prefetch alone still failed (5/1, exit 1, 9.616 s). Keeping
prefetch and replacing the dashboard shell's eager UI-barrel import with its
three actual controls passed the unchanged LandingPage test: **6 passed**,
exit **0**, 11.310 s total process time. No heading assertion, timeout, or mock
was weakened. Receipt: `apps/frontend/.tmp/test-1789036873731-0c76d131.json`.

The dashboard remains lazy. Auth/returning-session paths may warm its code;
anonymous landing rendering does not. Save-Data/2G suppress speculative loading.
Protected views still wait for session verification before mounting. Module
loading is not private data readiness, and these test durations are not route
latency measurements.

## Retained Frontend Behaviors

The existing continuation implementations and regressions cover scoped cache
reads, request ownership, independent primary/optional loading, honest errors,
serialized study writes and draft recovery, bounded job observation, complete
exports, keyboard/mobile behavior, and separate content/AI/save timing.

Focused verification: **79 passed / 0 failed / 0 skipped, 11 files**, exit **0**,
25.532 s. This includes LandingPage, session boundaries, performance counters,
primary content, view ownership, persistence, polling, navigation, persona
library, exports, and accessibility. Receipt:
`apps/frontend/.tmp/test-1789036925728-62138e73.json`.

## Tooling Migration

Fresh official JSTS session: `53c5ecb4-f2ca-408e-b91e-12991ac59525`.
The installed `--mcp` server was used because this chat does not expose direct
JSTS/search-loading tools. The old completed session was not reused. The server
generates its own root `.tsupgrader` progress metadata; authored docs remain
limited to this audit and the dependency review.

After the pre-install R8 review, the official root installer, compile baseline,
and refreshed runtime baseline passed. The latter recorded **505 passed / 0
failed / 0 skipped** tests and **8/8** assertions: types, production build,
complete tests, strict JSON counts, theme, lock graph, real loopback API-boundary
rejection, and the recorded mock study browser journey. The original stale
baseline was preserved separately. This larger count includes pre-existing
concurrent frontend tests, not 32 tests authored by this continuation.

The names-only official group upgrade actually selected Vite **8.2.2**, Vitest
**5.0.0**, and React plugin **6.1.1**. It initially introduced 12 compiler
errors. Explicit existing Node types and native Rolldown `codeSplitting`
configuration resolved all 12; no strictness setting or type assertion was
disabled. Official post-upgrade compile passed with zero errors.

Runtime-driven compatibility fixes:

- Root `--minWorkers` was removed after the installed CLI rejected it.
  `--maxWorkers=1 --no-file-parallelism` remains.
- Root-hoisted Vitest could not import workspace-only Vite. The reviewed Vite
  version was also declared as a root dev dependency and reconciled using the
  official root installer. No nested or competing install was run.
- On Windows, lowercase `e:/BebshaX` produced a zero-test runner `config` error;
  the same unchanged test command passed **6/6** from canonical `E:\BebshaX`.
  The new shared launcher canonicalizes both the working directory and Vitest
  entry and preserves arguments and verification-environment isolation.
- Three launcher regressions were observed failing on a throwing stub, then
  passed with LandingPage (**9/9**) from the originally failing lowercase path.
- The graph checker now selects Rolldown/Lightning CSS for Vite 8 and retains
  Rollup/esbuild for old locks. Four regression tests cover modern/legacy
  selection, workspace resolution, and mismatched manifests; two initially
  failed and then **4/4** passed. Registry hash comparison remains mandatory.
- The first upgraded complete suite was **511 passed / 1 failed**, exit 1,
  61.630 s. The failing test compared the composed transport `AbortSignal`
  to the caller signal as a whole. The transport already intentionally combines
  caller/session/deadline cancellation. The corrected test asserts the actual
  signal starts un-aborted, then aborts with the caller's exact reason, while
  retaining rejection, reader cancellation, and delta-count assertions. All
  **24** stream-transport tests then passed, exit 0.

After the launcher and graph changes, the retained focused correctness slice
plus the seven new tooling tests passed **86/86**, 13 files, exit 0, 13.959 s.
No test was skipped. Frontend coverage is not configured; no percentage or
coverage delta is claimed.

## Mobile Notice Follow-up

Desktop/mobile screenshots exposed the existing fixed mock-data notice covering
a mobile example-prompt button. A new layout regression failed (**3 passed / 1
failed**, exit 1). The same mock/demo/backend messages now occupy a normal row
inside the main column before the page view. Tokens, status roles, wording,
GSAP, and concurrent theme work were retained. Accessibility, LandingPage, and
demo-read-only tests then passed **16/16**, exit 0, 6.813 s.

Playwright rechecked **1440x1000** and **390x844**, reduced motion enabled.
Notice and example-button bounds did not intersect, and clicking the example
filled the complete expected composer text at both sizes. No horizontal
overflow or unexpected API/outbound request was observed. The earlier broader
browser check also verified visible logo decoding, no page errors, no anonymous
dashboard-module request, and an actual `/api/health` HTTP **503** rejection
from the mock-only boundary. These are synthetic development-preview checks,
not production-bundle browser, live authentication, or live AI evidence.

## Final Verification

The final official replay used the same plan hash as the fresh baseline,
`df72d5ecb972401f8590139fad4d8c2a38d4a7db5424a740fa6a1292b4c6c639`.
No assertions were skipped or weakened. The normal test script and official
runtime wrapper share the canonical, isolated launcher and one-worker flags.

| Final gate | Observed result |
| --- | --- |
| Official compile after final layout change | PASS; 0 new / 0 existing errors |
| Complete frontend suite | **513 passed / 0 failed / 0 skipped, 57 files; exit 0; 61.390 s** |
| Strict complete JSON report | PASS; exit 0; full counts/no failed suites/no skips |
| Final production build | PASS; exit 0; 1.355 s process duration |
| Final TypeScript no-emit check | PASS; exit 0; 8.429 s |
| Final theme check | PASS; exit 0; 0 files needing tokenization; 0.477 s |
| Final workspace manifest/lock consistency | PASS; exit 0 |
| Final recorded mock study journey | PASS; exit 0; 1 Playwright test; 6.017 s process duration |
| Final real loopback API-boundary assertion | PASS; exit 0; HTTP 503 with explicit mock-only body |
| Official runtime comparison | **8/8 passed**, no regression, no inconclusive result |
| Root command gates before notice follow-up | `npm run build`: exit 0, 10.741 s; `npm run typecheck`: exit 0, 8.536 s; `npm run theme:check`: exit 0, 0.676 s |
| Public registry version/integrity check | PASS; exit 0; Vite 8 / Vitest 5 / plugin 6 / TypeScript / Rolldown / Lightning CSS / neonctl |
| Installed `npm ls` tooling/DOM graph | PASS; exit 0; Vite peers and DOM 10.4.1 resolve |
| Scoped `git diff --check` | PASS; exit 0 |
| Public npm audit | **exit 1**; 4 affected package entries: 0 critical, 0 high, 3 moderate, 1 low |

Eight tests were added by this continuation: three launcher tests, four npm
graph tests, and one notice-layout test. The AbortSignal contract correction
is documented above; no application cancellation behavior was weakened.
Coverage remains unconfigured, so there is no measured coverage percentage or
delta. Existing React `act(...)` warnings remain. Build warnings identify the
existing mixed static/dynamic NewStudyView import and future native-loader
`__dirname` deprecation; neither was suppressed or treated as a failed build.

Local runtime artifacts live under `apps/frontend/.tsupgrader/runtime-validation/`:
`continuation-baseline-result.json`, `continuation-baseline-tests.json`,
`postupgrade-result.json`, `frontend-tests.json`,
`continuation-after-versions.json`, `npm-graph-registry-final.log`,
`npm-ls-final.log`, `public-npm-audit-final.log`,
`browser-desktop-mobile.json`, `browser-notice-fixed.json`, and the
`console-notice-fixed-390.png` / `console-notice-fixed-1440.png` screenshots.
The separate notice test receipt is
`apps/frontend/.tmp/test-1789040823654-0895e9f8.json`.

## Changed Files

Only continuation-authored files are listed; pre-existing dirty frontend work
is not attributed to this session. Dependency lock and runtime artifacts are
generated outputs, not manually edited dependency versions.

| Files | Continuation changes |
| --- | --- |
| `apps/frontend/src/App.tsx` | Auth/returning-session module prefetch with Save-Data/2G guard |
| `apps/frontend/src/components/dashboard/DashboardLayout.tsx` | Direct shell-control imports; non-overlapping status-notice layout |
| `apps/frontend/package.json`, `package.json`, `package-lock.json` | Official tooling upgrade, root Vite peer, canonical test launcher, current worker flags |
| `apps/frontend/tsconfig.json`, `apps/frontend/vite.config.ts` | Explicit Node types; native Rolldown vendor-only splitting |
| `apps/frontend/scripts/test-runner.mjs` | Canonical-path, environment-isolated shared test invocation |
| `apps/frontend/tests/FrontendToolchain.test.ts`, `apps/frontend/tests/FrontendNpmGraph.test.ts` | Seven new tooling regressions |
| `apps/frontend/tests/FrontendAccessibility.test.tsx`, `apps/frontend/tests/ExhibitionStreamTransport.test.ts` | Notice-layout regression; explicit composed-signal cancellation assertions |
| `scripts/ops/npm-graph.mjs` | Vite-version-aware engine verification only |
| `apps/frontend/.tsupgrader/runtime-validation/eval-plan.json`, `apps/frontend/.tsupgrader/runtime-validation/run-unit-tests.mjs` | Explicit API boundary; shared launcher; preserved strict runtime gate |
| `docs/audits/modernization-frontend.md`, `docs/DEPENDENCY_REVIEWS.md` | Scoped evidence and R8 review |

## Remaining Reservations

- Four public audit entries remain in the existing neonctl/neon/Hono/diff CLI
  tree; the prior Vite/Vitest findings and all critical/high entries are absent.
  No force audit fix, neonctl downgrade, or unrelated dependency override was
  applied. See [DEPENDENCY_REVIEWS.md](../DEPENDENCY_REVIEWS.md).
- Independent code/security reviewer tools are unavailable in this chat; the
  implementation and its regressions still need independent review.
- No per-route 100-sample latency measurement, live authentication, durable
  database/AI journey, provider reliability, or release certification is claimed.
  Faster build/test durations do not establish page or AI latency budgets.
- No backend/ML test or install, live API/Neon startup, production operation,
  Git commit/branch/push, or global toolchain install was performed.
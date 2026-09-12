# Frontend Continuation Tooling Review (2026-09-10)

Status: **Upgrade applied and locally verified; four CLI audit entries remain.**
The owner explicitly relaxed the earlier method/version ceilings for this
continuation. The historical blocked workflow below remains historical evidence,
not the current target policy. Its completed JSTS session is not reused.

Fresh primary npm registry metadata was read on 2026-09-10. Local Node is
24.11.1. The names-only official JSTS workflow may upgrade the following compatible
stable group; no React or TypeScript major upgrade is authorized or required.

| Package | Existing Lock | Reviewed Stable Target | Necessity, License, And Activity |
| --- | --- | --- | --- |
| `vite` | 5.4.21 | 8.2.2 | Replace the obsolete build/dev tool and its affected transitive tooling. MIT; official Vite release published 2026-08-20. Vite 8 uses Rolldown, so vendor grouping, lazy route boundaries, assets, and the actual production build must be checked. |
| `vitest` | 2.1.9 | 5.0.0 | Retain the existing test framework on a maintained line compatible with Vite 8. MIT; official release published 2026-09-03. Removed worker flags, mock APIs, DOM realms, and strict assertions require migration verification. |
| `@vitejs/plugin-react` | 4.7.0 | 6.1.1 | Retain the official React JSX/Fast Refresh integration with Vite 8. MIT; official release published 2026-08-28. Its Vite peer is `^8.0.0`; no React runtime change is needed. |

Metadata sources: [Vite 8.2.2](https://registry.npmjs.org/vite/8.2.2),
[Vitest 5.0.0](https://registry.npmjs.org/vitest/5.0.0), and
[React plugin 6.1.1](https://registry.npmjs.org/%40vitejs%2Fplugin-react/6.1.1).
None was marked deprecated. Vite/plugin require Node `^20.19.0 || >=22.12.0`;
Vitest requires `^22.12.0 || ^24.0.0 || >=26.0.0` and accepts Vite
`^6.4.0 || ^7.0.0 || ^8.0.0`. The local runtime meets these requirements.
Vite-managed Rolldown (`~1.2.4`, MIT) and Lightning CSS (`^1.33.0`, MPL-2.0)
replace old bundler internals; these are build-time transitive dependencies,
not new application services. Their actual selected metadata/integrity and
advisories remain final verification gates.

Keep DOM Testing Library **10.4.1** explicitly declared. Keep the existing
jsdom 24 and jest-dom 6 lines: Vitest has an unrestricted optional jsdom peer,
and neither a DOM major nor matcher major is necessary for this upgrade.
Latest jsdom 30.0.1 requires Node `^22.22.2 || ^24.15.0 || >=26.0.0`, which
does not include this machine's Node version. Do not install React Compiler,
optional Babel integrations, a new browser framework, or a global toolchain.
The already reviewed isolated Playwright runtime is reused.

The post-upgrade root test command exposed `ERR_MODULE_NOT_FOUND` for Vite
imported by the root-hoisted Vitest 5 package. The workspace copy of Vite was
not reachable from that peer. Before reconciliation, Vite `^8.2.2` is therefore
also declared as a root development dependency: it supplies the same reviewed
shared build/test peer to the root workspace runner, not a second Vite version
or installation graph. The official root installer must reconcile the root
lock, and the unchanged LandingPage test must then execute successfully.

The root workspace/lock is authoritative. Use the official installed JSTS MCP
tools for scan, install, group upgrade, compile, runtime, and one final summary;
no `name@version` no-op call, shell dependency install, or competing nested graph.
The server is accessed through its documented `--mcp` entry point because direct
JSTS/deferred-search tools are not exposed to this chat. The tool can generate
its own root `.tsupgrader` progress metadata; authored source/docs stay within
the owner's frontend continuation paths.

Pre-upgrade local repair evidence: the retained LandingPage content assertion
failed with 5 passed / 1 failed, then passed all 6 after dashboard startup
prefetch and direct shell-control imports. The surrounding frontend regression
slice passed 79 tests across 11 files, exit 0. Fresh JSTS session
`53c5ecb4-f2ca-408e-b91e-12991ac59525` recorded a complete **505/505** pre-upgrade
baseline and **8/8** runtime assertions. The official names-only group call
applied the reviewed versions. Actual lock/installed comparison confirmed Vite
**8.2.2**, Vitest **5.0.0**, plugin-react **6.1.1**, Rolldown **1.2.8**, and
Lightning CSS **1.33.0**. The transitive Rolldown patch is inside Vite's reviewed
`~1.2.4` range. React/React DOM **18.3.1**, TypeScript **5.9.3**, DOM Testing
Library **10.4.1**, jsdom **24.1.3**, and jest-dom **6.9.1** remain unchanged.
Official post-upgrade compilation passed after explicit Node types and native
Rolldown configuration. The final unchanged-plan runtime comparison passed
**8/8** assertions with **513/513** tests, zero failed/skipped tests, and exit 0
for compile, production build, tests, strict JSON report, theme, graph, real
loopback API-boundary rejection, and recorded mock study browser flow. The
eight additional tests are three launcher, four graph, and one mobile-notice
regression. Windows runner entry/CWD paths are canonicalized; the retired
`minWorkers` flag is removed without enabling parallel files. The composed
AbortSignal assertion now checks actual cancellation and reason instead of
incorrect whole-signal equivalence. No strictness/assertion gate was disabled.

`npm run check:npm-graph -- --registry` passed, exit 0, including selected
Rolldown **1.2.8** integrity. `npm ls vite vitest @vitejs/plugin-react typescript
@testing-library/dom --json` passed, exit 0, after root peer reconciliation.
This verifies the actual installed graph rather than the upgrade tool's prose.

The final read-only public audit (`npm audit --json
--registry=https://registry.npmjs.org`) exited **1** with **4** affected package
entries, down from 9: **0 critical, 0 high, 3 moderate, 1 low**. These are
package/metavulnerability entries, not four distinct CVEs. Remaining entries:

| Package | Severity | Public advisory / disposition |
| --- | --- | --- |
| `@hono/node-server` | Moderate | [Windows static traversal](https://github.com/advisories/GHSA-frvp-7c67-39w9) and [aborted-WebSocket memory leak](https://github.com/advisories/GHSA-9mqv-5hh9-4cgg); existing Neon CLI dependency |
| `diff` | Low | [Patch-parser denial of service](https://github.com/advisories/GHSA-73rr-hh4g-fpgx); existing CLI dependency |
| `neon` | Moderate | Metavulnerability through the dependencies above |
| `neonctl` | Moderate | Metavulnerability through `neon`; remains 4.14.3 |

The audit's proposed neonctl **2.37.1** downgrade was not applied. These findings
remain open for a compatible CLI-specific dependency review; this continuation
does not claim a clean audit or production sign-off. No additional dependency
was installed for browser checks. The existing isolated Playwright/Edge runtime
verified mock sign-in and the study-approval journey, with desktop/mobile
rendering and actual HTTP/API isolation checks. It did not exercise live AI,
real identity providers, the production browser bundle, or per-route latency
budgets. Full frontend evidence is in
[the continuation audit](audits/modernization-frontend.md).

# Targeted Frontend Tooling Upgrade (2026-09-10)

Status: **BLOCKED; the required tooling upgrade was not applied.** The official
MCP workflow and prerequisite repairs ran, but the installed group-upgrade tool
does not expose bounded version targets. Final isolated baseline validation also
has one reproducible existing frontend test failure, detailed below.
The owner approved the tooling upgrade and necessary compatible peers, with no
React or TypeScript major upgrade. The root npm workspace and lock remain
authoritative. No backend, ML, private database, deployment, or global toolchain
change is part of this work.

## R8 Review

| Package | Existing Lock | Approved Target | Purpose, Necessity, License, And Maintenance |
| --- | --- | --- | --- |
| `vite` | 5.4.21 | 7.3.6 | Replace the obsolete development/build tool with the newest stable Vite 7 patch; retain the Rollup-based build rather than adopting Vite 8. MIT; official Vite maintainers published this patch on 2026-06-25. |
| `vitest` | 2.1.9 | 4.1.11 | Keep the existing test suite on a maintained runner compatible with Vite 7. MIT; official Vitest maintainers published this patch on 2026-08-18. Worker flags, fake timers, mocks, DOM realms, and assertions require verification. |
| `@vitejs/plugin-react` | 4.7.0 | 5.2.0 | Retain the official React JSX/Fast Refresh integration with Vite 7. MIT; official Vite maintainers published this release on 2026-03-12. No React runtime major change is required. |

Primary npm registry metadata was read on 2026-09-10:
[Vite](https://registry.npmjs.org/vite/7.3.6),
[Vitest](https://registry.npmjs.org/vitest/4.1.11), and
[React plugin](https://registry.npmjs.org/%40vitejs%2Fplugin-react/5.2.0).
Vite/plugin require Node `^20.19.0 || >=22.12.0`; Vitest accepts Node
`^20.0.0 || ^22.0.0 || >=24.0.0`. Local Node 24.11.1 meets both.
Vitest accepts Vite 7, and the plugin accepts Vite 4 through 8. TypeScript 5.9.3
and React 18 remain outside the target list.

JSTS groups the existing `jsdom` and `@testing-library/jest-dom` dependencies with
these tools. Their existing DOM environment and matcher roles remain necessary;
Vitest's `jsdom` peer range is unrestricted, so a DOM major upgrade is not required
solely by Vite 7/Vitest 4. Any necessary peer change must be reviewed and validated
without skipped tests or weaker assertions. Vite 7 updates its managed esbuild
dependency to the 0.27 line and keeps Rollup 4; these are build-tool internals,
not new application dependencies. Public audit results are a separate gate.

The official runtime recorder may provision `@playwright/mcp` and
`@playwright/test` in its isolated validation environment. Both are Apache-2.0
Microsoft-maintained browser automation tools, necessary to record and replay
the mock-only critical journey; they are not added to application dependencies.
Use an existing supported browser where available. References:
[Playwright Test](https://registry.npmjs.org/%40playwright%2Ftest/latest) and
[Playwright MCP](https://registry.npmjs.org/%40playwright%2Fmcp/latest).
The upgrade-only server uses port 5217 because the existing mock server on 5194
belongs to another session. It loads the actual Vite configuration, disables
environment files, forces mock/auth/API values, and rejects `/api` requests.

Baseline prerequisite discovered before the tooling upgrade:
`@testing-library/react` 16 requires `@testing-library/dom` `^10.0.0`.
The official root install left that peer unresolved, producing missing
`screen`/`fireEvent`/`waitFor` exports and test-suite collection failures.
`@testing-library/dom` 10.4.1 is the public registry's current stable release,
MIT licensed, published by the existing Testing Library maintainers, and supports
Node >=18. It provides the DOM queries/events re-exported by the already-used
React testing package; declaring/installing it is necessary for reproducible
tests, not a new framework or application feature. Review source:
[DOM Testing Library](https://registry.npmjs.org/%40testing-library%2Fdom/10.4.1).
The first runtime attempt is invalid as a passing baseline: its test parser
reported 98 passing tests despite process exit 1 and failed collection. Require
both complete test counts and exit 0 in the final gates.

## Official Workflow Evidence

- Skill: official JSTS `typescript-dependencies-upgrade`, including its plan,
  monorepo, peer-dependency, upgrade, and runtime-validation phase instructions.
- Session: `24dc0bd9-5f33-49c1-8d60-8e050e9e4dca`.
- Requested packages: `vite`, `vitest`, `@vitejs/plugin-react`.
- Scan: npm monorepo, one frontend workspace, no applicable framework guidance.
- Flags: `validateRuntime=true`, `validateBundlerChanges=false`,
  `runNpmAudit=false`, `disableKnowledgeBase=false`.
- Required gates: official install/compile baseline, isolated mock runtime
  baseline, bounded group upgrade, official post-upgrade compile/runtime, root
  build, complete single-worker frontend tests, theme check, workspace/lock
  integrity check, and public registry audit. No commit or branch is authorized.

## Outcome And Resume Blockers

The group-upgrade MCP was called with
`@vitejs/plugin-react@5.2.0`, `vite@7.3.6`, and `vitest@4.1.11`. It reported
configuration-only changes, but direct manifest and public-registry lock checks
proved that all three versions were unchanged. Its public `tools/list` schema
accepts package names only; there is no target-version input, and the installed
CLI help offers no version-bound control. The version-qualified call was a
no-op, not a successful upgrade. An unbounded call could select Vite 8/Vitest 5,
outside the owner's approved lines, so it was not made. No existing dependency
version was manually bumped and no shell install/audit-fix command was used.

Actual selected lock: Vite **5.4.21**, Vitest **2.1.9**, React plugin **4.7.0**,
TypeScript **5.9.3**, esbuild **0.21.5**, Rollup **4.63.1**, neonctl **4.14.3**.
The only new frontend direct dependency is the required DOM Testing Library peer
**10.4.1**, installed by MCP after the R8 review above. Playwright Test **1.63.0**
is isolated under `.tsupgrader/runtime-validation`, not an application dependency.
Default Vitest exclusions are preserved and extended only to keep those
Playwright specs out of the unit runner.

Verification evidence:

| Gate | Measured Result |
| --- | --- |
| Official compile after DOM peer repair | PASS; initial 119 missing-peer errors resolved |
| Initial complete MCP baseline and comparison | 7/7 assertions passed in each; 473/473 tests, zero failed/skipped; unchanged old tooling |
| Final corrected isolated MCP baseline | 5/7 assertions passed; 472/473 unit tests, one failed, zero skipped; strict JSON report correctly failed with it |
| Final browser replay | PASS in 12.197 s; mock sign-in, study creation, two context answers, goal approval, suggested-roles outcome |
| Final MCP production build / typecheck / theme / lock graph | PASS; zero files needing theme tokenization |
| Root `npm run build` | PASS, exit 0; 2,447 modules, Vite 5.4.21 build 20.18 s; existing mixed static/dynamic NewStudyView import warning |
| Public registry graph/integrity | PASS for selected root-lock versions; root lock remains authoritative, historical nested lock present |
| `npm ls` installed graph | Not certified: npm threw `Cannot read properties of null (reading 'edgesOut')` |
| Recorder cleanup | Verified no listener on 5217 and no owned mock-server process; other services untouched |

The final failing test is
`BebshaX Premium Landing Page opens the console from the hero CTA when the visitor is already signed in`
in [LandingPage.test.tsx](../apps/frontend/tests/LandingPage.test.tsx). Its heading
query expires while the lazy dashboard's Suspense fallback is still rendered.
One isolated run with the same verification environment reproduced exit 1;
machine contention/route-load timing is plausible, not a proven root cause.
No test was skipped, weakened, or changed to hide this failure. Earlier 473/473
runs are historical evidence, not the final corrected baseline verdict.

The corrected eval plan makes its unit process set
`BEBSHAX_FRONTEND_VERIFY=1` itself, blocks root environment-file loading, checks
the JSON report for full counts/no skips/no failures, and asserts the successful
post-approval UI state. Its final result is a baseline only; no real post-upgrade
comparison can be claimed until the bounded upgrade is applied.

Public npm audit against `https://registry.npmjs.org` reported **9 affected
packages: 1 critical, 1 high, 6 moderate, 1 low**. Remaining tooling findings
include [Vitest UI file read/execution](https://github.com/advisories/GHSA-5xrq-8626-4rwp),
[Vitest mock redirect traversal](https://github.com/advisories/GHSA-82fw-gwwq-j7x9),
[Vite Windows deny bypass](https://github.com/advisories/GHSA-fx2h-pf6j-xcff),
and [esbuild development-server exposure](https://github.com/advisories/GHSA-67mh-4wv8-2f99).
Additional findings affect the existing neonctl/neon/Hono/diff tree. These counts
include transitive/metavulnerability entries, not nine distinct CVEs. No audit
fix, downgrade, private database operation, service deployment, commit, or branch
creation was performed. OPS-01 remains open.

Resume requires an official MCP path that supports the approved bounded targets
or an explicit change to the owner's method/version constraints. Resolve the
isolated baseline test and establish a fresh green MCP baseline before applying
that upgrade. The existing strict runtime plan can then be replayed unchanged.

The operations review below is historical pre-upgrade evidence. Its old tooling
blocker is not considered closed until the required gates above are recorded.

# Operations Dependency Review (2026-09-10)

This scoped review supplements the existing [dependency review](DEPENDENCY_REVIEW.md).
No dependency was added, upgraded, installed or removed during this batch. Existing
Python hash locks and the root npm lock were preserved, not regenerated from the
shared environment. Passing registry checks does not mean a package has no CVEs.

## Verified Existing Graph

`node scripts/ops/npm-graph.mjs --registry` verified these exact root-lock versions
and their integrity hashes against public npm metadata on 2026-09-10:

| Package | Locked Version | Public Evidence |
| --- | --- | --- |
| Vite | 5.4.21 | [npm](https://registry.npmjs.org/vite/5.4.21) |
| Vitest | 2.1.9 | [npm](https://registry.npmjs.org/vitest/2.1.9) |
| React Vite plugin | 4.7.0 | [npm](https://registry.npmjs.org/%40vitejs%2Fplugin-react/4.7.0) |
| TypeScript | 5.9.3 | [npm](https://registry.npmjs.org/typescript/5.9.3) |
| esbuild | 0.21.5 | [npm](https://registry.npmjs.org/esbuild/0.21.5) |
| Rollup | 4.63.1 | [npm](https://registry.npmjs.org/rollup/4.63.1) |
| neonctl | 4.14.3 | [npm](https://registry.npmjs.org/neonctl/4.14.3) |

The root workspace is authoritative. The existing frontend lock remains historical
input, not an alternative installation graph. Root scripts, CI, setup and the web
image use `npm ci --workspaces --include-workspace-root`. Do not run nested installs
or use `--prefix` to choose a competing graph.

Python release checks cover the existing complete/full and runtime hash locks;
NumPy 2.5.2, SciPy 1.18.1 and scikit-learn 1.9.0 remain frozen. Existing reviewed
build/test/audit tools are covered by the prior review, not newly installed here.
New ops code uses standard libraries and existing Pydantic/Alembic/SQLAlchemy only.

## Required Tooling Upgrade Gate

The old Vite/Vitest/esbuild set remains a release blocker under OPS-01. Loopback
binding reduces exposure; it is not a substitute for supported tooling or audit.
Public latest metadata returned Vite 8.2.2, Vitest 5.0.0 and React Vite plugin 6.1.1
on 2026-09-10. All three report MIT licenses and active official publishing. These
are observed candidates, not approved versions or a compatible-set certification.

- [Vite 8.2.2](https://registry.npmjs.org/vite/8.2.2): Node `^20.19.0 || >=22.12.0`;
  changes the bundler to Rolldown. Existing vendor chunk behavior must be tested.
- [Vitest 5.0.0](https://registry.npmjs.org/vitest/5.0.0): Node
  `^22.12.0 || ^24.0.0 || >=26.0.0`; Vite peer `^6.4.0 || ^7.0.0 || ^8.0.0`.
  Review worker flags, mock lifecycle, DOM environment and assertion changes first.
- [React Vite plugin 6.1.1](https://registry.npmjs.org/%40vitejs%2Fplugin-react/6.1.1):
  Vite peer `^8.0.0`. Do not combine it with the currently locked Vite 5.

The operator requires the `typescript-dependencies-upgrade` skill before any
version change. Its supplied location is outside this remote worker's permitted
project directory; no project-local copy exists. The worker did not bypass that
requirement or change versions. The supervising parent must load that skill and
review a bounded compatible upgrade, then verify build/tests without weaker
assertions. Adding any direct dependency still requires its own R8 review first.

## After Concurrent Tests Finish

No install is needed to use the code changes against the current matching graph.
For a clean checkout or to reconcile the existing reviewed locks, the parent may
run the following from the root only after all shared-environment tests stop:

```powershell
.venv/Scripts/python.exe scripts/ops/dependencies.py install
npm ci --workspaces --include-workspace-root
npm run check:npm-graph
npm run build
npm test
```

Use `.venv/bin/python` on Linux. These install the existing reviewed graph, not the
candidate versions above. No global installation or machine setting is required
by this batch. The release image/CI toolchain remains the pre-existing Node
24.20.0/npm 11.19.0 and Python 3.12.14 pins. Local Node was 24.11.1, so local checks
do not certify the image toolchain. Recheck public metadata/advisories at release.

Container builds, non-root runtime checks, SBOM/CVE scans, clean Linux/Windows
reproduction and live recovery remain separate parent-scheduled gates. Do not
publish images, deploy, migrate production, or infer a backup rehearsal from
synthetic file tests. See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
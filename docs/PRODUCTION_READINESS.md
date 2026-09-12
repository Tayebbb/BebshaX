# Production Readiness - Operations Gate (2026-09-10)

**BLOCKED for release. Operations foundations are implemented, not production
certified.** The scoped results below belong to this workstream; older tables
are archived evidence. No commit/push/deploy, real DB/provider call, weight
change, host installation, service start/stop or volume reset was performed.

## Current Batch (2026-09-10)

Only the assigned operations, scripts, deployment/configuration and setup docs
were changed. Existing uncommitted locks and other owners' source/tests were
preserved. No dependency installation/upgrade, credential/environment-file read,
provider call, database connection/migration, container build/start, production
deployment or Git publication was performed. The old snapshot below remains
dated evidence and is not a repeated clean-install or recovery claim.

| Check | Executed Result And Limit |
| --- | --- |
| Canonical `npm run test:ops` | PASS: 33 Node tests and 43 Python tests, exit 0. Covers launchers, retirement notices, policy consent/context/cleanup, migration target/TLS/no-apply, synthetic recovery files, image probe failure paths and configuration. |
| Node syntax | PASS: `node --check` for both development launchers, production start, Python runner, isolated check runner, npm graph and web-config helper. |
| Python lint | PASS: `.venv/Scripts/python.exe -m ruff check --config apps/backend/pyproject.toml scripts deploy`. Bug-tier only; not a full backend type check. |
| Root build | PASS: `npm run build` from root through the scrubbed runner; TypeScript 5.9.3 and Vite 5.4.21, 2,403 modules. A source-owner warning remains: NewStudyView is both statically and dynamically imported. No browser performance or layout certification. |
| Frontend types | PASS: existing TypeScript CLI `--noEmit --project apps/frontend/tsconfig.json`. Relative aliases work without `baseUrl` or deprecation suppression. |
| npm graph and registry | PASS: `node scripts/ops/npm-graph.mjs --registry`; both manifests match the root lock and all seven selected tool versions/integrity hashes match public npm metadata. This is not a vulnerability scan. |
| Python/preflight | PASS: default `scripts/release_preflight.py`, 93 full / 60 runtime hash-locked distributions, frozen NumPy 2.5.2 / SciPy 1.18.1 / scikit-learn 1.9.0. No network/model/DB probe requested. |
| Fake cross-route evaluation | PASS: one fixed persona/question across two scripted routes, two served rows, zero failures, `simulated=True`. Output retained under `.tmp/ops/cross-route-fixture-20260910.*`; no live inference or model-quality claim. |
| Patch hygiene | PASS: scoped `git diff --check` with retained receipt. Script-name scan contains only retirement notices, a removal filter and negative tests for Ollama; historical artifacts were untouched. |
| Production entry point | Command contract and rejection paths tested. `npm start` uses the existing production validator, one non-reloading loopback API worker, no database startup/migration. Actual hosted startup needs operator settings/model and was not attempted. |
| Container configuration | Offline tests pass for private networking, non-root identities, immutable mounts, deadline ordering and single Docker CMD/ENTRYPOINT. Compose `config --quiet`, image build/run and live UID permissions were deliberately deferred to the parent after the concurrent-test batch. |
| Editor diagnostics | Edited code/config/docs checked with `get_errors`. The editor reported duplicate CMD in the API Dockerfile; direct source and the focused executable invariant check confirm exactly one CMD and one ENTRYPOINT. Actual Docker validation remains pending; no command was removed to hide the diagnostic. |
| Application suites | Full backend, ML and frontend test suites were not rerun by this worker during the shared batch. The root sequential `npm test` graph is wired for the parent; existing tests/assertions and coverage gates remain enabled. |

Receipts and logs are under `.tmp/ops/` with `20260910` labels, including
`root-ops-suite-20260910`, `root-build-20260910`, `frontend-types-20260910`,
`npm-registry-20260910`, `ops-preflight-20260910`, `ops-lint-20260910`,
`ops-cross-route-fake-20260910` and `ops-diff-check-20260910`.
Shared synchronous terminals initially returned other agents' output; those
results were not counted. Isolated runner receipts establish the results above.

### Delivered Changes

- Root [package.json](../package.json) now has canonical workspace build/test
	commands and production [start.mjs](../scripts/start.mjs). The backend-only
	launcher no longer starts Docker or falls back to a global Python interpreter.
- Direct Vite dev/preview binds loopback with strict ports; root and CI builds
	retain the same workspace dependency graph. No version or lock churn.
- Compose forwards `BEBSHAX_REMOTE_PROCESSING_POLICY` without built-in approvals.
	[SETUP.md](SETUP.md#remote-processing-is-denied-by-default) documents only the
	deny-all JSON. Smoke/capacity/cross-route probes use the unchanged operator
	policy and fixed synthetic prompt context; credentials and `--allow-network`
	alone never grant processing permission. Routing-owned providers remain separate.
- Historical Ollama benchmark/smoke/local-judge/preflight paths terminate with
	retirement notices. Historical provenance and artifacts are not deleted.
- [migrate_db.py](../scripts/migrate_db.py) uses explicit URL-variable selection,
	exact confirmation, known-pooler rejection, remote `verify-full` plus separate
	consent, and plan-only default. Applying one Alembic head is explicit, with no
	auto-initializer or seeding. Setup carries the same target contract.
- [runtime_probe.py](../deploy/runtime_probe.py) is shipped in the API image and
	used by release CI for UID/GID, frozen numerical versions and actual disposable
	filesystem writes. Existing recovery/immutable-artifact safeguards remain tested.

### Pending Parent Work

The required `typescript-dependencies-upgrade` skill is outside this worker's
permitted project directory, with no local copy. Version changes were not made
without it. Current Vite 5.4.21 / Vitest 2.1.9 / esbuild 0.21.5 are still an
OPS-01 release blocker. Public newer versions were inspected, not adopted.
[DEPENDENCY_REVIEWS.md](DEPENDENCY_REVIEWS.md) records versions, evidence and
the exact install commands to run only after concurrent tests stop:

```powershell
.venv/Scripts/python.exe scripts/ops/dependencies.py install
npm ci --workspaces --include-workspace-root
npm run check:npm-graph
npm run build
npm test
```

No install is necessary for this batch against the current matching graph. A
major-version upgrade requires the parent to load the required skill, review
breaking behavior and dependencies, reconcile only the root lock and rerun the
same tests without assertion weakening. Local Node 24.11.1 is not the image/CI
Node 24.20.0/npm 11.19.0 pair; that clean release-toolchain gate remains open.

After the shared test batch: quiet Compose validation, clean Windows/Linux
reproduction, container build/non-root/runtime/model checks, fresh npm/Python/image
audits and SBOMs, real HTTPS/authenticated browser flows, independent processing
approval, DB-owner migration/TLS checks, and a separate-target PG16 backup/restore
with complete lineage, measured RPO/RTO and scheduling are still required. No
synthetic test is a backup rehearsal. The supervising parent owns integration
of root execution logs and other out-of-scope documentation.

## Prior Operations Snapshot (2026-09-09)

The synchronous [check runner](../scripts/ops/run-check.mjs) records exit receipts
and logs under `.tmp/ops/`, with scrubbed child credentials, no environment-file
input and bounded numerical threads. Windows checks use a separate process group
to survive other workstreams' terminal interruptions. Incomplete attempts were
not called passes. Concurrent source changes make results scoped snapshots.

| Gate | Result And Limit |
| --- | --- |
| Python closure | PASS: 93 full / 60 runtime distributions resolved from both projects + dev/build requirements with hashes. Numerical pins remain NumPy 2.5.2 / SciPy 1.18.1 / scikit-learn 1.9.0. |
| Clean Windows install | PASS: hash-verified wheelhouse, no-index install into a new Python 3.12.9 environment, both project wheels built from disposable source copies, `pip check`. Shared `.venv` unchanged. |
| Installed consistency/audit | PASS: installed `pip --isolated check` and `pip_audit --progress-spinner off --desc off --format json` exit 0. No known vulnerabilities reported. Local BebshaX/ML packages are skipped because they are not on PyPI, not security-certified. |
| Clean locked audit | PASS: same pip-audit command in the offline-reproduced full environment, exit 0. Includes reviewed build/type tools. No auto-fix or version upgrade performed. |
| Image provenance | PASS: all four recorded index digests matched public Docker Hub tags. Node 24.21.0 tag was absent; Node 24.20.0/npm 11.19.0 were verified. Digest pins are not CVE/runtime evidence. |
| Compose | PASS: default/full quiet configuration parsing using installed standalone Compose, an empty temporary env-file and synthetic settings. No daemon/service contact. Isolated Docker plugin discovery was unavailable; standalone was explicit. |
| New ops regressions | PASS: 25 Node + 28 Python tests; bundle hashes/portable keys, synthetic backup/restore file flow, consent/target/TLS, read-only/private deployment, CI pins/gates, startup model/origin guard, safe launchers, exact-origin CSP/Vercel and root-lock mismatch tests. |
| Preserved judge checks | PASS: 4 existing FakeAdapter disjoint-judge tests. Executable local benchmarking is retired; tested historical helpers remain importable. |
| Lint/syntax | PASS at executed scope: repository bug-tier Ruff for owned operations Python and Node syntax/regression tests. |
| Backend Pyright | BLOCKED: final published Pyright 1.1.412 snapshot, 153 errors / 2 warnings / 142 files / 10.232s (earlier concurrent-source run: 152 errors). No suppressions or type-setting changes. The first invalid internal-bundle launch lacked typeshed initialization and is not the baseline. |
| Existing ops contracts | BLOCKED: 13 failed / 13 passed in 0.94s. Unmodified tests demand old exact unpinned install commands, automatic migrations, old host data mounts/nginx layout and Node pin. Parent owns contract updates; tests remain enabled. |
| Root npm graph | PASS for manifest consistency only: Vite 5.4.21, Vitest 2.1.9, esbuild 0.21.5, Rollup 4.63.1, neonctl 4.14.3; nested lock remains. Supported-tooling migration, npm audit and clean build are frontend-owner gates. |
| Linux/images | BLOCKED locally: default and explicit Docker Desktop Linux-engine pipes unavailable. No engine was started. Actual builds, Linux wheels/model load, nginx syntax/UID/write permissions and image scans remain CI/operator gates. |
| Recovery/browser/HTTPS | UNVERIFIED: no live PG restore, scheduler, encrypted destination, real lineage export, RPO/RTO measurement, authenticated browser journey or deployed HTTPS rehearsal. Synthetic tests do not establish these. |

## OPS Delivery

| ID | Foundation And Remaining Gate |
| --- | --- |
| OPS-01 | Launcher loopback/strict port and production refusal. Frontend owner: compatible tooling upgrades and direct Vite exposure. |
| OPS-02 | R8 review, universal/full/runtime hash locks, preserved numerical pins, locked setup/CI/images and offline reproduction. Linux clean install remains outstanding. |
| OPS-03 | Root-lock consistency check and matching web/CI/Vercel workspace installs. Frontend manifest/lock upgrades remain pending. |
| OPS-04 | 15s outer > 12s HTTP > 8s DB readiness, 180s startup grace, required pinned model/origin guard. Parent owns health/main; cold readiness unmeasured. |
| OPS-05 | Explicit backup/verify/restore, bounded portable keys, immutable model hash and supplied lineage, no clean/drop/overwrite. Parent owns real lineage exporter and different-host PG16 rehearsal. |
| OPS-06 | Commit-pinned actions, least privilege, blocking audit/types, unchanged 68% coverage floor, retained migration/PG/frontend/gitleaks gates, Windows/Linux installs and image SBOM/CVE gates. Known failures block; browser/recovery evidence still required. |
| OPS-07 | Verified image digests, non-root API/web, read-only roots, private/loopback DB, resource/log/restart limits, persistent data and immutable model mount, no demo default. Running-container/disk/restart tests outstanding. |
| OPS-08 | Exact HTTPS tenant CSP, same-origin API, no CORS regex, fail-closed public-origin guard and Vercel API gate. Parent owns session/cookie/CSRF and real callback/HTTPS verification. |
| OPS-09 | Unbuffered request/response proxy, 315s idle > current 300s router cap, 15/25/45s drain/server/container shutdown. Heartbeat/stall/disconnect/durable state need live rehearsal. |
| OPS-10 | No unreviewed spreadsheet engine installed. Parser/admission/CPU budgets and valid-XLSX acceptance belong to parent data/security owners. |
| OPS-11 | Images are the release path; root dev/start is not a supervisor. Vercel fails until an actual explicit API configuration is selected. Hosting/HTTPS/storage budget unprovisioned. |
| OPS-12 | Written dependency/image review, unknown pretrained rights excluded, explicit dataset/model/GSAP/commercial acceptance gate. No blanket commercial license claim. |

## Commands And Handoff

From the root, wrap commands as
`node scripts/ops/run-check.mjs LABEL EXECUTABLE ARGUMENTS...` for a retained receipt.

```text
.venv/Scripts/python.exe scripts/ops/dependencies.py check
.venv/Scripts/python.exe scripts/ops/reproduce.py --environment .tmp/ops/repro --wheelhouse .tmp/ops/wheelhouse/windows
.venv/Scripts/python.exe -m pip --isolated check
.venv/Scripts/python.exe -m pip_audit --progress-spinner off --desc off --format json
.tmp/ops/repro/Scripts/python.exe -m pip_audit --progress-spinner off --desc off --format json
.venv/Scripts/python.exe scripts/ops/registry.py check
.venv/Scripts/python.exe scripts/ops/compose_check.py --standalone
.tmp/ops/repro/Scripts/python.exe -m unittest discover -s scripts/tests -p test_ops_*.py -v
node --test scripts/tests/ops-*.test.mjs
.venv/Scripts/python.exe -m pytest apps/backend/tests/evaluation/test_eval_judge_disjointness.py -q --no-cov
.venv/Scripts/python.exe -m pytest apps/backend/tests/test_ops_env_parity.py -q --no-cov
.tmp/ops/repro/Scripts/python.exe scripts/ops/typecheck.py --outputjson apps/backend/bebshax
node scripts/ops/npm-graph.mjs
.venv/Scripts/python.exe scripts/release_preflight.py
```

Reproduction refuses an existing environment; use a new path when repeating.
Full backend/frontend suites were not rerun by operations. Required parent work:

- Reconcile the out-of-scope operations contract tests with approved locking,
	immutable-storage, entrypoint and root-workspace semantics. Preserve their
	intended invariants; do not remove/disable tests or lower coverage for green.
- Resolve actual backend type errors; the type job is intentionally blocking.
- Frontend owner: finish supported tooling/root lock and verify the pinned
	Node/npm pair, or coordinate new reviewed pins. Operations does not edit npm
	manifests/locks and exclusively owns Docker adaptation.
- Auth/config owner: verify server revocation, cookie flags, CSRF/Origin,
	callbacks, trusted proxy IP/scheme chain, HTTPS and DB TLS. CSP alone is not proof.
- Data owner: supply complete storage-key lineage and exporter checks for data,
	persona versions and transcripts. Backup schedule, encrypted storage, retention
	and a different-host rehearsal need explicit source/target consent.
- Documentation owner: synchronize root/other active docs and the implementation
	ledger outside this write scope. Preserve historical provenance/audit evidence.

The active script scan found no retired local-provider invocation/URL wiring.
Remaining name matches are a rejection filter and negative tests/retired-path
assertions. Offline dataset replays and SQLite wording are not live-inference
claims. Historical evidence and real environment files were not scanned/changed.

<details>
<summary>Historical production-readiness evidence (not current release certification)</summary>

Original dated evidence follows. Its offline/local-live, old install and readiness
claims are superseded by the current gate above.

> Status legend: ✅ VERIFIED (exercised in this repo — test, live run, or config validation) · 🟡 PARTIAL · 🔴 BLOCKED · ⏸️ DEFERRED (deliberate). Nothing is marked complete because code exists; each ✅ names how it was exercised.

## Current ML maintenance assessment (2026-09-09)

**Research prototype, not a production-readiness sign-off.** The numbered
tables below preserve earlier dated checks, not freshly rerun gates or proof
that their human security actions were completed. Original phase dates remain.
Post-sync local checks are listed explicitly; live DB/provider/container/browser
evidence predates upstream sync and was not repeated.

| Area                         | Verified result / remaining requirement                                                                                                                                                                                             |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Generation                   | Four paths share CPU TF-IDF/NMF source selection; synthetic claims, preserved source identity, no LLM fallback; 503 unavailable / 422 unsupported or exhausted                                                                      |
| Artifact operations          | Ignored ~32.54 MiB bundle must be trained or staged; exact NumPy 2.5.2 / SciPy 1.18.1 / scikit-learn 1.9.0 pins apply locally and in Docker; restart after replacement                                                              |
| Local persistence            | Fresh local PostgreSQL at `f2a3b4c5d6e7`, pgvector 0.8.6; five unique profiles read back; two existing integration tests passed; cloud DB untouched                                                                                 |
| Existing LLM flow            | Seven Freellmpool responses covered context, roles, and two interview turns with four 384-dimensional memories; not a success rate or cross-route benchmark                                                                         |
| Container                    | Windows artifact loaded and selected five profiles in Linux with networking disabled; full Compose app/web rehearsal not run in this continuation                                                                                   |
| Post-sync offline suites     | Backend 1,287 passed / 3 deselected (81.64% coverage) after the exact warning-policy correction; ML 298 passed after fixture isolation (earlier coverage 97%); frontend 269 passed / 36 files after the CSS token correction        |
| Other post-sync local checks | Ruff, `pip check`, both quiet Compose configuration checks, and all 5 trained-artifact smoke stages passed. Latest TypeScript/Vite build and theme check passed after the four-declaration CSS token correction; 0 theme violations |
| Quality and coverage         | NMF test MRR 0.432654 vs lexical 0.751621; USA-synthetic-only, 72/160 `not_in_workforce`; no validated demand, population, student/Bangladesh fit, or income/OCEAN prediction                                                       |
| Concurrency                  | Active owner-scoped source exclusions work sequentially; no transactional identity lock for overlapping independent requests                                                                                                        |
| UI and unverified checks     | Earlier desktop check passed; mobile header clipping remains unfixed and was not reverified after upstream styling or the token-only correction. Cross-conversation retrieval not run; Pyright unavailable                          |

Source, timing, and full caveats: [post-sync local verification](../ml_persona/IMPLEMENTATION_REPORT.md#post-sync-verification-2026-09-09),
[model card](../ml_persona/MODEL_CARD.md), [setup](SETUP.md#persona-ml-artifact).
Commit, push, and CI results are tracked separately in the
[implementation log](IMPLEMENTATION_PLAN.md); local passes are not publication success.

## 1. Configuration & secrets

| Item                                                                            | Status | Evidence                                                           |
| ------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------ |
| All settings env-driven (`BEBSHAX_*`), `.env.example` parity test-enforced      | ✅     | `tests/test_ops_env_parity.py` (9)                                 |
| JWT secret ≥ 32 chars, burned value rejected, demo mode refused in prod/staging | ✅     | `config.py` validators + `tests/test_production_hardening.py`      |
| No secrets in tree or `dist`                                                    | ✅     | gitleaks (CI, full history w/ allowlist), grep in review           |
| Secrets committed 2026-09-01 still in git history                               | 🔴     | **rotate Neon / Resend / Brevo SMTP / gmail app password** (human) |
| Paid routes excluded (`openrouter/auto` removed)                                | ✅     | `test_routing_hardening_openrouter_classification.py`              |

## 2. Database

| Item                                                           | Status | Evidence                                                                                                       |
| -------------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------- |
| Migrations from zero → single head `e1f2a3b4c5d6`              | ✅     | run on scratch pgvector DB this session: 33 tables, HNSW ×2, `uq_conversation_turns_conversation_turn`         |
| Inspector-guarded migrations for `create_all`-bootstrapped DBs | ✅     | migration self-tests in `tests/memory/test_persona_hardening_memory.py`                                        |
| Compose `full` runs `alembic upgrade head` before uvicorn      | ✅     | `docker-compose.yml` app `command`; `docker compose --profile full config` exit 0                              |
| pgvector integration tests                                     | ✅     | 3 passed against migrated scratch DB                                                                           |
| Study delete cascades every `study_id` table + persona chain   | ✅     | `test_api_hardening_study_delete.py` (metadata-driven)                                                         |
| Memory retrieval uses the HNSW index at query time             | ⏸️     | scores in Python after a persona-scoped fetch (small per-persona sets); index exists for future `ORDER BY <=>` |
| Backups / restore recipe                                       | 🟡     | documented `pg_dump` recipe only; no scheduled backup                                                          |

## 3. API & error handling

| Item                                                                               | Status | Evidence                                                          |
| ---------------------------------------------------------------------------------- | ------ | ----------------------------------------------------------------- |
| One error envelope `{detail, error_code, request_id}` on every non-2xx             | ✅     | `test_api_hardening_error_envelope.py`, live 404/422 smoke        |
| `X-Request-ID` on every response, one access-log line per request                  | ✅     | same; no headers/bodies/query strings logged                      |
| 500 envelope readable cross-origin (inside CORS)                                   | ✅     | `test_unhandled_500_keeps_cors_headers_for_cross_origin_spa`      |
| LLM failures → 503/413/502 with attempts and estimates                             | ✅     | tournaments C/E                                                   |
| DB unreachable → 503 `database_unavailable` (request time) and `/api/health/ready` | ✅     | `test_chaos_database_unavailable_at_request_time_returns_503`     |
| Body cap 2 MiB (uploads exempt, own 25 MB)                                         | ✅     | envelope tests                                                    |
| Pydantic bounds mirror column widths                                               | ✅     | `test_api_hardening_limits.py`                                    |
| Rate limits on every LLM-spending route; per-user job cap                          | ✅     | limits tests                                                      |
| Pagination on all list endpoints                                                   | 🟡     | provenance/memories/personas bounded; some legacy lists unbounded |

## 4. LLM routing & provenance

| Item                                                                       | Status | Evidence                                                      |
| -------------------------------------------------------------------------- | ------ | ------------------------------------------------------------- |
| Pre-flight context filter, never truncate                                  | ✅     | `tests/llm/test_context.py`, tournament E                     |
| Attempt-time all-CWE → `ContextWindowExceeded`                             | ✅     | `test_routing_hardening_exhaustion.py`                        |
| Failure taxonomy closed; quality not a kind                                | ✅     | `tests/llm/test_taxonomy.py`                                  |
| `INTERNAL_ERROR` surfaced, chain not burned                                | ✅     | routing hardening tests                                       |
| Provider-scope cooldowns for 429/quota/auth, persisted across restarts     | ✅     | cooldown scope tests, `capacity_state` round-trip             |
| Attempt budget on freellmpool                                              | ✅     | `test_routing_hardening_freellmpool_budget.py`                |
| Provenance: estimate, params, ranker markers, `via` for virtual candidates | ✅     | `test_routing_hardening_provenance.py`, real cross-route rows |
| Sink flush on shutdown; DB errors counted and logged                       | ✅     | `tests/db/test_sink.py`, chaos test                           |
| Quota caps single source of truth                                          | 🟡     | `providers.toml` (rpd 1000) vs `quota.py` (50) — unify        |

## 5. Security

| Item                                                                  | Status          | Evidence                                                                                 |
| --------------------------------------------------------------------- | --------------- | ---------------------------------------------------------------------------------------- |
| JWT HS256 pinned, exp/iss/aud enforced                                | ✅              | `auth/security.py`, tests                                                                |
| `/auth/sync` pre-hijack closed                                        | ✅              | `tests/auth/test_api_hardening_auth.py`                                                  |
| OTP scoped/invalidated/lockout                                        | ✅ (in-process) | same; DB-backed counter needed for multi-worker                                          |
| Tenancy: 404-first, write predicate on all mutations, body ids scoped | ✅              | `test_security_regressions.py`, `test_row_scoping_hardening.py`                          |
| SSRF: scheme/host/IP denylist + DNS-rebind pinning                    | ✅              | `test_api_hardening_ssrf.py`                                                             |
| Prompt injection: untrusted blocks everywhere + identity rule         | ✅              | prompt_safety tests, tournament D                                                        |
| Security headers API + SPA (nginx CSP)                                | ✅              | `main.py`, `deploy/nginx.conf` (validated with `nginx -t`)                               |
| PBKDF2 iterations                                                     | 🟡              | 100 000 (OWASP floor 600 000) — test pin `tests/test_auth.py`                            |
| Dependency audit                                                      | 🟡              | `pip-audit` baseline 0 vulns, `npm audit` 0; CI step advisory until one green Ubuntu run |

## 6. Observability

| Item                                                                   | Status | Evidence                                                                  |
| ---------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------- |
| Request ids end-to-end (header, body, log, UI "Request ID" tag)        | ✅     | tests + frontend `RequestIdTag`                                           |
| Health: liveness + `db`/`local_tier_up`/sink counters; readiness route | ✅     | live smoke                                                                |
| Structured JSON logs / metrics endpoint                                | ⏸️     | plain key=value access log; no `/metrics` (deliberately no new infra)     |
| Redaction                                                              | ✅     | `safe_error_summary`; provenance `failure_detail` redacted for non-owners |

## 7. Deployment

| Item                                                                                                    | Status | Evidence                                                       |
| ------------------------------------------------------------------------------------------------------- | ------ | -------------------------------------------------------------- |
| Compose `full`: restart policies, healthchecks (`/api/health/ready`), web waits for app, data mounts    | ✅     | `docker compose --profile full config --quiet` exit 0          |
| Non-root image, pinned minor tags                                                                       | ✅     | Dockerfiles                                                    |
| Image build rehearsal (`--profile full up --build`)                                                     | 🟡     | not run in this pass (network + minutes) — do before the venue |
| Offline venue: fonts self-hosted, Neon URL empty in `.env.demo`, preflight scans `dist` for tenant URLs | ✅     | `scripts/demo_preflight.py --strict-offline`                   |
| Two deployment stories (compose vs Vercel+hosted API) documented                                        | ✅     | `docs/SETUP.md`                                                |

## 8. Testing & CI

| Item                                                                                                                                       | Status | Evidence                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------ | ------ | ---------------------------------------------------- |
| Backend unit suite green                                                                                                                   | ✅     | 929 passed / 3 deselected (integration) — 2026-09-08 |
| Frontend suite + tsc build + theme drift gate                                                                                              | ✅     | 247 passed / 32 files; build 0 errors; theme 0 files |
| Integration (pgvector)                                                                                                                     | ✅     | 3 passed on migrated DB                              |
| Lint (`ruff` backend + scripts)                                                                                                            | ✅     | clean                                                |
| Type check                                                                                                                                 | 🟡     | pyright 79 errors, advisory in CI                    |
| CI: lint, coverage floor, alembic from zero + single head, integration, frontend test/build/theme, gitleaks, compose validation, pip-audit | ✅     | `.github/workflows/ci.yml`                           |
| Browser E2E (Playwright)                                                                                                                   | ⏸️     | none; API-level tournaments cover the flows          |

## 9. Demo mode

| Item                                                              | Status | Evidence                                                    |
| ----------------------------------------------------------------- | ------ | ----------------------------------------------------------- |
| Coherent seeded case, labelled `CACHED`, no fabricated provenance | ✅     | `tests/db/test_seed_demo_mode.py` (+8), live smoke          |
| Judge Lab gated to demo/dev, auth + limiter                       | ✅     | `tests/api/test_demo_lab_scenarios.py`                      |
| Interviews/persona generation live (Ollama offline path)          | ✅     | design; local model verified serving in the cross-route run |

## Go / no-go

**No unconditional production go.** Before an exhibition, confirm the outstanding
human security actions, stage a compatible ML artifact, and rehearse the full
Compose app/web workflow. Post-sync local checks passed as scoped above. Use an isolated
demo environment without overwriting personal secrets/settings; review the
known mobile controls defect before relying on that viewport. Present outputs
as synthetic research hypotheses with the baseline/bias limits above. Commit,
push, and CI results belong in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

</details>

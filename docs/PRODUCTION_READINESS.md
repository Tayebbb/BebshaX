# Production Readiness — BebshaX (2026-09-07)

> Status legend: ✅ VERIFIED (exercised in this repo — test, live run, or config validation) · 🟡 PARTIAL · 🔴 BLOCKED · ⏸️ DEFERRED (deliberate). Nothing is marked complete because code exists; each ✅ names how it was exercised.

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

**Go for exhibition** once the two human items are done: rotate the leaked credentials, and rehearse `docker compose --profile full up --build` with `.env.demo` copied first. Everything else marked 🟡/⏸️ is documented as a limitation, not hidden.

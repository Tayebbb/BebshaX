# Runtime Integration Handoff

Date: 2026-09-09. Owned runtime composition implemented; integrated release is
blocked by the cross-owner items below. No live-provider, PostgreSQL, server,
deployment, installation, git, commit, or push operation was performed.
Existing shared-worktree changes were preserved. No shared implementation logs
or other workers' source packages were edited.

## Delivered

- Removed runtime imports of the retired OLLAMA pool symbol from demo and
  evaluation code. Demo, chaos and offline synthetic candidates now use primary
  Freellmpool and independent OpenRouter. Total outage remains an explicit
  AllCandidatesFailed result, including the same-route connection retry.
- Configuration imports no longer read dotenv, construct Settings, exit the
  process, or mutate FREELLMPOOL_CONFIG. get_settings is the sole runtime dotenv
  reader; direct Settings construction defaults to no dotenv. Raw provider
  credentials must be supplied in the process environment by the deployment
  launcher; parsing BEBSHAX settings does not export raw provider variables.
- Lifespan validates/initializes the database before any capacity restore,
  adapter construction or feature consumer. PostgreSQL uses the foundation's
  strict source-head validation; errors abort startup in every environment.
  Restore failures do not silently reset quota/cooldowns. Startup logs redact
  driver detail. SQLite create_all remains test-only foundation behavior.
- QuotaLedger.seed_provenance receives today's full request records, including
  failed, aborted, cached and unknown-consumption observations. It is not also
  seeded with legacy aggregates. Attempt JSON retains observations, requested
  and reported models, elapsed_ms, cache flags and endpoint latency.
- Primary latency replay uses only successful, known-consumption inner
  observations, the requested model, chronological ordering and per-target caps.
  Independent OpenRouter, legacy outer latency and unknown/cache observations
  are excluded. The adapter applies its verified-catalog filter again.
- The factory receives quota_ledger, provider_config, initial_cooldowns and
  on_cooldown_change. Both the factory and PoolRouter get restored cooldowns.
  CooldownStore uses PostgreSQL/SQLite ON CONFLICT with an atomic CASE maximum,
  tracks scheduled writes, and exposes drain()/aclose()/pending_count/failed_writes.
- ProvenanceSink.persist(record) returns only after commit, marks acknowledged,
  and raises a sanitized finalization error on failure. Cancellation remains
  unknown; failed_records retains complete records for reconciliation. The
  legacy callable still queues records and reports submitted, not acknowledged.
  Submission captures immutable ownership via tenancy_context.capture_provenance_owner.
  Accounting errors cannot bypass the awaited sink. Failure never triggers a
  new provider fallback. Retained failures are process-local, not a durable outbox.
- No new persistence-status column is required: persisted rows reconstruct as
  acknowledged; missing legacy preflight estimates remain unknown. No attempts
  are invented to store top-level metadata. Exact historical preflight estimate
  replay would require a coordinator-owned estimated_tokens column if needed.
- AsyncExitStack plus finally closes registered child tasks and public feature
  close APIs, sink, adapters, cooldown writes and DB engine even on partial
  startup failure. Shared adapter instances close once. No feature-private task
  set or circular main import is required.

## Configuration

| Setting | Contract |
| --- | --- |
| BEBSHAX_PROVIDER_CONFIG_PATH | Path; default repository providers.toml; relative values resolve against the repository, not process CWD. Stage an absolute deployment path. |
| BEBSHAX_EMBEDDING_BACKEND | Literal local or freellmpool. local is deterministic 384-dimensional hash, not local LLM inference. auto and Ollama are rejected. |
| BEBSHAX_EMBEDDING_MODEL | Required explicit model for freellmpool embeddings. |
| BEBSHAX_ML_PERSONA_ENABLED | Default true. Disabled persona generation returns explicit unavailable. |
| BEBSHAX_ML_PERSONA_REQUIRED | Default false. When true, startup/readiness require available or configured manifest-preflight capability. |
| BEBSHAX_ML_PERSONA_MANIFEST_SHA256 | Optional lowercase SHA-256 of trusted metadata.json; required to enable ML in production/staging. Never derive trust from the artifact itself. |
| BEBSHAX_RUNTIME_SHUTDOWN_TIMEOUT_S | Positive bounded shutdown interval; default 15 seconds, maximum 120. |

Settings.expected_ml_persona_manifest returns the frozen
bebshax_persona_ml.provenance.ExpectedArtifactManifest. main passes
expected_manifest only when explicitly supported by the adapter constructor.
The concurrently updated MLPersonaAdapter now supports that argument.

ML startup is lazy: bounded metadata, file-name/size/runtime checks and the
optional trusted manifest checksum produce configured with validation=manifest,
model_loaded=false and reason=lazy_model_load_pending. This does NOT verify
payload hashes, model arrays, model quality or successful inference; the ML
loader owns those checks on first use. Missing/invalid metadata is unavailable.
Optional ML failure does not disable chat. Health refreshes the preflight without
loading the model; a future public readiness() method is consumed when present.

## Exact Runtime And Health APIs

- app.state.register_runtime_task(task) returns and tracks an existing asyncio
  Task, cancels/drains it before dependencies close. Feature workers must register
  their application-owned tasks or implement public aclose()/close().
- app.state.register_runtime_resource(resource) registers public cleanup once.
  InterviewEngine.aclose is now consumed automatically. MLPersonaAdapter still
  needs a public drain/close API for shielded inference and readiness for loaded
  state; main deliberately never reaches into its private task/model fields.
- app.state.provider_health_snapshot() and
  bebshax.api.health.provider_status_snapshot(app) are network-free public fleet
  snapshots for the routes owner: name, status, configured (bool or null),
  streaming_mode, recent_success, last_observed_at. Status is configured,
  available, degraded or unknown. available requires a recent non-cached governed
  success (300 seconds); registration/catalog existence alone is not healthy.
- GET /api/health: status=ok, app, version, environment, demo_mode, db,
  core_ready, schema_validated, providers, capabilities.{chat,persona_generation,
  memory_embeddings}, optional sink.{written,dropped,db_errors,pending,retained_failures}.
  local_tier_up is removed. No provider discovery or LLM call occurs.
- GET /api/health/ready: status=ready and db=ok only after core startup/schema
  validation and DB probe; otherwise 503 database_unavailable/runtime_not_ready/
  ml_persona_unavailable. Optional remote or persona unavailability is not core
  DB readiness. This is not a live provider availability guarantee.
- GET /api/health/openrouter uses the shared routing adapter only. POST /test
  retains authentication and 10/hour limit, bounds model input, binds tenant
  scope and calls OpenRouterService(shared_adapter).health_check(model=model,
  llm_service=app.state.llm_service). Fields: configured, authenticated, model,
  models, status, latency_ms, error_code, message, verified_response, catalogue,
  provider, request_id, streaming_mode. healthy maps to available; unverified or
  missing configuration maps to unknown. A primary answer never verifies OpenRouter.
- GET /api/evaluation/metrics reuses require_development_diagnostics for global
  aggregates. Adds measured schema denominators/basis, concrete-route fallback
  denominator, pool status and metrics_window. Cached/unevaluable generation is
  not schema-valid evidence; same-route retries are not provider fallback.
  local_serve_rate and loaded legacy quality gates are explicitly historical.

## Verification And Remaining Gates

- Python 3.12.9 venv, fake providers, isolated SQLite and mock PostgreSQL SQL
  compilation only. Dotenv loaders and asyncpg connections were blocked by the
  repository-local test_runtime_modernization_runner.py. All basetemps are under
  E:/BebshaX/.tmp/runtime-integration; no persistent shell environment changes.
  Shared terminal interference required editor-launched synchronous 3.12 child
  processes; the editor's 3.15 interpreter was only the launcher.
- RED/GREEN: first simulation/import repair 8 passed; persistence 7 failures to
  7 passes; config 7 failures plus a temp-directory setup issue to 8 passes;
  lifespan 11 failures to 11 passes; health 8 failures to 8 passes; evaluation
  6 new failures to 12 passes. Added owner, lazy-manifest and cache-status tests
  also observed RED then GREEN. Durable SQLite/accounting checks both passed.
- Combined owned gate: 129 passed, 4 failed in 59.49 seconds. Bug-tier Ruff
  over all 30 touched Python files passed. No full backend execution occurred.
  A later remote-embedding guard observed 2 RED failures, then the complete
  lifecycle slice passed 18 tests; this is not mislabeled as a new combined run.
  Final editor review found an offline ranker placeholder type mismatch; an
  inert FakeAdapter replaced None and all 3 simulator checks passed again.
- Full collection remains blocked: tests/evaluation/test_eval_judge_disjointness.py
  imports scripts/judge_local_interview.py, which imports retired OllamaAdapter.
  2165/2168 tests collected, 3 integration deselected, 1 collection error.
- Current source head is b1bf09c4d2e7. No PostgreSQL connection or migration was
  run. Coordinator must migrate the new ownership/snapshot/memory schema from
  other workers before startup; matching the old head alone does not add those
  columns, and runtime restore will fail closed on a missing schema column.
- Remaining failing assertions, not weakened: test_business_and_persona_and_interview_e2e
  and tournament A expect persona identity memory; api/personas.py's remember
  call must receive the verified owner and reads must use the owner's filter.
  Tournament B's durable row is invisible to the owner's provenance query:
  interview execution must bind tenant_scope(owner_id) through its LLM call
  (also stream/background paths). Unknown owners must remain private.
- test_user_studies_persistence_and_isolation expects a client-supplied
  personas_data snapshot; the tenant worker now drops that unverified snapshot.
  Its owner must reconcile that test with the canonical-reference contract.
- routes/status and routing/capacity remain exclusively tenant-worker owned;
  adopt the public network-free snapshot rather than marking candidates healthy.
- Primary activation still needs approved context-verified provider metadata.
  FreellmpoolEmbedding still uses Pool.from_default_config and has no public
  close API; startup now rejects that remote embedding path until the LLM owner
  adds build_embedding_backend(backend, model, *, provider_config: Path), passes
  the path into the embedding adapter, and adds explicit environment/cleanup
  wiring. main supplies that keyword only when the signature supports it.
  Default hash embedding works; no silent hash substitution is used for a
  requested remote backend.
- Cross-worker atomic quota reservation/reconciliation, retained-record recovery,
  live PG concurrency, real providers, frontend status-string adaptation and
  final integrated acceptance remain coordinator/owning-worker gates.
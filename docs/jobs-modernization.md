# Jobs Modernization

## Status (2026-09-10)

The jobs/domain continuation consumes the existing durable journal and e7 typed
version/source-selection contract. Current research, dataset, segmentation,
study-persona, behavioral and report entrypoints use awaited durable admission.
The concrete report, refresh, study-persona and segmentation gaps found in this
continuation are closed; this is not
production sign-off or completion of unrelated roadmap work.

| Requirement | Owned implementation | Remaining integration |
| --- | --- | --- |
| WF-01 | Owner-wide SQL admission, durable polling, research aliases, inline/background report commands, refresh snapshot replay | Live PostgreSQL multi-process admission and locking rehearsal |
| WF-02 | Persisted terminal states, fenced artifact/checkpoint writes, owner-scoped report cancellation, cleanup journal and restart tests | Real provider cancellation ambiguity and deployed shutdown/resource ordering |
| WF-03 | Research stages run behind durable admission; study projection uses revision CAS; reports retain typed input manifests and avoid replacing newer study state | Full-stack rehearsal with the parent's lifecycle and data migrations |
| M8 | Existing job journal plus dataset/persona versions and source ledger are consumed without schema edits | Migration owner remains responsible for applying and rehearsing the e7 contract on PostgreSQL |

This continuation changes only the owned jobs/datasets/evidence/studies/personas/
segmentation APIs, dataset/persona/segmentation/research/report services,
associated tests, and this handoff. It does not
edit main/configuration, jobs/runtime, ORM/db/migrations/source_ledger, LLM,
interview/memory/auth/security APIs, frontend, or ML. No dependency, environment
file, deployment, live configured database, live provider call, or Git operation was
used for verification.

### Maintenance (2026-09-10)

- Research admission records the study revision. Completion increments the
  matching revision only; a newer edit or terminal study state is preserved.
  Historical research still completes with `study_projection_applied=false`
  when it cannot advance the current study projection.
- Both report-generation routes now pass `JobContext` into the real report
  service. Synthesis intent precedes inference; report, checkpoint and matching
  study findings commit together behind the lease fence. The inline route keeps
  its 201 response contract and additionally returns the durable `job_id`.
- Report commands capture study/artifact fingerprints and existing typed
  dataset/persona version references. Changed queued inputs fail before provider
  work. Full AI context and existing provenance remain intact. Unversioned legacy
  rows are identified as such; the report path never invents lineage or writes
  source selections.
- A report completed from an older snapshot remains a historical version but
  does not overwrite newer study findings/status. Overlapping reports over the
  same unchanged inputs retain serialized version allocation and the existing
  latest-report projection behavior. Metrics disclose `study_projection_applied`
  and `published_study_revision`.
- Refresh pins the published dataset version and source fields before admission,
  rejects changed queued input before fetching, and rechecks computation-relevant
  metadata in the final transaction. Its existing durable file-publication and
  cleanup protocol is preserved.
- Identical report/refresh/persona/segmentation retries reuse the first command's saved input snapshot,
  including after their own publication advances current state. Explicit command
  changes conflict. A new generation/refresh requires a new key. Compacted payloads
  cannot silently start new work.
- Inline execution honors the durable terminal outcome after a lease is revoked;
  cancellation produces a job-state conflict instead of leaking `LeaseLost`.
- Both study-persona generation routes now carry an input-version manifest and
  `JobContext`. The existing service fences commits, persists its run reference
  before selection, and checkpoints the cohort and typed persona versions in
  the same transaction. Changed queued or in-flight inputs are rejected; source
  exclusions and cohort counts retain their existing behavior. Job poll/cancel
  reconciles active run projections to the journal's terminal state.
- Segmentation now pins its actual dataset selection, including the owner-global
  fallback, with matching published dataset version IDs and study/evidence
  fingerprints. Changed queued inputs fail before interpretation. Its separate
  failure-projection transaction is also lease-fenced, so cancellation cannot be
  overwritten by a stale worker's failure handler.
- Existing upload admission, study-delete cleanup, typed persona/source ledger,
  archive, and behavioral workflows were retained and included in scoped tests.
  Fixture repairs enable current verified synthetic owners, the extended async
  report signature, and existing e7 FK dependencies without weakening auth or
  disabling foreign keys.

## Public Integration APIs

Imports from `bebshax.api.jobs`:

- `await initialize_jobs(app) -> JobRuntime`: recover expired records and start
  the idempotent expiry-maintenance task. Does not replay runners or provider calls.
- `await startup_jobs(app) -> list[dict]`: compatible startup hook returning
  the records recovered by that call.
- `await shutdown_jobs(app)`: stop admission, cancel/drain owned work, and
  persist interruption of any still-active records owned by this runtime.
- `await start_job_async(app, kind=..., scope_id=..., user_id=..., runner=...,
  input_data=..., input_revision=..., idempotency_key=..., prepare=...)`:
  await committed admission before returning an accepted HTTP response.
- `await run_job_inline(app, ..., operation=...)`: the same durable admission and
  execution contract for a request that waits for its saved result. Persisted
  cancellation/interruption takes precedence over a stale worker exception.
- `await replay_job_input(app, ..., input_data=..., snapshot_fields=...)`:
  owner-scoped reuse of an existing command's immutable server-captured fields.
  Kind, scope, and all explicit fields must still match. This does not admit or
  run work; callers still use `start_job_async` or `run_job_inline`.
- `await prepare_job(...) -> Admission`, then `start_job(..., admission=...)`:
  two-stage compatibility for an existing runner. Preparation belongs to the
  runtime even before launch. Match the kind, scope, and authenticated owner.
- `await get_job_async(app, job_id, kind=..., scope_id=..., user_id=...)`:
  owner-scoped recovery and read; unknown or mismatched scope returns `None`.
- `await cancel_job_async(app, job_id, kind=..., scope_id=..., user_id=...)`:
  persisted, owner-scoped, idempotent cancellation. Local tasks are signalled
  immediately; other workers observe the revoked fence through heartbeat/write.
- `await running_jobs_for_user_async(app, user_id)`: durable active count.

`JobRuntime` exposes `prepare`, `start`, `startup`, `cancel`, `drain`,
`shutdown(timeout_s=10)`, and `aclose`. `drain` waits for jobs, not the perpetual
expiry task. Shutdown timeout is positive/finite and at most 60 seconds. A worker
that suppresses cancellation causes shutdown to raise after the drain budget;
it does not claim the worker has stopped. SQL cleanup still requires an available
DB and its configured transaction/statement timeouts.

The explicit `MemoryJobStore` is a test double only. Neither missing storage nor
legacy `app.state.jobs` enables an in-memory production fallback. Unprepared
synchronous starts against SQL fail closed.

## Main Lifecycle Handoff

The parent reports that `initialize_jobs` now runs before readiness. Do not
implement a second lifecycle here: `jobs/runtime.py` remains unchanged for the
lifecycle workstream. The order below remains the integration contract, not a
request to redo the parent's initialization fix.

The parent runtime already exposes `register_runtime_task` and
`register_runtime_resource`. `job_runtime(app)` uses both when it is first
constructed; `JobRuntime.aclose` does not dispose the borrowed DB engine,
providers, provenance sink, or any other feature's resources.

Required parent order:

1. Install the task/resource registration hooks and `app.state.db_sessionmaker`.
2. Validate/apply the migration through the database owner's existing process.
3. Initialize shared providers, provenance, and feature services.
4. Call `await initialize_jobs(app)` before accepting requests or setting ready.
   Registering jobs after its dependencies ensures LIFO resource cleanup closes
   jobs first.
5. On shutdown, stop accepting requests and wait for in-flight request admission.
   Call `await shutdown_jobs(app)` while DB/provenance/providers remain usable.
6. Drain the parent task registry, flush acknowledged provenance, then close
   provider clients and the DB engine.

If jobs or the parent task registry report a non-stopping worker, the parent must
not continue closing resources that worker can still use. The parent's
`AsyncExitStack` teardown owns that failure gate. Deployed teardown and real
provider shutdown were not exercised here. Choose the parent's outer timeout to allow the
jobs drain budget plus short DB cleanup; an outer cancellation is not a successful
drain.

Startup and periodic recovery touch only expired active records. Shutdown selects
by the fresh per-runtime worker ID; it does not clear all jobs, expire another
worker's healthy lease, or dispose shared resources. A restart before the prior
lease expires can temporarily see `running`; expiry maintenance or polling
eventually persists `interrupted`, without submitting another inference request.

## Command, Deadline, and Checkpoint Contract

- At most three `queued`/`running` commands per owner across cooperating store
  instances, regardless of feature or study. PostgreSQL admission first inserts
  the owner row with conflict handling and then updates it in the admission
  transaction, serializing the count and insert. Identical retries consume no
  extra slot, even at the limit.
- Default deadline: 600 seconds. Existing trusted per-call overrides remain
  supported, bounded to positive finite values no greater than 3,600 seconds.
  Behavioral trigger/retry use the 600-second default. Lease duration defaults
  to 60 seconds and is bounded to 300; workers must have synchronized UTC clocks.
- `(owner_id, idempotency_key)` identifies one command. Kind, scope, canonical
  JSON input hash, and exact input revision must agree on reuse, including after
  completion, interruption, or payload compaction. Different inputs conflict.
  A missing key creates a new command; automatic network retries need a key.
- `input_revision` should identify an immutable input manifest. If omitted, the
  canonical input hash is the revision, which does not pin external mutable
  entities. Callers must include persona versions, script revision, scenario,
  membership, and other influencing parameters or immutable references.
- Input/result journal snapshots are JSON-only, finite, and at most 2 MiB.
  Larger results belong in their feature tables with immutable `result_refs`.
- `prepare(session, job)` performs short DB-only preparation in the admission
  transaction and returns result references. It must not call an LLM, await
  network I/O, commit the supplied session, or hold it during inference.

Runners receive a `JobContext`, compatible with the existing job dictionary:

1. Materialize and verify immutable input using a short session; close it.
2. `await job.begin_item(item_key, input_data=...)` commits the intent before a
   non-idempotent/provider step. A completed item returns saved references;
   an unfinished item raises `UncertainItem` instead of replaying it.
3. Await the existing governed LLM service outside any DB transaction.
4. In a short feature transaction, call `await job.fence(session)`, save the
   artifact, and `await job.complete_item(item_key, result_refs=..., session=session)`.
   Artifact and checkpoint must commit together. The helper does not commit the
   caller's session. An expired/wrong owner/token/attempt cannot finalize.
5. Set `job['result']` and/or `job['result_refs']`. Returning with unfinished
   checkpoints persists `interrupted` / `job_outcome_uncertain`, not completion.

`FencedSession.commit()` is available for existing session-based runners, but
direct commits on its underlying session or delegated transaction context managers
are not automatically fenced. Prefer the explicit short-transaction contract above.

The journal's attempts are worker attempts, not authoritative provider billing
records. A started/uncertain checkpoint means an external call might have run.
This cannot prove exactly-once provider execution or stop an already-dispatched
request. Recovery never replays it automatically. An explicit reviewed retry
uses a new command key and must reuse/check saved artifacts through the owning
engine. Physical provider/thread concurrency remains the owning engine/router's
responsibility; durable admission counts active commands, not remote requests
that cannot be forcibly cancelled.

## Persona API

`POST /api/studies/{study_id}/personas/generate` and its `/jobs` variant share
durable admission, saved input-version replay and fenced cohort persistence.
The inline route preserves its 201 payload and includes `job_id`. The job route
returns 202 and retains the existing polling URL. The new cancel route is
`POST /api/studies/{study_id}/personas/generate/jobs/{job_id}/cancel`.

`PersonaGenerationService.create_generation_run` accepts optional keyword-only
`job` and `expected_input_versions`; existing non-job callers keep their public
behavior. Production persona selection remains the CPU selector, not an LLM.
This work does not alter its source identity, context or trained model.

## Report API

Both routes are journal-backed:

- `POST /api/studies/{study_id}/reports/generate`: waits for the persisted result.
- `POST /api/studies/{study_id}/reports/generate/jobs`: returns durable acceptance.
- `GET /api/studies/{study_id}/reports/generate/jobs/{job_id}`: provider-free polling.
- `POST /api/studies/{study_id}/reports/generate/jobs/{job_id}/cancel`: owner-scoped,
  persisted, idempotent cancellation. It cannot undo an already dispatched remote
  request, but a revoked worker cannot publish its report.

Job input, synthesis checkpoint and report metrics carry the captured input
versions. Dataset references follow the published pointer/hash, not simply the
highest version number. Study/artifact comparison occurs again at publication;
the manifest retains the honest `captured_inputs_not_database_version_freeze`
label because this does not claim a database-wide historical snapshot.

## Behavioral API

Trigger and retry require authenticated ownership and use `start_job_async`.
The obsolete private task registry has been removed. The trigger pins a persona
ID/version manifest and test/scenario revision, rechecks it during preparation,
and persists the run reference with admission. Retry snapshots the run's scenario,
manifest, and population; full engine-side lineage/finalization remains the
lineage integrator's responsibility.

Bounds: 50 personas, persona IDs at most 64 characters, scenario text at most
10,000 characters, title at most 256, parameters at most 64 KiB/2,048 JSON values/
eight nesting levels. Stored fallback scenarios are checked too. Shared owner
admission remains three jobs in addition to the existing route rate limits.

New route:

`POST /api/studies/{study_id}/behavioral-tests/runs/{run_id}/cancel`

It checks study/run ownership, persists journal cancellation, then reconciles the
run with a job-ID/status conditional update. Historical runs without a managed
job return a conflict. Polling reconciles interrupted/cancelled/timed-out active
run projections and exposes `job_state`, `job_error_code`, redacted checkpoint
references, and `provider_outcome_unknown`, without inference. The journal is
canonical if a crash occurs between journal and domain projection updates.

## Migration Handoff

The migration agent owns Alembic and ORM registration. Import
`bebshax.jobs.orm` in its metadata/upgrade path; do not recreate shared `Base`.

Required changes relative to the existing job ORM:

- `durable_jobs.input_revision`: `VARCHAR(255) NOT NULL`; backfill existing jobs
  from `input_hash` before applying `NOT NULL`.
- `durable_jobs.payload_expired_at`: nullable `TIMESTAMP WITH TIME ZONE`.
- Replace `uq_job_idempotency(owner_id, kind, scope_id, idempotency_key)` with
  `uq_job_idempotency(owner_id, idempotency_key)`. Preflight legacy cross-scope
  collisions; do not silently delete jobs or rename keys to satisfy uniqueness.
- `worker_id` also identifies a prepared/queued job's submitting runtime. Existing
  nullable storage is sufficient; no additional column is required.
- Status storage must accept `queued`, `running`, `completed`, `failed`,
  `cancelled`, `interrupted`, and `timed_out`; checkpoint states are `started`,
  `completed`, and `uncertain`.

For installations without the journal, create the ORM's `job_owners`,
`durable_jobs`, `job_attempts`, and `job_checkpoints` tables, owner/status and
status/lease-expiry indexes, owner FK, and cascading attempt/checkpoint job FKs.
Keep the pre-existing `JobFileCleanup` mapping intact; it was not changed here.
The ORM is the column/type source of truth. Entity deletion must not cascade away
active commands without coordinating cancellation/recovery first.

`SQLJobStore.compact_terminal(before=UTC_datetime, limit=100)` is explicit, bounded
retention, not an automatic deletion policy. It removes old terminal input/result
payloads but keeps command keys/hashes/revisions, outcomes, references, attempts,
and checkpoint states. Polling exposes `payload_expired_at`. Active jobs are never
selected. An old key still returns its original job after compaction; it cannot
accidentally dispatch new work. Account erasure/backup retention is separate work.

## Verification

Verification uses the explicit Python 3.12 venv and
`apps/backend/tests/jobs/run_domain_checks.py`. It disables dotenv loading and
isolates application settings inside the test child process, while allowing
fixtures to supply temporary SQLite databases and fake providers. It does not
mutate the shared PowerShell environment. Per-run stdout, JSON exit receipts and
coverage artifacts use `.domain-<label>` names in the jobs test directory.

Final production-code verification: **324 passed, 1 intentionally deselected**
(`main_wires` belongs to the untouched parent lifecycle), **426.71 seconds**,
pytest **exit 0**, receipt `tests/jobs/.domain-domain-verified.json` and output
`tests/jobs/.domain-domain-verified.stdout`. Three additional in-flight persona
invalidation cases then passed in **15.67 seconds**, pytest **exit 0**, receipt
`tests/jobs/.domain-domain-input-edges.json`. The runs are disjoint: **327 passed
total**. No production code changed between them. The continuation adds **46
parameterized regression cases** in total.

Combined coverage over the 41 touched functions and nested runners: **704/871
statements, 80.83%**; **184/276 branches**; statement-plus-branch **77.42%**.
This is measured function-scope coverage, not exact changed-line coverage. No
pre-change baseline/delta is claimed. The two generated coverage JSON reports
contain the underlying line/branch receipts. Bug-tier Ruff and editor diagnostics
passed for every changed Python file; handoff diagnostics and local Markdown
link checks passed too.

Focused continuation receipts (overlap the final gate; do not add these counts):

| Label | Scope | Result | Exit |
| --- | --- | --- | --- |
| `report-workflows-final` | Report workflows and existing async API contracts | 21 passed | 0 |
| `refresh-publication-green` | Both refresh routes: queued changes, publication fencing, replay | 6 passed / 15 deselected | 0 |
| `research-double-contract` | Real research runner CAS with autospecced async doubles | 3 passed / 18 deselected | 0 |
| `inline-final` | Inline terminal-state handling and SQL/memory snapshot replay | 12 passed | 0 |
| `behavioral-fixture-complete` | Isolated behavioral job contracts with e7 metadata registered | 8 passed | 0 |
| `persona-final` | Both persona routes: fences, stale inputs, cancellation, restart replay | 8 passed | 0 |
| `persona-compatibility` | Existing async API and selector contracts | 61 passed / 1 deselected | 0 |
| `segmentation-green` | Typed inputs, stale queued study, remote cancellation | 3 passed / 21 deselected | 0 |

The earlier combined `scoped-final-complete` receipt passed **249 tests** in
251.47 seconds, exit **0**, before the final persona/segmentation additions.
The final receipts above supersede its coverage figures.

The final combined command is scoped to jobs, dataset publication/lineage,
behavioral lineage, research lineage, report fidelity/versioning and async job
API contracts plus persona selector and segmentation compatibility. It
deliberately does not invoke the full backend suite. Coverage
for entire legacy modules is not a changed-code or repository-wide coverage gate.

```powershell
& ./.venv/Scripts/python.exe -B apps/backend/tests/jobs/run_domain_checks.py domain-verified `
  apps/backend/tests/jobs apps/backend/tests/api/test_async_generation_jobs.py `
  apps/backend/tests/api/test_ml_persona_generation_contracts.py `
  apps/backend/tests/datasets/test_dataset_publication_durability.py `
  apps/backend/tests/test_modernization_lineage_research.py `
  apps/backend/tests/test_modernization_lineage_datasets.py `
  apps/backend/tests/test_modernization_lineage_behavioral.py `
  apps/backend/tests/test_modernization_lineage_reports.py `
  apps/backend/tests/test_exhibition_report_versioning.py `
  apps/backend/tests/test_exhibition_report_fidelity.py `
  apps/backend/tests/test_report_field_normalization.py `
  apps/backend/tests/test_segmentation_engine.py -k "not main_wires" -q `
  --cov=apps/backend/bebshax --cov-branch `
  --cov-report=json:apps/backend/tests/jobs/.domain-domain-verified.coverage.json `
  --cov-fail-under=0
```

This command now includes the three added edge cases as well. Their separately
recorded focused invocation was:

```powershell
& ./.venv/Scripts/python.exe -B apps/backend/tests/jobs/run_domain_checks.py domain-input-edges `
  --confcutdir=apps/backend/tests/jobs apps/backend/tests/jobs/test_domain_persona_commands.py `
  -k inflight_input_change -q --cov=apps/backend/bebshax --cov-branch `
  --cov-report=json:apps/backend/tests/jobs/.domain-domain-input-edges.coverage.json `
  --cov-fail-under=0
```

Use the filesystem coverage source shown above. Two attempted invocations with
multiple nested package-name sources returned pytest exit 4 before collection
(`NumPy: cannot load module more than once per process`). A seven-test filesystem
coverage probe passed, exit 0, without dependency or application changes.

Remaining integration dependencies are external to this local verification:
the data owner must apply/rehearse e7 and journal constraints on PostgreSQL;
real multi-process lock/deletion contention, remote provider outcomes, deployed
restart/shutdown resource ordering, and a complete authenticated frontend journey
were not exercised. SQLite transactions/FKs and compiled PostgreSQL statements
are not evidence that these deployment gates passed. No additional schema change
was required for the implemented domain workflows.

Changed implementation files:

- `apps/backend/bebshax/api/jobs.py`
- `apps/backend/bebshax/api/datasets.py`
- `apps/backend/bebshax/api/evidence.py`
- `apps/backend/bebshax/api/studies.py`
- `apps/backend/bebshax/api/personas.py`
- `apps/backend/bebshax/api/segmentation.py`
- `apps/backend/bebshax/datasets/service.py`
- `apps/backend/bebshax/personas/service.py`
- `apps/backend/bebshax/segmentation/service.py`
- `apps/backend/bebshax/research/service.py`
- `apps/backend/bebshax/research/report_service.py`

Changed/added tests and tooling: `tests/jobs/test_feature_job_entrypoints.py`,
`tests/jobs/test_domain_report_commands.py`, `tests/jobs/test_domain_persona_commands.py`,
`tests/jobs/test_inline_job_commands.py`, `tests/jobs/conftest.py`,
`tests/jobs/run_domain_checks.py`, and `tests/api/test_async_generation_jobs.py`
(all relative to `apps/backend/`). Test receipts are generated evidence, not
production files. Independent reviewer tooling was unavailable in this session;
the parent should route this bounded change through its normal code/security
review before integration.

### Historical Jobs-Only Verification (2026-09-09)

Owned suite: **38 passed** (6.94 seconds in the recorded full owned-slice run).
Repository bug-tier Ruff checks passed for jobs, both owned APIs, and the new
tests. Editor diagnostics were clean for all six owned implementation files.
Tests use isolated repo-local SQLite files with foreign keys enabled, explicit
fakes, and a minimal FastAPI app. The behavioral fixture disables dotenv-file
loading and injects synthetic authentication; it does not validate the real auth
provider/session stack. Temporary database files are owned by each fixture.

Run from the repository root using the existing venv:

```powershell
& ./.venv/Scripts/python.exe -B -m pytest -c apps/backend/pyproject.toml --confcutdir=apps/backend/tests/jobs apps/backend/tests/jobs -q -p no:cacheprovider
```

Test files: `test_job_journal.py`, `test_job_recovery.py`,
`test_job_runtime_recovery.py`, `test_job_memory_contract.py`,
`test_job_postgresql_contract.py`, and `test_behavioral_job_contract.py`, all
under `apps/backend/tests/jobs/` with shared fixtures in its `conftest.py`.

PostgreSQL checks compile the schema, owner lock, conditional claim/fence,
`FOR UPDATE SKIP LOCKED` recovery, and terminal-only compaction. They do not
execute PostgreSQL or prove real multi-process concurrency. Full backend tests,
live DB/service operations, real provider calls, main/studies/personas integration,
migration rehearsal, and production resource-close behavior were not run.

The shared PowerShell terminal interrupted early verification attempts; the same
tests were subsequently run in separate one-shot child processes with captured
output. No commit, push, deployment, or broad roadmap status update was performed.
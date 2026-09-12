# Durable Jobs And Dataset Publication

Updated: 2026-09-10. Scope: owned job, research, behavioral, dataset, and direct feature API repairs. This is scoped implementation evidence, not a production or PostgreSQL multi-process certification.

## Delivered Behavior

- SQL admission is owner-scoped across job kinds, with a three-active-job limit, immutable input hashes/revisions, and owner-scoped idempotency keys. Reusing a key with different input produces HTTP 409.
- Workers claim fenced leases. Domain writes and item checkpoints require the current owner, attempt, token, lease, and deadline. A cancelled or late worker cannot acknowledge success, even if its runner suppresses cancellation.
- Claim transactions settle before cancellation propagates. Shutdown cancels and drains registered workers before resources can close; an uncooperative worker produces an explicit shutdown failure. Sibling behavioral tasks are cancelled and drained after batch failures.
- Polling reads the journal, not a process-local task registry. Missing or expired leases become interrupted; timed-out jobs are distinct. Unfinished checkpoints become uncertain and are never automatically replayed against an LLM.
- Behavioral runs/retries use durable admission and captured persona versions. Retry results, aggregates, insights, and checkpoints commit atomically. Existing completed results/history are retained. Native legacy cancellation clears the execution token without claiming an external provider request was stopped.
- Behavioral prompts retain every supplied owned interview insight, evidence claim, segment characteristic, and dataset reference. Dataset persona prompts retain all supplied sample records. Tenant filters remain in place; no weaker-model or cached-content fallback was added.
- Dataset upload, URL ingestion, refresh, candidate import, and persona generation now use the journal, including nested study routes. Final domain writes and checkpoints share a fenced transaction.
- Version files are immutable, exclusively created, and fsynced before pointer publication. A file-intent record is committed before writing; the content hash is acknowledged only after writing completes. A live publication lease is consumed in the transaction that retains the version.
- Failed/cancelled publications retain cleanup intent, including partial files and copied legacy versions. Erasure is bounded, leased, ownership/hash checked, retryable after file errors, and rechecks previously shared files after the last reference is removed.
- Dataset CPU admission remains held until the actual thread exits, including repeated cancellation. The app reuses its dataset service instead of constructing unmanaged fallback database engines.
- Existing parser cell, byte, nesting, node, archive, XML, and shared-string budgets are preserved. Missing optional XLSX support returns HTTP 415 with `dataset_format_unsupported`; nothing was installed.
- Research captures detached inputs before releasing read transactions, accepts a prepared run ID, and persists stage checkpoints. Its owned search client has an idempotent close hook; borrowed clients remain their owner's responsibility.

## Runtime Contract

Implementation: [job API](../apps/backend/bebshax/api/jobs.py), [runtime](../apps/backend/bebshax/jobs/runtime.py), [SQL store](../apps/backend/bebshax/jobs/store.py).

Use `await start_job_async(app, kind=..., scope_id=..., user_id=verified_owner, input_data=..., runner=..., idempotency_key=..., input_revision=...)` before acknowledging background work. `prepare(session, job)` may insert a domain run and return artifact references in the same transaction as admission. It must not commit the caller's transaction or perform network work.

The runner receives a `JobContext`, which remains dictionary-compatible. Call `begin_item(item_key, input_data=...)` before a non-replayable step. Call `complete_item(item_key, result_refs=..., session=transaction_session)` in the transaction that saves its output. `fence(session)` protects other writes. Set `job['result_refs']` to committed artifact references and `job['result']` to the complete response, not a truncated substitute.

`run_job_inline(...)` provides the same admission and replay contract for APIs retaining synchronous result shapes. Request cancellation does not orphan its managed worker. A duplicate active job on another runtime returns an explicit conflict with its job ID; a completed duplicate returns its saved result.

Use `await get_job_async(...)` and `await cancel_job_async(...)` with verified owner, kind, and scope. Legacy synchronous getters cannot read SQL-backed jobs. Public `status` retains the compatibility values `running`, `completed`, and `failed`; `state` distinguishes `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`, and `timed_out`.

An uncertain checkpoint means the operation's outcome is not fully acknowledged. It does not prove that a provider consumed tokens. Completed checkpoints contain immutable result references. Retention may expire large input/result payloads while preserving audit identity and references; callers must handle expired results explicitly.

## API Contracts

| Family | Command And Response | Persisted Poll / Cancellation |
| --- | --- | --- |
| Research | `POST /api/studies/{study_id}/research` now returns **202** with the queued run object, `id`, and `job_id`; repeated idempotency keys return the same run | `GET .../research/jobs/{job_id}`; `POST .../research/jobs/{job_id}/cancel`; run detail also reconciles interruption |
| Segmentation | Existing `POST .../segmentation` result stays `{run, segments}` with added `job_id` | `GET .../segmentation/jobs/{job_id}`; `POST .../segmentation/jobs/{job_id}/cancel`; run detail reconciles interruption |
| Datasets | Upload/URL/refresh/import/persona result fields are retained with added `job_id`; mutations require authenticated owners | `GET /api/datasets/jobs/{job_id}?kind=dataset_upload&scope_id=...`; same path with `/cancel` for POST |
| Behavioral | Existing create-run/retry responses retain their run IDs and include durable `job_id` | Existing run detail/results and cancel routes reconcile persisted journal state |

Dataset kinds are `dataset_upload`, `dataset_url`, `dataset_refresh`, `dataset_import`, and `dataset_personas`. Upload/URL scope is the study ID, or owner ID for a standalone dataset. Refresh/persona scope is the dataset ID. Candidate import scope is the study ID. Research uses `research_generation`; segmentation uses `segmentation`; both use study scope. Behavioral uses `behavioral_simulation` and study scope.

Clients must retain the accepted IDs and use persisted polling after reconnect. The separate `/api/studies/{study_id}/research/run` alias belongs to the studies owner and is not changed by this work.

## Domain And Main Handoffs

- **WF-01 / WF-02 / M8:** main should call `await initialize_jobs(app)` after database readiness and before accepting commands, enabling periodic expired-lease recovery. Lazy runtime creation already consumes `app.state.register_runtime_task` and `register_runtime_resource`.
- **WF-02 / M8:** stop admission and await `shutdown_jobs(app)` before closing LLM clients or the database. Runtime `aclose()` delegates to shutdown. If shutdown reports remaining workers, do not close resources they still use. Full application shutdown ordering was not tested in this owned-only run.
- **WF-03:** the studies owner's `/research/run` alias still directly awaits `ResearchEngineService.run_study_research`. Route it through the same durable acceptance contract. The engine signature is `run_study_research(session, study, user_id=..., *, job=None, run_id=None)`. A supplied `run_id` must identify an owned `queued` run; background admission must create that row atomically.
- **SEC-14 / DB-03 / M3:** schedule bounded `DatasetService.cleanup_pending_files(limit=100)` at startup and periodically in a registered runtime task. Immediate deletion cleanup is wired; crash/rollback cleanup survives in SQL but needs this periodic consumer. Study/account deletion must call `enqueue_dataset_cleanup(session, dataset)` inside its deleting transaction before cascading rows.
- **DB-06 / WF-07:** segmentation engine files were outside the authorized ownership list. The API wrapper fences its commits and records run/checkpoint references, and the existing rollback regression passes. The engine still owns deterministic clustering, its evidence snapshot breadth, and short-transaction/threading refinements.
- **DB-04 / M4:** typed persona origins remain a shared-model/domain-owner decision. Current dataset persona writes still use `Personas.generation_run_id = DatasetPersonaRuns.id` and a dataset-local key in `Personas.segment_id`. Do not add FKs from those legacy values blindly to unrelated generation/market-segment tables. Proposed explicit contract for coordination: `dataset_persona_run_id` referencing `dataset_persona_runs.id`, `dataset_version_id` referencing `dataset_versions.id`, and `dataset_segment_key` for the local key. These proposed columns were **not** added or silently emulated here.
- **DB-02 / M3:** behavioral input manifests reject changed persona versions before execution/retry. Full historical persona snapshot capture and cross-feature typed lineage remain the persona/data owners' responsibility.
- **WF-01 / M8 / SEC-14:** real PostgreSQL independent-worker admission/fencing, process-kill recovery, shared-file races, deployment cleanup scheduling, and retention policy require integration verification. SQLite and PostgreSQL SQL compilation are not substitutes.

## Exact Persisted Fields

No new shared-model properties were added in this repair. The existing worktree migration `c6f8a2d4e901_modernization_schema_parity` includes the following owned structures; `alembic/env.py` calls `get_metadata()`, which imports `bebshax.jobs.orm`, `bebshax.datasets.orm`, and `bebshax.behavioral.orm`. No missing ORM import was found. Migration application/catalog parity was not run here.

- `job_owners`: `owner_id`, `revision`.
- `durable_jobs`: `id`, `owner_id`, `kind`, `scope_id`, `idempotency_key`, `input_hash`, `input_revision`, `input_data`, `status`, `attempts`, `worker_id`, `lease_token`, `lease_expires_at`, `deadline_at`, `started_at`, `finished_at`, `payload_expired_at`, `result`, `result_refs`, `error`, `error_code`. Unique `(owner_id, idempotency_key)`.
- `job_attempts`: composite key `(job_id, number)`, plus `worker_id`, `lease_token`, `status`, `started_at`, `finished_at`.
- `job_checkpoints`: composite key `(job_id, item_key)`, plus `input_hash`, `input_data`, `status`, `result_refs`, `lease_token`, `updated_at`.
- `job_file_cleanup`: `id`, `dataset_id`, `owner_id`, `file_path`, `content_hash`, `status`, `attempts`, `lease_token`, `lease_expires_at`, `error_code`, `created_at`, `completed_at`. It intentionally has no dataset FK, so deletion cannot erase its cleanup work.
- `dataset_versions`: `id`, `dataset_id`, `owner_id`, `version`, `content_hash`, `records_hash`, `file_path`, `original_file_path`, `file_type`, `row_count`, `column_count`, `schema_metadata`, `statistics`, `segments`, `created_at`. Unique `(dataset_id, version)`.
- `behavioral_test_runs`: nullable `job_id`, `execution_token`, `input_manifest`; `behavioral_test_results`: unique `(test_run_id, persona_id)`. `BehavioralTests.owner_id` is a property alias for existing `user_id`, not a database column.

Canonical output references emitted now:

| Operation | Reference Fields |
| --- | --- |
| Research/segmentation/behavioral job | `run_id` |
| Behavioral item | `result_id`, `run_id`, `status` |
| Uploaded or changed dataset | `dataset_id`, `version_id` |
| Unchanged refresh | `dataset_id`, `content_hash` |
| Candidate import | `dataset_id`, `candidate_id` |
| Dataset persona cohort | `dataset_id`, `run_id`, `persona_ids` |

Research's domain link is `ResearchRuns.step_progress['summary']['job_id']`; segmentation's is `SegmentationRuns.configuration['job_id']`. Behavioral has its dedicated `job_id` column. Domain links and job result references must remain owner/study-consistent.

## Verification

Final run: **179 passed, 1 skipped**, 68.41 seconds, exit 0. Invocation UUID: `8d8480e3-a37a-4408-bc3d-edba91a15798`. The skip is successful optional-openpyxl parsing when the dependency is absent; archive/preflight and explicit missing-reader refusal tests ran. No dependency was installed.

Command used from the repository root:

```text
node apps/backend/tests/jobs/run_owned_checks.cjs final-owned-runtime apps/backend/tests/jobs apps/backend/tests/behavioral apps/backend/tests/research apps/backend/tests/test_modernization_lineage_behavioral.py apps/backend/tests/test_modernization_lineage_datasets.py apps/backend/tests/test_modernization_lineage_research.py apps/backend/tests/test_modernization_lineage_transactions.py apps/backend/tests/test_exhibition_dataset_parser.py apps/backend/tests/datasets/test_modernization_input_parser_budgets.py apps/backend/tests/datasets/test_dataset_publication_durability.py apps/backend/tests/datasets/test_persona_hardening_datasets.py apps/backend/tests/datasets/test_persona_hardening_research.py -q
```

The runner asserts the workspace Python 3.12 interpreter, disables dotenv reads before application imports, uses unique workspace-local temporary directories, and saves JUnit, stdout/stderr, process IDs, elapsed time, and exit status under `.tmp/owned-<label>/<UUID>/`. Shared-console interference caused earlier discarded/incomplete runs; only the recorded completed run above is the final verdict.

Changed Python surfaces passed the project's bug-tier Ruff checks. Touched runtime files and the lineage behavioral test had no editor diagnostics at the final check. No full-backend run, PostgreSQL service, real LLM, dependency installation, Git operation, or deployment was performed.

## Changed Files

Production: [jobs/runtime.py](../apps/backend/bebshax/jobs/runtime.py), [jobs/store.py](../apps/backend/bebshax/jobs/store.py), [api/jobs.py](../apps/backend/bebshax/api/jobs.py), [api/behavioral.py](../apps/backend/bebshax/api/behavioral.py), [api/datasets.py](../apps/backend/bebshax/api/datasets.py), [api/evidence.py](../apps/backend/bebshax/api/evidence.py), [api/segmentation.py](../apps/backend/bebshax/api/segmentation.py), [behavioral/engine.py](../apps/backend/bebshax/behavioral/engine.py), [datasets/parser.py](../apps/backend/bebshax/datasets/parser.py), [datasets/service.py](../apps/backend/bebshax/datasets/service.py), [research/service.py](../apps/backend/bebshax/research/service.py).

Tests and harness: [job runtime recovery](../apps/backend/tests/jobs/test_job_runtime_recovery.py), [inline commands](../apps/backend/tests/jobs/test_inline_job_commands.py), [feature entrypoints](../apps/backend/tests/jobs/test_feature_job_entrypoints.py), [owned runner](../apps/backend/tests/jobs/run_owned_checks.cjs), [behavioral lineage](../apps/backend/tests/test_modernization_lineage_behavioral.py), [dataset publication](../apps/backend/tests/datasets/test_dataset_publication_durability.py), [parser budgets](../apps/backend/tests/datasets/test_modernization_input_parser_budgets.py), [dataset persona quality](../apps/backend/tests/datasets/test_persona_hardening_datasets.py), [behavioral hardening](../apps/backend/tests/behavioral/test_api_hardening_behavioral.py), [research resource lifecycle](../apps/backend/tests/research/test_research_resource_lifecycle.py).
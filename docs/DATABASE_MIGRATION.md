# BebshaX Database Migration & Dynamic Switching Guide

BebshaX uses **Alembic as the source of PostgreSQL schema truth**. Production
startup validates the revision and reflected schema; it does not create tables and stamp them as
migrated. SQLite `create_all` remains available for isolated tests and local
fixtures, without an Alembic stamp.

---

## 1. Schema initialization on startup

When the backend starts (`uvicorn bebshax.main:app`), [`init_database`](../apps/backend/bebshax/db/engine.py) runs and:

1. Registers the shared metadata through `get_metadata()`, explicitly importing
   auth, behavioral, datasets, interview, jobs, memory, persona, and persona-version
   mappings. Registration does not depend on importing the application.
2. For PostgreSQL, requires exactly the checked-in Alembic head. Empty,
   unversioned, behind-head, unknown, or multiple-head databases fail closed before
   seeding. Startup creates neither PostgreSQL tables nor extensions nor revision
   markers. After the revision check, read-only Alembic comparison checks table,
   column, type, index and supported constraint differences; named CHECK presence
   and HNSW methods/operator classes are inspected explicitly. A head marker alone
   is insufficient. This is not a validation of all historical CHECK expressions,
   server defaults, or existing row integrity. Alembic creates the `vector`
   extension inside its migration transaction.
3. For SQLite fixtures, creates the registered tables without stamping them.
   PostgreSQL-only HNSW indexes are omitted on SQLite.
4. Ensures shared-tenant users when a session factory is supplied, and runs demo
   seeding only when requested and permitted by `BEBSHAX_DEMO_MODE`. Seed failures
   are logged without private driver details.

---

## 2. Apply migrations with Alembic

Configure `BEBSHAX_DATABASE_URL` through the approved secret mechanism. Do not
put a real connection string into command history, documentation, or test output.
Back up an existing database before upgrading. From the repository root:

```powershell
Set-Location apps/backend
../../.venv/Scripts/python -m alembic current
../../.venv/Scripts/python -m alembic upgrade head
../../.venv/Scripts/python -m alembic current
```

The current integration chain ends in:

```text
a9c2e7b6d410 -> b1bf09c4d2e7 -> c6f8a2d4e901 -> d4e6f8a0b219 -> e7a9c1d3f205 -> f2b4d6e8a013
```

`a9c2e7b6d410` is the pre-modernization baseline. The pre-existing
`b1bf09c4d2e7` HNSW repair was preserved; its application status was not inferred
from Git status. The initial integration revision is
[c6f8a2d4e901_modernization_schema_parity.py](../apps/backend/alembic/versions/c6f8a2d4e901_modernization_schema_parity.py).
The earlier 2026-09-10 continuation added the forward revision
[d4e6f8a0b219_durable_provenance_context.py](../apps/backend/alembic/versions/d4e6f8a0b219_durable_provenance_context.py).
The data-integrator follow-up adds
[e7a9c1d3f205_persona_source_ledger.py](../apps/backend/alembic/versions/e7a9c1d3f205_persona_source_ledger.py)
after it, retaining one head.
The current continuation adds only
[f2b4d6e8a013_report_version_integrity.py](../apps/backend/alembic/versions/f2b4d6e8a013_report_version_integrity.py)
after that ledger revision. It enforces positive report versions and unique
`(study_id, version)` pairs without changing report columns or historical rows.
No historically applied revision was rewritten. On 2026-09-10 the owner explicitly
confirmed that `c6f8a2d4e901` has never been applied to a user database and approved
its pre-deployment memory-owner correction. This is not a general permission to
edit an installed revision.

For an unversioned or manually bootstrapped schema, stop and reconcile its actual
schema and data with a reviewed revision before any explicit stamp. The presence
of tables alone is not proof that a revision was applied. The historical migration
helper is not a substitute for the Alembic upgrade command.

Programmatic tooling can pass an existing SQLAlchemy connection through
`Config.attributes["connection"]`, or an explicit URL through
`Config.attributes["database_url"]`. Those paths do not consult application
settings. Application URL-override behavior was not changed.

---

## 3. Integrated schema and data preservation

The current declarations contain **42 tables, 617 columns, 113 declared indexes,
and 97 constraints** across **35 migration revisions**, measured on 2026-09-10.
The source-ledger revision preserved the prior 41-table, 600-column, 107-index
schema and added one table, three persona columns, and six indexes. The report
revision adds two constraints, not columns or declared indexes; PostgreSQL's
unique-constraint backing index is not included in the declared-index count.
These are source/metadata counts, not a live catalog certificate. Revision
`c6f8a2d4e901` freezes the nine existing feature-owned tables: `auth_sessions`,
`auth_rate_limits`, `job_owners`, `durable_jobs`, `job_attempts`, `job_checkpoints`,
`job_file_cleanup`, `dataset_versions`, and `persona_versions`. It does not import
runtime ORM definitions to construct migration DDL.

The initial integration adds twelve columns to existing tables:

| Table | Columns |
| --- | --- |
| `users` | `role`, `legacy_tokens_revoked_at` |
| `email_verification_tokens` | `purpose`, `failed_attempts`, `session_version` |
| `studies` | `revision` |
| `conversations` | `persona_snapshot` |
| `memory_items` | `owner_id` |
| `llm_requests` | `owner_id` |
| `behavioral_test_runs` | `job_id`, `execution_token`, `input_manifest` |

Revision `d4e6f8a0b219` adds six `llm_requests` columns: `study_id`,
`data_classification`, `processing_policy_id`, `processing_provider_allowlist`,
`processing_openrouter_upstreams`, and `estimated_tokens`. Historical rows retain
NULL study/policy/estimate, `unknown` classification, and empty allowlists. These
are unspecified historical values, not retroactive processing approval. Existing
owners, attempts, and artifacts are not rewritten. The classification CHECK is
added `NOT VALID` then validated on PostgreSQL; no owner or study FK is introduced
for failed-generation provenance. Pre-created column shape conflicts stop before
adding any columns.

The initial revision includes the declared job idempotency, dataset-version uniqueness,
persona-version primary key/checks, refresh-token hash uniqueness, memory-owner
deduplication, behavioral result uniqueness, user-role check, foreign keys, and
supporting indexes. Existing new tables are checked against frozen column and
constraint shapes rather than silently skipped; missing indexes are restored.

Only explicit legacy backfills are performed: missing memory owners come from
a verified private conversation user, with matching memory/persona identity,
consistent persona owner and secondary user, an owned or explicitly shared
business when linked, and matching study ownership when present. Missing, public,
orphaned, or inconsistent links
remain NULL and are excluded by private memory readers. SQL NULL persona JSON
objects become empty objects; and
missing conversation starts use the stored creation timestamp. Existing memory
owners and non-null content are preserved. Unknown provenance owners remain NULL,
and missing conversation snapshots remain NULL rather than inventing history.
Legacy users receive the least-privileged `user` role, not an inferred admin role.

Conflicting memory or behavioral-result duplicates stop the upgrade instead of
deleting or renumbering history. Downgrades of the durable integration, provenance,
and source-ledger revisions deliberately refuse to discard history; use a reviewed
restore plan. The report-only revision can drop its two constraints without
dropping columns or rows. PostgreSQL transaction rollback and full-chain data
preservation still need the live rehearsal below.

---

### M4/M5 integration contract (2026-09-10)

The data integrator owns shared DB models, migrations, persona version/source
helpers, and their tests. The job integrator owns dataset writes and study-job
wiring; neither integrator should edit the other's service while this work runs.
The implemented single forward revision is `e7a9c1d3f205`, after `d4e6f8a0b219`.
The job agent subsequently landed typed dataset writes, pinned-version checks,
version snapshots, source-exclusion rechecks and canonical refresh. These changes
remain that agent's owned work, not edits made by the data integrator.

Dataset persona writers must set these fields on `Personas`:

| Field | Contract |
| --- | --- |
| `dataset_persona_run_id` | Actual `dataset_persona_runs.id`; owner must match the generated persona. |
| `dataset_version_id` | Actual immutable `dataset_versions.id`, belonging to that run's dataset. Never use the latest version implicitly. |
| `dataset_segment_key` | Exact segment `id` inside that immutable version's `segments`; not a `market_segments.id`. |

For typed dataset origins, leave the legacy `generation_run_id` and `segment_id`
NULL. Study generation continues using its existing fields. New CHECKs enforce
mutually exclusive run/segment origins and require a dataset run/version for a
dataset segment key. Historical ambiguous aliases remain intact; the migration
does not infer their type from prefixes or fabricate missing versions.

Call `record_persona_version(session, persona)` after flushing the actual run and
persona, within the same parent-locked transaction. This records the complete
version and acquires the source selection. Call `refresh_study_persona_state`
in that transaction for affected studies. Dataset deletion continues through
`delete_persona_artifacts`; archive paths must release selections transactionally.
Deletion/exclusion queries must recognize both the new typed dataset run field
and existing historical aliases during cutover. Do not remove a pinned dataset
version while personas reference it.

The new feature-owned `PersonaSourceSelections` / `persona_source_selections`
stores `id`, `owner_id`, `scope_owner_id`, `persona_id`, `persona_version`,
`persona_owner_id`, `study_id`, `business_id`, `dataset_id`, `source_namespace`,
`source_record_id`, `source_name`, `created_at`, and `released_at`.
`source_namespace` is the exact ML provenance `source`; `source_record_id` is its
exact `record_id`. No missing namespace or historic ID is invented. The version's
full snapshot retains source revision, model and training lineage.

Exactly one parent scope is required. Parent composite keys preserve the actual
owner separately from the private requesting tenant; only explicit shared owners
may differ. The version FK pins `(persona_id, persona_version, persona_owner_id)`.
The partial unique indexes `uq_source_active_study`, `uq_source_active_business`,
and `uq_source_active_dataset` cover private owner, parent ID, namespace and record
ID only while `released_at IS NULL`. There is no globally unique persona/source
constraint, so a shared legacy persona can participate in distinct authorized
studies and released selections remain as history.

The canonical facade's `active_source_exclusions` accepts explicit `study_id`,
`business_id`, or `dataset_id` in addition to its legacy persona filter. These
arguments include active ledger reservations for reused shared personas as well
as existing nonarchived JSON provenance. Business, study, role, and the now-landed
dataset callers supply their scope. The dataset writer revalidates sources and
captured inputs after acquiring its finalization locks.
The lower-level `acquire_source_selection`, `release_source_selections`, and
`source_exclusions` helpers are in
[source_ledger.py](../apps/backend/bebshax/personas/source_ledger.py).

Same-version changes to source or parent lineage fail. Replacement releases the
previous selection, including replacements without attributable source metadata.
Direct `acquire_source_selection` calls also compare the current dataset run,
pinned dataset version, and segment key against the immutable snapshot before
reusing a selection. A valid replacement run/version in the same dataset is still
an immutable-lineage change; the caller must create a new persona version.
Archive refresh releases matching study and dataset reservations, including
authorized datasets with no study parent. Released rows are retained; rollback
restores the old active reservation. Missing namespaces and legacy polymorphic
dataset-run aliases do not produce invented reservations.

Exact added constraints and indexes:

| Surface | Names |
| --- | --- |
| Parent/version identity keys | `uq_businesses_id_owner`, `uq_studies_id_owner`, `uq_dataset_sources_id_owner`, `uq_dataset_persona_runs_id_owner`, `uq_persona_versions_identity_owner` |
| Persona typed FKs | `fk_personas_dataset_run_owner`, `fk_personas_dataset_version` |
| Persona origin CHECKs | `ck_personas_generation_origin`, `ck_personas_segment_origin`, `ck_personas_dataset_version_run`, `ck_personas_dataset_segment_version` |
| Selection FKs | `fk_source_selection_owner`, `fk_source_selection_version_owner`, `fk_source_selection_study_owner`, `fk_source_selection_business_owner`, `fk_source_selection_dataset_owner` |
| Selection CHECKs | `ck_source_selection_one_scope`, `ck_source_selection_private_owner`, `ck_source_selection_scope_owner`, `ck_source_selection_persona_owner`, `ck_source_selection_identity`, `ck_source_selection_release_time` |
| Selection indexes | `uq_source_active_study`, `uq_source_active_business`, `uq_source_active_dataset`, `ix_source_selections_persona_version` |
| Persona indexes | `ix_personas_dataset_persona_run_id`, `ix_personas_dataset_version_id` |

Migration reconciliation verifies existing column/constraint/index shapes. On
PostgreSQL, existing CHECK expressions are compared with the server's own
reflection of a uniquely named, empty temporary table containing the expected
CHECK. It is immediately dropped and also declared `ON COMMIT DROP`; this path
requires temporary-table privileges and is not exercised by offline compilation.
The three simple partial-index predicates accept harmless PostgreSQL parentheses,
but different logic or a missing predicate is rejected. New parent-table FKs and
CHECKs are added `NOT VALID` then validated. No historical source IDs, owners,
segments, or versions are backfilled by this revision.

This contract is not a claim of live PostgreSQL verification or completed M2-M7.

### M7 report-version backstops (2026-09-10)

`f2b4d6e8a013` adds `uq_study_reports_study_version` and
`ck_study_reports_positive_version`. Uniqueness is per study, not per nullable
report owner; conflicting owner values cannot bypass it. Different studies have
independent positive version sequences. Existing report fields, JSON findings,
full text, and NULL owners are retained unchanged.

The online migration checks duplicate/nonpositive legacy versions and the shape
of any pre-created named constraints before adding DDL. Conflicts stop migration
with a payload-free error, leaving history available for reviewed reconciliation;
no reports are deleted, renumbered, or assigned inferred owners. PostgreSQL takes
a table write lock before that audit, then adds and validates the positive-version
CHECK. Plan for this migration's write-blocking DDL; production-volume lock time
has not been measured. Offline SQL emits the constraints but cannot audit rows.

Only this revision's two constraints are removed by its downgrade. Empty and
populated SQLite upgrade/downgrade/upgrade tests preserve rows; they are not a
PostgreSQL migration or concurrency certificate. Report allocation and job
finalization APIs are unchanged and remain with their existing owner.

## 4. Architectural Guarantees & Dialect Normalization

- **TLS verification:** `postgres://` and `postgresql://` normalize to
   `postgresql+asyncpg://`. `sslmode` maps to asyncpg's `ssl` parameter while
   retaining `disable`, `allow`, `prefer`, `require`, `verify-ca`, or `verify-full`.
   Duplicate/ambiguous and invalid modes are rejected. Use `verify-full` with
   appropriate trust roots for CA and hostname verification; `require` alone is
   not an identity-verification guarantee. `PGSSLROOTCERT` can select the trust
   root. Channel binding is omitted because asyncpg does not implement it; no
   channel-binding guarantee is made.
- **Vector parity:** evidence and memory use PostgreSQL `vector(384)` and the
   historical `ix_evidence_chunks_embedding_hnsw` and
   `ix_memory_items_embedding_hnsw` names with `vector_cosine_ops`. Shared index
   registration does not override feature-owned `__table_args__`. Evidence's
   vector comparator emits native `<=>` SQL with study/space filters and a limit;
   a PostgreSQL query failure is not retried inside an aborted transaction.
   SQLite stores evidence vectors as JSON and scores them locally.
- **Pooling and log hygiene:** configurable pool size/overflow, pre-ping, and
   recycling apply to PostgreSQL; SQLite uses its own connection configuration.
   Engines hide SQL bind values. Tests cover error-log redaction.
- **Supported migration target:** this chain targets PostgreSQL with pgvector.
   SQLite fixture creation and URL normalization for other dialects are not proof
   of a portable production migration chain.

---

## 5. Verification and remaining gates (2026-09-10)

Run the non-network DB scope from the repository root:

```powershell
.venv/Scripts/python -I -B apps/backend/tests/db/run_isolated.py apps/backend/tests/db apps/backend/tests/test_production_hardening.py apps/backend/tests/test_runtime_modernization_persistence.py -q
```

The runner disables dotenv reads, clears inherited application settings, uses
synthetic credentials and SQLite, and keeps temporary state under the DB test
directory. It changes only its own process environment, not machine settings.

To run the real PostgreSQL gate after local Docker Desktop is available and the
existing `pgvector/pgvector:pg16` image is present:

```powershell
.venv/Scripts/python apps/backend/tests/db/run_isolated.py apps/backend/tests/db/test_db_postgres_rehearsal.py -m integration --db-docker -q
```

This gate accepts no configured database URL. It uses the explicit local Docker
pipe/socket, a clean temporary Docker client configuration, a UUID-named
container/database, loopback-only random port, bounded CPU/memory, and tmpfs data.
It never pulls images or mounts/removes user volumes, and removes only the
container ID it created. Tests cover a fresh full-chain migration, upgrade from
`a9c2e7b6d410`, retained pre-created tables, duplicate rollback, native vector
search, reflected metadata/HNSW parity, and real CA/hostname TLS failures.

### Current bounded continuation evidence (2026-09-10)

- Two observed gaps were fixed test-first: direct source acquisition accepted
   same-version dataset run/version/segment substitutions, and report rows had no
   DB-level positive-version or `(study_id, version)` backstop.
- Ledger RED: **3 failed** because no exception was raised; GREEN: **3 passed**.
   Report RED: **4 failed, 1 passed, 10 missing-revision setup errors**; GREEN:
   **15 passed**. The 18 new cases are included in the surrounding result, not
   additional passes to sum with it.
- Owned offline DB plus dedicated persona-version scope: **247 passed,
   6 live integration tests deselected, pytest exit 0** in 106.10 seconds.
   JUnit records zero failures, errors, and skips among the 247 executed tests.
   The separate, overlapping coverage run took 158.34 seconds.
   No full backend, job-domain, provider, or ML suite was run by this continuation.
- Branch-aware coverage: **84%** for `personas/source_ledger.py`, **90%** for
   `f2b4d6e8a013_report_version_integrity.py`, **86% combined** for those two files.
   No pre-change coverage delta was measured. Scoped bug-tier Ruff exited 0;
   editor diagnostics are clear for the changed Python files.
- Exactly one source head, **f2b4d6e8a013**. Measured metadata: **42 tables,
   617 columns, 113 declared indexes, 97 constraints, 35 revisions**. Single-head,
   compiled PostgreSQL constraint DDL, and populated/empty SQLite constraint
   round trips passed. Full historical offline SQL still has the existing
   inspection-dependent limitation described below.
- Disposable live PostgreSQL gate: **exit 1, 1 setup error, 5 deselected**,
   0.48 seconds. The explicit local Docker `version` check failed before image
   inspection or container creation. **Zero database connections and zero test
   containers** resulted. No configured user database, Neon, dotenv file, or
   existing volume was accessed. This is an external-availability block, not
   live PostgreSQL verification or a reported migration failure.
- Compact receipts with run identifier `6a832e` are retained in the owned DB
   test directory to preserve attributable evidence despite shared-terminal
   interference. Other scratch artifacts from this continuation are removed;
   earlier agents' files are preserved.

Parent/job-owner coordination: the new head depends only on `e7a9c1d3f205`.
There are no new packages, tables, columns, or service signatures. Existing
typed dataset writes, pinned snapshots, and locked report allocation remain
compatible. Direct ledger acquisition now requires unchanged pinned lineage
within a persona version. Parent owns the shared implementation log, full-suite
integration, independent code/security review, and any application of this head;
those files and workflows were not changed here. See the
[current DB audit](audits/modernization-db-foundation.md) for the bounded outcome
and remaining M2-M9 gates.

### Data-integrator follow-up evidence (2026-09-10)

- Owned DB, persona-version, embedding compatibility and provider-boundary scope:
   **268 passed, 6 live PostgreSQL tests deselected** (176.79 seconds), using the
   isolated Python 3.12 runner. This is not the full backend suite.
- The original ML fresh-process guard was reproduced failing on provider import
   and now passes unchanged (**1 passed**, final rerun 5.25 seconds). The pure
   dimension contract lives in
   [embedding_space.py](../apps/backend/bebshax/llm/embedding_space.py), with the
   adapter's `CANONICAL_DIM` import retained for compatibility. Lazy persona-service
   package export closes the second eager import path; the ML adapter was not edited.
- The final backfill adds secondary-user/business checks to the earlier verified
   joins. Its **16 attribution cases passed** after that last change, including
   private conversations on shared personas and unresolved/reparented links.
   Quarantined NULL rows were also tested through actual private memory retrieval.
- Final clean ledger plus migration run after all corrections: **77 passed**
   (29.01 seconds). The new source-ledger helper has **83% measured branch-aware
   coverage**, above the 80% changed-code gate. This overlaps earlier counts.
   Coverage used a file-path include; module-discovery coverage imported NumPy
   twice and failed collection, so that earlier wrapper run is not test evidence.
- After the job agent's typed writer landed, its focused
   [dataset persona lifecycle tests](../apps/backend/tests/jobs/test_dataset_persona_lifecycle.py)
   passed **13 tests** (24.92 seconds) against this data layer. This confirms the
   scoped integration, not the entire job/recovery suite or live PostgreSQL.
- New migration tests cover PostgreSQL/SQLite compiled parity, a single forward
   head, synthetic legacy preservation, repeatability, conflicting pre-created
   schema, and weakened CHECK/partial-index rejection. They do not certify live PG.
- Scoped bug-tier Ruff and editor diagnostics pass. A read-only review found three
   medium issues, reproduced by tests and repaired; its follow-up found no remaining
   Critical/High/Medium issues in those corrections. That review ran no commands.
- Live PostgreSQL, migration application, credentials, environment files, Git,
   provider calls, and the full backend/ML suites were not touched. Shared-terminal
   interference interrupted earlier runs; incomplete runs are not clean passes.

### Previous continuation evidence (2026-09-10)

- Final owned unit scope: **170 passed, 6 existing integration tests deselected**
   in 28.89 seconds after the native-async fixture typing corrections. No full
   backend run was performed during concurrent work. All six live PostgreSQL cases
   collect against the new head without execution. Bug-tier Ruff and editor
   diagnostics passed for DB code, migrations and owned tests; scoped diff
   whitespace checks passed.
- Fresh registration and source coverage include all 41 tables and 600 columns.
   Named index/constraint source coverage includes the 107 declared indexes;
   frozen new table/index/column definitions have dialect-compiled parity tests.
   These are source/SQLite checks, not a reflected PostgreSQL catalog certificate.
- Offline PostgreSQL `a9c2e7b6d410:head` produces a complete transaction with one
   head, `d4e6f8a0b219`. No configured URL, dotenv file, Neon connection, container,
   service, or application restart was used in this continuation.
- `ProvenanceSink.persist` now honors the declared `owner_user_id`, including
   deferred persistence without a tenant context, and rejects conflicting verified
   owners. Full study/policy/classification/estimate context and account-reservation
   observations survive commit and replay. Completion still awaits commit; failed,
   cancelled, closed, and overflow deliveries never claim acknowledgement.
- Quota replay tests retain failed/aborted/unknown consumption and cache hits,
   preserve reservation observations, and seed idempotently. This proves restart
   replay, not cross-process account admission or recovery of attempts lost before
   provenance commit. That pre-commit crash window remains.
- Cooldown writes retain atomic maximum deadlines, reject nonfinite/nonpositive
   durations, and closure waits for outstanding commits. Failed writes surface at
   finalization with no private driver payload. Expired-row tests insert genuine
   expired rows rather than violating the duration API to construct fixtures.
- Both path-default regressions isolate `BEBSHAX_DATA_DIR`,
   `BEBSHAX_UPLOAD_DIR`, and `BEBSHAX_PROCESSED_DIR`. Explicit overrides still win;
   application configuration precedence was not changed. The historic two baseline
   failures remain documented as verifier-environment interference, not current
   application failures.
- The shared factory uses `async_sessionmaker[AsyncSession]` with
   `expire_on_commit=False` and `autoflush=False`; persistence consumers accept
   callable async-session factories. Shared `DeclarativeBase` typing remains
   intact. Strict TLS-mode and vector comparator/index regressions passed.

### Previous integration evidence (2026-09-09)

- **136 passed, 6 integration tests deselected** in the isolated DB/hardening
   run (27.44 seconds, Python 3.12.9). Bug-tier Ruff passed on the touched slice;
   the original ORM typing diagnostics are resolved.
- Fresh-process registration covers all 41 declared tables without importing the
   app. Source checks cover all 594 declared columns. Frozen new-table, column, and
   index definitions match current ORM metadata on PostgreSQL/SQLite compilation.
   Synthetic SQLite legacy-slice upgrades preserve data and are repeatable.
- PostgreSQL offline SQL for `a9c2e7b6d410:c6f8a2d4e901` compiles. This is **not**
   evidence of execution on PostgreSQL.
- Full-chain offline compilation stops at historical `c4d5e6f7a8b9`, whose data
   backfill calls `fetchall()` on a live connection. Later historical revisions
   also use inspection. These applied-history scripts were not rewritten or
   supplied with fabricated inspection results.
- The explicit live gate failed at the local Docker server prerequisite
   (1 setup error, 5 deselected); no container was created, so no cleanup or
   database connection was needed. Fresh PostgreSQL, live reflection, rollback,
   and actual TLS handshakes remain **unverified**. No configured dotenv/Neon
   database was used.

### Migration risks and parent coordination

Full-chain offline compilation remains blocked by the unchanged historical
`c4d5e6f7a8b9` live data query and later inspection-dependent migrations. Do not
replace inspection with fabricated catalogs or equate SQLite `create_all` and
stamping with PostgreSQL migration execution. Live fresh/legacy upgrades, actual
TLS handshakes, reflection, concurrency, and migration rollback remain unverified.

Legacy duplicate memory/result rows block `c6f8a2d4e901` before the new revision
can run. Pre-created feature tables with incompatible frozen shapes also block
that predecessor. Resolve those rows/shapes through reviewed, attributable
cleanup or quarantine first; never invent owners, silently delete records, or
stamp around the failure. The stricter startup schema check can expose such
previously hidden drift and intentionally refuses readiness. An automatic
downgrade is not provided for durable historical processing context.

Parent/feature-owner follow-up: M5 source-identity active uniqueness and its
composite scope/version keys are now implemented by `e7a9c1d3f205`. Wider M2
contextual FKs, normalized dataset-segment tables, historical attribution repair,
and M6 audience/message records are not thereby complete. The job agent's typed
writer and helper calls have landed; deletion/archival and recovery coverage
across the complete job workflow remain its verification responsibility. Actual
run-to-dataset/version/segment membership is checked by the facade, not yet by a complete
set of dataset contextual composite FKs.
The new M7 report backstops in `f2b4d6e8a013` do not close those gaps or certify
the remaining chunk/counter/domain constraints. Live foreign-key/null-owner
behavior, partial-index contention, report allocation concurrency, PostgreSQL
upgrade/rollback preservation, native-vector queries/TLS, and M9 query plans
remain blocked on the disposable local PostgreSQL gate. SQLite proves none of
the PostgreSQL locking or multi-process guarantees.
The current parent callback already awaits `sink.persist`; no mapping or callback
signature was broken. Any additional auth, memory, jobs, behavioral, persona or
dataset ORM changes after this schema snapshot require another coordinated
forward revision and a rerun of these coverage checks. Full-stack verification and
shared account admission remain parent-owned. No dependencies, manifests,
environment files, feature-owned ORMs, other docs, commits, pushes, or deployments
were changed by this continuation.

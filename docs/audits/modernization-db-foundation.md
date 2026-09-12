# Batch 1B: Database Foundation

## Data Continuation (2026-09-10)

Bounded data fixes are implemented and verified offline. The single source head
is now **f2b4d6e8a013**, directly after **e7a9c1d3f205**. No historical migration
was changed, including the already-corrected, owner-confirmed-unapplied
`c6f8a2d4e901`. Earlier foundation evidence below remains historical.

### Implemented

- [source_ledger.py](../../apps/backend/bebshax/personas/source_ledger.py): direct
  acquisition compares dataset run, pinned version, and segment key with the
  immutable persona snapshot. Previously, another valid run/version in the same
  dataset or removal of the segment key was accepted within the same persona
  version. Three permanent regressions reproduce and prevent this bypass.
- [models.py](../../apps/backend/bebshax/db/models.py): report version positivity
  and unique `(study_id, version)` are database backstops, independent of nullable
  report owners. No columns or service signatures changed.
- [report migration](../../apps/backend/alembic/versions/f2b4d6e8a013_report_version_integrity.py):
  preflight invalid/duplicate legacy versions and conflicting named constraints;
  preserve all rows, NULL owners, JSON findings, and complete report text.
  PostgreSQL acquires a table write lock before auditing, then adds uniqueness
  and a `NOT VALID` CHECK followed by validation. Conflicts stop for reviewed
  reconciliation; no invented attribution or automatic renumbering/deletion.
  Its downgrade removes only its two constraints. Older history-bearing
  revisions retain their downgrade refusal.
- [report regressions](../../apps/backend/tests/db/test_db_report_version_integrity.py)
  cover owner-independent uniqueness, positive versions, distinct studies,
  retained legacy history, conflicting pre-created shapes, empty/populated
  round trips, and offline PostgreSQL DDL. Existing head assertions and the
  disposable rehearsal now target the new head while retaining old ancestry.

### Evidence

| Check | Result |
| --- | --- |
| New ledger regression RED / GREEN | 3 failed / 3 passed |
| Report regression RED / GREEN | 4 failed, 1 passed, 10 missing-migration errors / 15 passed |
| Owned DB + dedicated persona-version scope | 247 passed, 6 integration deselected, pytest exit 0; JUnit: 0 failures/errors/skips among executed tests |
| Measured branch-aware coverage | Ledger helper 84%; new migration 90%; combined 86%; no baseline delta measured |
| Ruff, nine changed Python files | Configured bug-tier rules passed, exit 0 |
| Editor diagnostics | No errors in the changed Python files |
| Source inventory | 42 tables, 617 columns, 113 declared indexes, 97 constraints, 35 revisions; one head |
| PostgreSQL constraint SQL | Offline compilation passed; not a connected catalog result |
| Empty/populated report round trip | SQLite passed; no PostgreSQL rollback claim |
| Disposable PostgreSQL attempt | Exit 1; 1 setup error, 5 deselected; local Docker version check failed in a 0.48-second test run |

The definitive 247-test run took 106.10 seconds and printed pytest exit 0 in its
child receipt; the overlapping coverage run took 158.34 seconds. Eighteen new
parametrized cases are included in that count; focused RED/GREEN runs overlap
and must not be added to it. Commands used the existing isolated Python 3.12 runner, synthetic settings,
disabled dotenv sources, repository-local temporary state, and separate coverage
data. Shared-terminal output was unreliable, so counts came from uniquely named
child-output/JUnit receipts rather than another workstream's displayed command.
Compact receipts with identifier `6a832e` are retained in the owned DB test
directory for that audit trail; other scratch artifacts from this continuation
are removed, without cleaning earlier agents' files. No package was installed
and no shared coverage file was overwritten.

The local Docker prerequisite failed before image inspection/container creation:
**zero PostgreSQL connections, zero test containers, no user volumes accessed**.
No `.env`, configured database URL, Neon connection, remote provider, or user data
was used. No whole-backend suite, commit, branch, push, or application deployment
was performed.

### Remaining Gates

- **M2:** wider contextual tenant/parent FKs and ambiguous historical attribution
  remain separate work. Existing offline attribution/quarantine tests do not
  establish private NULL-owner handling or FK validation on live PostgreSQL.
- **M3-M5:** immutable versions and scoped source uniqueness have offline
  coverage; normalized dataset segments and complete run/dataset/version
  composite FKs are not delivered by this revision. Active-source contention,
  parent locks, and multi-process safety remain unverified on PostgreSQL.
- **M6:** canonical audience/message/citation records and their writer cutover
  are not closed by these database fixes; coordinate with the domain owner.
- **M7:** the report backstops are new. Other planned chunk/counter/domain
  checks are not certified here. Real report allocation/constraint concurrency
  and full-chain upgrade/rollback require the disposable PostgreSQL gate.
- **M8:** existing journal migration contracts remain compatible; job-domain
  recovery and multi-process admission are the job/parent workstream's gates.
- **M9:** native vector/TLS offline contracts remain green. Real vector queries,
  realistic `EXPLAIN (ANALYZE, BUFFERS)`, query-count budgets, and production-size
  migration lock times are still unverified.

Parent/job-owner handoff: new schema dependency is only `f2b4d6e8a013` after
`e7a9c1d3f205`; no job/dataset API or ORM contract was changed. Keep the existing
typed writer and report parent-lock allocation. Rehearse the new head on an
owned disposable PostgreSQL database before any application. Independent
code/security review and the parent-owned shared implementation-log update are
pending; this implementation agent does not self-approve the diff. Changes were
limited to shared DB models, the source helper, one new migration, owned tests,
and this audit plus [DATABASE_MIGRATION.md](../DATABASE_MIGRATION.md).

## Earlier Foundation Evidence

Date: 2026-09-09. Owned changes implemented and verified offline. This is not
PostgreSQL integration, full-stack, or production sign-off.

## Owned Changes

- [engine.py](../../apps/backend/bebshax/db/engine.py): preserve all six asyncpg
  SSL modes, reject ambiguous/invalid modes, deliberately strip unsupported
  channel binding, retain supported `target_session_attrs`, hide SQL parameters,
  and omit private exception details from bootstrap/seed warnings.
- [models.py](../../apps/backend/bebshax/db/models.py): evidence embeddings use
  `Vector(384).with_variant(JSON(), "sqlite")`, exposing the native cosine
  comparator. Shared `Base.__table_args__` declares both PostgreSQL-only HNSW
  indexes with their historical names and `vector_cosine_ops`.
- [vector_search.py](../../apps/backend/bebshax/research/vector_search.py): native
  PostgreSQL search retains study/space filters and LIMIT; SQL failures propagate
  without a second query in an aborted transaction or a raw traceback log.
  SQLite retains Python scoring and JSON vector round-trips.
- [repair migration](../../apps/backend/alembic/versions/b1bf09c4d2e7_repair_vector_indexes.py):
  revision `b1bf09c4d2e7`, predecessor `a9c2e7b6d410` (verified as the sole source
  head immediately before authoring). Exactly two `CREATE INDEX IF NOT EXISTS`
  operations; SQLite upgrade and downgrade are no-ops. Ancestors own the indexes.
- [foundation regressions](../../apps/backend/tests/db/test_db_foundation_hardening.py),
  [vector regressions](../../apps/backend/tests/db/test_db_foundation_vectors.py),
  and [migration regressions](../../apps/backend/tests/db/test_db_foundation_migration.py).
- [production-hardening tests](../../apps/backend/tests/test_production_hardening.py):
  isolate the two directory-fallback tests from inherited directory overrides;
  explicitly test that OS environment overrides still win with dotenv disabled.

`init_database(engine, sessionmaker_=None, seed=True)` remains compatible. For
non-SQLite engines it validates the database revision against exactly one source
head before seeding. Missing, empty, behind, unknown, or multiple database heads
are rejected; invalid/missing source heads are not swallowed. It does not create
extensions, run migrations, or stamp PostgreSQL. SQLite alone uses repeatable
`create_all`, without inserting an Alembic stamp. Returned names describe registered
metadata, not proof that migrations or complete schema reconciliation occurred.

## Verification Evidence

All pytest executions used the repository venv, Python **3.12.9**. Installed
asyncpg **0.31.0** parser checks verified required trust roots and the distinction
between CA verification and hostname verification without connections or real
certificate/key reads. No dependency or type-checker installation was performed.

| Check                                                 | RED                                                         | GREEN                                       |
| ----------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------- |
| Initial SSL/comparator/index/revision/parameter slice | 11 failed, 1 passed (0.19 s)                                | 12 passed (0.21 s)                          |
| Expanded foundation and repair                        | 6 failed, 28 passed, 5 missing-repair setup errors (0.54 s) | 39 passed (0.55 s)                          |
| Two fallback tests with injected directory overrides  | 2 failed (1.88 s)                                           | 2 passed (1.82 s)                           |
| Private seed-error logging                            | 1 failed (2.30 s)                                           | 1 passed (1.99 s)                           |
| Closing selected regression set                       | 80 passed, 1 non-foundation OpenRouter failure (4.01 s)     | 80 passed, 1 explicitly deselected (3.49 s) |

Closing selection: the three new DB regression files, DB `test_models.py`,
`test_sink.py`, `test_migration_idempotency.py`, `test_orm_placement.py`,
`test_owner_id.py`, and `test_production_hardening.py`. The only deselected test
was `test_openrouter_models_env_override`: it expected two candidates but got an
empty list. Its provider behavior and assertions were left untouched for the
LLM workstream. No full backend suite was run.

- Ruff: `python -m ruff check --no-cache --config apps/backend/pyproject.toml`
  over the eight changed Python files: **All checks passed**, exit 0. Configured
  rules: `E9`, `F63`, `F7`, `F82`.
- Editor `get_errors`: **no errors** for all eight changed Python files. This
  is editor diagnostic evidence, not a separate Python 3.12 CLI type-check gate.
- Final source head: **b1bf09c4d2e7**. Final PostgreSQL connection attempts: **0**.
- Pytest used `--confcutdir=apps/backend/tests/db`, `-p no:cacheprovider`, and a
  unique `--basetemp` under an auto-cleaned repository-local E-drive temporary
  directory. Child processes disabled both dotenv loaders, used SQLite/fakes,
  and blocked asyncpg connections. Directory overrides were pytest-scoped,
  never persistent shell environment changes.
- The normal suite-wide conftest initially could not import `main`: an evaluation
  route imported a missing `OLLAMA` symbol. Shared terminals also returned other
  workers' output or interruption traces; these were not counted as verification.
  Final Ruff/pytest ran in synchronous venv subprocesses launched by the Python
  execution tool; its selected 3.15 interpreter was only the launcher.
- Python/security repo rules were read. Requested database-patterns and
  Python-fact-grounded skill files were outside the repository and were not read
  under remote mode's working-directory restriction. Facts came from scoped
  source reads, the installed asyncpg parser, real SQLite, and editor diagnostics.

## Coordinator-Owned Follow-up

1. [main.py](../../apps/backend/bebshax/main.py): move revision validation ahead
   of DB consumers in `_lifespan`; do not swallow PostgreSQL schema-revision
   failures in development. Remove stale create-all/stamp bootstrap wording.
2. `check_migrations_current_async`: use the same single-source-head semantics,
   resolve `script_location` relative to the chosen ini file, dispose the temporary
   engine in `finally`, and set `hide_parameters=True`. Its empty/multiple-head
   handling must not undermine `init_database`'s stricter validation.
3. [alembic/env.py](../../apps/backend/alembic/env.py): set `hide_parameters=True`
   on its separate migration engine. ORM imports already register both index
   definitions; no new import is needed for this repair.
4. Sanitize the coordinator-owned startup exception logging and `{exc!r}` fatal
   message. Parameter hiding does not redact private text already in a driver's
   own error detail. Configure trusted CA material for verified SSL modes, e.g.
   via `PGSSLROOTCERT`; do not weaken them to `require`.
5. Apply and inspect the migration only on coordinator-owned scratch PostgreSQL:
   fresh schema and legacy/previous-head upgrade, both historical HNSW names,
   cosine operator classes, vector dimensions, and filtered native queries.
   This additive repair does not reconcile every possible legacy schema drift;
   `IF NOT EXISTS` also does not repair a same-name index with a wrong definition.
6. Memory ORM was not edited. Its inherited HNSW metadata must be preserved if
   a later feature worker introduces its own `__table_args__` override. Memory
   comparator/retrieval behavior remains with that owner.

No configured database, live data, shared documentation, configuration, main
wiring, historical migration, feature ORM, job, authentication, or API file was
modified. No commit, branch, push, server, or deployment was performed.

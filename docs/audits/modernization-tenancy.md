# Tenancy and Integrity Implementation Handoff

Date: 2026-09-09. Assigned migration predecessor: `b1bf09c4d2e7`.
Scope is the operator-approved tenancy worker allocation, not the whole modernization roadmap.
No migration, live DB, provider call, install, server, full suite, commit, push, or deployment was run.
Existing vector types and HNSW declarations in central models are preserved unchanged.

## Delivered

- SEC02: `POST /api/studies` requires the real required-user dependency before writes; missing/invalid bearer returns 401. IDs and ownership are server-assigned. PATCH/PUT never create missing studies (404). Shared demos are read-only, including for a matching owner.
- WF05: persona counts, IDs, and persona snapshots are rebuilt from active rows whose immutable owner matches the study owner. List reads use one batched persona query, not one query per study. Client findings cannot overwrite generated findings.
- WF05: study revision uses SQLAlchemy optimistic versioning, including ORM writes by other services. Response bodies include `revision`; create/detail/update also return `ETag`. Full copilot-message list order is retained; guarded stale history saves cannot overwrite an accepted version.
- SEC09: provenance visibility uses immutable request-time `LLMRequests.owner_id`, never mutable persona joins. Auth is required; NULL/unknown owners are private. Raw provider failure details are redacted even for owners. No persona/conversation/owner FK was added to LLM provenance, so failed generations remain loggable.
- SEC09: route status/capacity are enabled only in development for a loopback peer. Production/staging return 404. Headers/query fields cannot grant a role. No administrator role or production privilege predicate was invented.
- WF09: legacy business generation now locks an authorized parent before exclusions and holds the same session through selection, persona/version persistence, and commit. Shared businesses remain usable by authenticated callers; exclusions and generated rows remain private to that caller. Shared parent ownership is unchanged.
- DB02: append-only `(persona_id, version)` snapshots, immutable owner stamp, canonical snapshot, and optional full legacy profile. New legacy/study generation and study regeneration write snapshots; regeneration captures the available prior version before replacement. Older missing versions are not reconstructed.
- ML boundary: all four converters retain `strategy`, nullable `topic`, `source_attribution`, `source_corpus_sha256`, and `training_code_sha256` in existing provenance fields. Optional trusted-manifest verification is available; the frozen production artifact was not read or replaced.
- Owned persona/report job callers await durable admission, poll by verified owner, and bind owner context in the runner. Persona API errors use the runtime's existing `ExplicitFailure` contract so persisted job error codes survive.

## Client Contract

Create a study with authenticated POST, then use its returned server ID. A missing PATCH/PUT is not an upsert.

New clients should send either `If-Match: "<revision>"` or integer `expected_revision` in the update body. If both are supplied they must agree. Revisions must be positive signed-32-bit integers. Invalid/conflicting conditions return 400; stale If-Match returns 412; stale expected_revision or ORM CAS races return 409. Reload and reconcile before retrying; do not blindly resend a stale full chat history.

New guarded clients must omit `persona_count`, `persona_ids`, `personas_data`, and `findings` entirely, including null/empty values (422). Legacy unguarded payloads still accept those fields but ignore them and return canonical state. Client `user_id`, `id`, and `is_demo` never grant ownership/publication. Guardless writes remain allowed for initial compatibility and can still overwrite newer client intent; frontend owner must migrate stores before making preconditions mandatory. No blanket 428 rollout occurred here.

Persona snapshots now match the canonical persona response fields. Role/UI-only presentation data must be persisted in appropriate canonical fields by its owning writer, not reinjected through a study PATCH. No new message table was needed for the optional full-history CAS contract.

## Integration Hooks

- Auth/API owners: use `get_tenant_user` or `get_optional_tenant_user` from `bebshax.api.deps`, or `with tenant_scope(verified_user.id):` from `bebshax.tenancy_context`. These are wired only into the assigned routers here. Bind in background runners too. Context always resets in `finally`; never derive it from an owner header/query/body.
- Runtime sink: call `capture_provenance_owner(record)` synchronously at submission, store that scalar alongside the record, and persist it as `LLMRequests.owner_id` inside deferred work. Do not read context later in a background flush. Explicit record owner and request context must agree. The runtime worker's sink currently uses this hook; its broader verification remains that worker's responsibility.
- Owner context is NOT egress consent, redaction, or an authorization policy for private provider data. No such policy is inferred here. Non-owned feature routes still need their auth/context integration before their new provenance can be attributed safely.
- All persona writers: `await lock_persona_parent(session, owner_id=verified_owner, study_id=...)` before exclusions and persistence; specify exactly one study/business/dataset parent. The narrowly scoped `allow_shared_business=True` option never applies to a study or dataset.
- Canonical row creation: flush the new `Personas` row, then `await record_persona_version(session, row)` from `bebshax.personas.service`, before committing. For overwrite/archive, first call with `capture_kind="observed_current"`, then change/increment the row and record the new version. Existing snapshots are never changed. Do not invent versions 1..N-1 for a row first seen at N.
- Legacy saves: `await save_persona(session, profile, owner_id=verified_owner, commit=False)` flushes but does not commit. The caller holds the parent lock and commits once. Default `commit=True` preserves existing callers. Replacing an existing legacy persona requires exactly the next version and identical owner/business.
- Study persona writers: `await refresh_study_persona_state(session, study=study, owner_id=verified_owner, removed_ids=set())` before commit. It now rebuilds all derived fields from rows, not only deleted IDs. Dataset/role writers outside this scope still need the version hook and canonical-refresh integration.
- Read facade: `list_persona_versions(session, persona_id, owner_id=verified_owner)` and `get_persona_version(session, persona_id, version, owner_id=verified_owner)` return ORM snapshots, scoped by immutable owner. Missing history returns None/empty. These are service APIs, not new HTTP routes.
- Interview/memory owners: pin `(persona_id, version)` at creation and resolve through the version facade for immutable identity. Conversations/memories were not changed by this worker; current historical conversations remain unpinned.
- Bulk SQL study writers bypass ORM version tracking: include the expected revision in the WHERE clause, atomically increment revision, and check row count. Ordinary ORM writers should handle `StaleDataError` as a conflict, not retry stale state silently.
- App/config owner: inject a trusted `ExpectedArtifactManifest` through `MLPersonaAdapter(path, expected_manifest=manifest)` or `MLPersonaAdapter.from_settings(settings, expected_manifest=manifest)`. Obtain the expected metadata digest out of band from a trusted reviewed release, not from the artifact being verified or user input. Omitting it preserves compatibility, not authenticity. No automatic reload/promotion is added.

## Migration Instructions

Coordinator must integrate these after the assigned head and reconcile with the other workers' migration chain. Application code using these columns must not precede the migration.

1. `studies.revision INTEGER NOT NULL DEFAULT 1`. Backfill existing rows to 1. Add a positive-revision check. The ORM uses this column as `version_id_col`; no automatic revision trigger should double-increment ORM updates.
2. `llm_requests.owner_id VARCHAR(64) NULL`, no FK and no shared/system default. Index `ix_llm_requests_owner_created_at (owner_id, created_at DESC)`. Backfill only from trustworthy request-time authentication/audit evidence. NEVER infer historical ownership from a persona's current owner or publish orphan/NULL rows. Uncertain rows remain NULL and inaccessible via the API.
3. Register `bebshax.personas.orm` in Alembic metadata imports. Create `persona_versions` with the following shape:

```sql
CREATE TABLE persona_versions (
    persona_id VARCHAR(64) NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    study_id VARCHAR(64) NULL,
    snapshot JSONB NOT NULL,
    legacy_profile JSONB NULL,
    capture_kind VARCHAR(32) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (persona_id, version),
    CONSTRAINT ck_persona_versions_positive_version CHECK (version >= 1),
    CONSTRAINT ck_persona_versions_capture_kind CHECK (capture_kind IN ('generated', 'observed_current'))
);
CREATE INDEX ix_persona_versions_study_id ON persona_versions(study_id);
CREATE INDEX ix_persona_versions_owner_persona ON persona_versions(owner_id, persona_id);
```

ORM supplies `capture_kind="generated"` and UTC `captured_at`; migration backfills must supply `observed_current` and the actual capture time explicitly. Snapshot only the currently available version and full fields that actually exist. Preserve absence of unavailable legacy data rather than fabricating it. No raw training data is required.

4. After conservative backfill, install a PostgreSQL trigger rejecting changes to `llm_requests.owner_id` (`IS DISTINCT FROM OLD.owner_id`) and updates to `persona_versions`, or equivalent application-role privileges. ORM guards cover normal object updates but cannot enforce invariants against raw SQL. Persona deletion is intentionally allowed to cascade versions; deleting a persona must not publish provenance. No trigger/migration was executed here.
5. Preserve the foundation worker's canonical vector dimensions, PostgreSQL-only HNSW indexes, index names, and `vector_cosine_ops`.

## Evidence and Remaining Gates

Tests use project Python 3.12, one pytest process, CPU library thread limits of 1, SQLite test databases, and project-local temporary paths. The isolated working directory prevents automatic discovery of local environment files. No live provider or live DB was used. All trained test artifacts are small synthetic fixtures; the schema-v1 probe builds its own compatibility artifact, not the frozen production bundle.

RED evidence: anonymous/invalid creation initially returned 201 and wrote rows; missing updates created rows; forged snapshot fields persisted; revisions were ignored; unknown provenance was readable; business generation lacked FOR UPDATE; study versions were absent; mutable user stamps selected foreign-owned personas; the ML adapter dropped new metadata and lacked the manifest argument. Each owned correction was immediately followed by focused tests.

Verified checkpoints: initial study slice 16 passed; SEC09 7 passed; context isolation 4 passed; lineage/business/owner slice 11 passed; ML contract 6 passed; existing store/adapter plus new tenancy contracts 72 passed; row scoping 9 passed; existing provenance slice 6 passed; final persona job slice 4 passed. These overlap and are not a summed suite count. Scoped Ruff bug-tier checks passed.

The normal project conftest initially failed on a routing-worker `OLLAMA` import; that was resolved upstream and subsequent scoped runs used the normal conftest without monkeypatching the production boundary. Shared terminal output sometimes interleaved; durable per-run logs/JUnit under `.tmp/tenancy-worker/` are the evidence.

The wider study/persona API check initially had 49 passes, 15 failures, and 6 setup errors. Local authorization ordering and obsolete tenancy expectations were corrected. Owned async callers were integrated and the job-code failures corrected using `ExplicitFailure`. Dataset/standalone failures were from unconverted durable admission callers outside this worker's ownership; they were not patched or hidden. A targeted repeat excluding those paths had 45 passes and only the two job-code failures, subsequently passing in the four-case job regression run.

Still required: coordinator DDL/backfill/DB immutability enforcement, live PostgreSQL multi-process lock/CAS validation, dataset/role version capture, interview version pinning, frontend revision rollout, production privilege policy (diagnostics stay disabled), trusted manifest injection, and provider egress policy from their respective owners. SQLite persistence and PostgreSQL-compiled lock SQL do not establish production concurrency behavior. Full suite/CI/release approval remains the coordinator's task.

The existing async persona/report route suite also passed all 8 tests after integration. Editor diagnostics remain in pre-existing optional-value paths in study script/report handlers and in the preserved foundation `Base.__table_args__` typing; there is no clean project-wide type-check claim. The newly added context/version modules and changed persona/service/provenance paths had no editor errors in the scoped check.

## Final Scoped Result

PASS: 143 tests, 15 deselected, 0 failures, 138.85 seconds. Normal repository conftest was used. Selection was `-q -k "not dataset and not standalone" --tb=short --show-capture=no` over exactly these files under `apps/backend/tests`:

```text
api/test_modernization_tenant_studies.py
api/test_row_scoping_hardening.py
api/test_api_hardening_study_delete.py
api/test_async_generation_jobs.py
api/test_ml_persona_generation_contracts.py
persona/test_store.py
persona/test_ml_backend_adapter.py
persona/test_modernization_persona_versions.py
persona/test_modernization_tenancy_context.py
persona/test_modernization_ml_contract.py
```

Final evidence: `.tmp/tenancy-worker/tenancy-final.log` and `tenancy-final.xml`. The 15 deselections are explicit dataset/standalone-owned cases, not suppressed failures. The separate existing-provenance slice passed 6 tests (`provenance or stamped_rows or redact_attempts` in `api/test_api_hardening_routes.py`). Final configured Ruff checks passed on all 17 owned/changed Python files; scoped diff whitespace check passed. No release/full-suite/CI claim is made.
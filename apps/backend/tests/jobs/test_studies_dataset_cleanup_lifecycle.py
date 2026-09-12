from __future__ import annotations

from collections.abc import AsyncIterator
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Delete


@pytest.fixture
async def study_cleanup_http(sql_upload_context, journal_engine, job_store, monkeypatch, tmp_path):
    from bebshax.api import deps, studies
    from bebshax.auth.models import Users
    from bebshax.datasets import service as dataset_module
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import Base, DatasetSources, Studies

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    monkeypatch.setattr(dataset_module, "_upload_dir", lambda: upload_root)
    async with journal_engine.begin() as connection:
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
        await connection.run_sync(Base.metadata.create_all)
    maker = job_store.sessionmaker
    files = {}
    expected_cleanup = set()
    versions = []
    original_path = upload_root / "cleanup-versioned.json"
    files[original_path] = b'[{"age": 20}]'
    for version, records in ((1, b'[{"age": 25}]'), (2, b'[{"age": 30}]')):
        digest = hashlib.sha256(records).hexdigest()
        path = upload_root / f"cleanup-versioned.v_{version:016x}.{digest}.json"
        files[path] = records
        expected_cleanup.add(("cleanup-versioned", str(path), digest, "owner-1"))
        versions.append(DatasetVersions(
            id=f"cleanup-version-{version}", dataset_id="cleanup-versioned", owner_id="owner-1", version=version,
            content_hash=digest, records_hash=digest, file_path=str(path),
            original_file_path=str(original_path) if version == 1 else None,
            file_type="json", row_count=1, column_count=1, schema_metadata={}, statistics={}, segments=[],
        ))
    legacy_path = upload_root / "cleanup-legacy.json"
    files[legacy_path] = b'[{"age": 35}]'
    for path, records in files.items():
        path.write_bytes(records)
    expected_cleanup.update({
        ("cleanup-versioned", str(original_path), None, "owner-1"),
        ("cleanup-legacy", str(legacy_path), None, "owner-1"),
    })
    kept_path = upload_root / "keep-dataset.json"
    kept_path.write_bytes(b'[{"age": 40}]')
    async with maker() as session, session.begin():
        owner = await session.get(Users, "owner-1")
        session.add_all([
            Studies(id="cleanup-study", user_id="owner-1", title="Delete synthetic study"),
            Studies(id="keep-study", user_id="owner-2", title="Keep synthetic study"),
        ])
        await session.flush()
        session.add_all([
            DatasetSources(id="cleanup-versioned", user_id="owner-1", study_id="cleanup-study",
                           name="Versioned synthetic dataset", file_path=versions[-1].file_path),
            DatasetSources(id="cleanup-legacy", user_id="owner-1", study_id="cleanup-study",
                           name="Legacy synthetic dataset", file_path=str(legacy_path)),
            DatasetSources(id="cleanup-pathless", user_id="owner-1", study_id="cleanup-study", name="Pathless synthetic dataset"),
            DatasetSources(id="keep-dataset", user_id="owner-2", study_id="keep-study",
                           name="Kept synthetic dataset", file_path=str(kept_path)),
        ])
        await session.flush()
        session.add_all(versions)

    request_sessions = []

    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            rollback = AsyncMock(wraps=session.rollback)
            monkeypatch.setattr(session, "rollback", rollback)
            request_sessions.append(SimpleNamespace(session=session, rollback=rollback))
            yield session

    app = sql_upload_context.app
    app.include_router(studies.router, prefix="/api")
    app.dependency_overrides[deps.get_session] = session_dependency
    app.dependency_overrides[deps.get_optional_tenant_user] = lambda: owner
    optional_cleanup = AsyncMock(side_effect=AssertionError("Request must defer filesystem work to the durable worker"))
    app.state.dataset_service = SimpleNamespace(cleanup_pending_files=optional_cleanup)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            app=app, client=client, maker=maker, engine=journal_engine, files=files,
            kept_path=kept_path, expected_cleanup=expected_cleanup, upload_root=upload_root,
            request_sessions=request_sessions, optional_cleanup=optional_cleanup,
        )


@pytest.fixture
async def study_cleanup_worker_factory(study_cleanup_http):
    from bebshax.datasets.service import DatasetService
    from bebshax.llm import SingleAdapterLLMService
    from bebshax.llm.adapters.fake import FakeAdapter

    engines = []

    def new_worker():
        engine = create_async_engine(study_cleanup_http.engine.url)
        engines.append(engine)

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        maker = async_sessionmaker(engine, expire_on_commit=False)
        service = DatasetService(maker, llm=SingleAdapterLLMService(FakeAdapter([])))
        return SimpleNamespace(service=service, maker=maker)

    try:
        yield new_worker
    finally:
        for engine in engines:
            await engine.dispose()


async def test_delete_journals_all_dataset_paths_before_cascade_without_unlinking(study_cleanup_http):
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import DatasetSources, Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    response = await context.client.delete("/api/studies/cleanup-study")
    assert response.status_code == 200, response.text
    assert response.json() == {"success": True, "deleted_id": "cleanup-study"}
    async with context.maker() as session:
        assert await session.get(Studies, "cleanup-study") is None
        assert not list(await session.scalars(select(DatasetSources).where(DatasetSources.study_id == "cleanup-study")))
        assert not list(await session.scalars(select(DatasetVersions)))
        journal = list(await session.scalars(select(JobFileCleanup)))
        assert {(entry.dataset_id, entry.file_path, entry.content_hash, entry.owner_id) for entry in journal} == context.expected_cleanup
        assert all(entry.status == "pending" and entry.attempts == 0 for entry in journal)
        assert await session.get(Studies, "keep-study") is not None
        assert await session.get(DatasetSources, "keep-dataset") is not None
        assert not (await session.execute(text("PRAGMA foreign_key_check"))).all()
    for path, records in context.files.items():
        assert path.read_bytes() == records
    assert context.kept_path.exists()
    context.optional_cleanup.assert_not_awaited()


@pytest.mark.parametrize("direct_study_scope", [True, False], ids=["direct-study", "dataset-lineage"])
async def test_composite_cascade_preserves_other_cohorts_and_standalone_sources(study_cleanup_http, direct_study_scope):
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import DatasetPersonaRuns, DatasetSources, Personas, Studies
    from bebshax.jobs.orm import JobFileCleanup
    from bebshax.personas.orm import PersonaSourceSelections, PersonaVersions

    context = study_cleanup_http
    cohorts = [
        ("composite-target", "owner-1"),
        ("composite-sibling", "owner-1"),
        ("composite-foreign", "owner-2"),
        ("composite-standalone", "owner-1"),
    ]
    cohort_files = {}
    async with context.maker() as session, session.begin():
        assert await session.scalar(text("PRAGMA foreign_keys")) == 1
        for cohort, owner_id in cohorts:
            study_id = None if cohort == "composite-standalone" else f"{cohort}-study"
            dataset_id = f"{cohort}-dataset"
            version_id = f"{cohort}-version"
            run_id = f"{cohort}-run" if study_id else None
            persona_id = f"{cohort}-persona"
            records = b'[{"age": 25}]'
            digest = hashlib.sha256(records).hexdigest()
            file_path = context.upload_root / f"{dataset_id}.json"
            file_path.write_bytes(records)
            cohort_files[file_path] = records
            if study_id:
                session.add(Studies(id=study_id, user_id=owner_id, title="Synthetic composite scope"))
                await session.flush()
            session.add(DatasetSources(
                id=dataset_id, user_id=owner_id, study_id=study_id, name="Synthetic composite dataset",
                file_path=str(file_path), content_hash=digest,
            ))
            await session.flush()
            session.add(DatasetVersions(
                id=version_id, dataset_id=dataset_id, owner_id=owner_id, version=1,
                content_hash=digest, records_hash=digest, file_path=str(file_path), file_type="json",
                row_count=1, column_count=1, schema_metadata={}, statistics={}, segments=[],
            ))
            if run_id:
                session.add(DatasetPersonaRuns(
                    id=run_id, dataset_id=dataset_id, user_id=owner_id, study_id=study_id,
                    model_used="synthetic-composite-fixture", requested_count=1, generated_count=1,
                ))
            await session.flush()
            session.add(Personas(
                id=persona_id, owner_id=owner_id, user_id=owner_id,
                study_id=study_id if direct_study_scope else None,
                name=f"Synthetic {cohort}", version=1, dataset_persona_run_id=run_id,
                dataset_version_id=version_id if run_id else None,
            ))
            await session.flush()
            session.add(PersonaVersions(
                persona_id=persona_id, version=1, owner_id=owner_id,
                study_id=study_id if direct_study_scope else None, snapshot={"id": persona_id, "version": 1},
            ))
            await session.flush()
            session.add(PersonaSourceSelections(
                id=f"{cohort}-selection", owner_id=owner_id, scope_owner_id=owner_id,
                persona_id=persona_id, persona_version=1, persona_owner_id=owner_id,
                dataset_id=dataset_id, source_namespace="synthetic-composite-fixture", source_record_id=cohort,
            ))

    response = await context.client.delete("/api/studies/composite-target-study")

    assert response.status_code == 200, response.text
    assert response.json() == {"success": True, "deleted_id": "composite-target-study"}
    expected_ids = {
        Studies: {"cleanup-study", "keep-study", "composite-sibling-study", "composite-foreign-study"},
        DatasetSources: {
            "cleanup-versioned", "cleanup-legacy", "cleanup-pathless", "keep-dataset",
            "composite-sibling-dataset", "composite-foreign-dataset", "composite-standalone-dataset",
        },
        DatasetVersions: {
            "cleanup-version-1", "cleanup-version-2", "composite-sibling-version",
            "composite-foreign-version", "composite-standalone-version",
        },
        DatasetPersonaRuns: {"composite-sibling-run", "composite-foreign-run"},
        Personas: {"composite-sibling-persona", "composite-foreign-persona", "composite-standalone-persona"},
        PersonaSourceSelections: {
            "composite-sibling-selection", "composite-foreign-selection", "composite-standalone-selection",
        },
    }
    async with context.maker() as session:
        remaining_ids = {
            model.__tablename__: set(await session.scalars(select(model.id))) for model in expected_ids
        }
        assert remaining_ids == {model.__tablename__: identifiers for model, identifiers in expected_ids.items()}
        assert set((await session.execute(select(PersonaVersions.persona_id, PersonaVersions.version))).all()) == {
            ("composite-sibling-persona", 1), ("composite-foreign-persona", 1), ("composite-standalone-persona", 1),
        }
        journal = list(await session.scalars(select(JobFileCleanup)))
        target_file = context.upload_root / "composite-target-dataset.json"
        assert [(entry.dataset_id, entry.file_path, entry.content_hash, entry.owner_id) for entry in journal] == [
            ("composite-target-dataset", str(target_file), hashlib.sha256(cohort_files[target_file]).hexdigest(), "owner-1"),
        ]
        assert journal[0].status == "pending" and journal[0].attempts == 0
        assert not (await session.execute(text("PRAGMA foreign_key_check"))).all()
    for path, records in {**context.files, **cohort_files}.items():
        assert path.read_bytes() == records
    assert context.kept_path.exists()
    context.optional_cleanup.assert_not_awaited()


async def test_delete_locks_study_before_dataset_rows_in_postgresql_sql(study_cleanup_http):
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.sql.selectable import Select

    context = study_cleanup_http
    statements = []

    def record_statement(connection, cursor, statement, parameters, execution_context, executemany):
        if execution_context.compiled is not None:
            statements.append(execution_context.compiled.statement)

    event.listen(context.engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        response = await context.client.delete("/api/studies/cleanup-study")
    finally:
        event.remove(context.engine.sync_engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200, response.text
    selects = [statement for statement in statements if isinstance(statement, Select)]
    assert [statement.get_final_froms()[0].name for statement in selects[:2]] == ["studies", "dataset_sources"]
    lock_sql = [str(statement.compile(dialect=postgresql.dialect())) for statement in selects[:2]]
    assert all(sql.rstrip().endswith("FOR UPDATE") for sql in lock_sql), lock_sql


@pytest.mark.parametrize("study_id", ["cycle-target-study", "cycle-absent-study"])
async def test_composite_scope_cycles_do_not_match_unrelated_parent_rows(journal_engine, study_id):
    from sqlalchemy import Column, ForeignKey, ForeignKeyConstraint, MetaData, String, Table, UniqueConstraint

    from bebshax.api.studies import _scoped_rows, study_scoped_tables

    metadata = MetaData()
    studies = Table("studies", metadata, Column("id", String, primary_key=True))
    roots = Table(
        "cycle_roots", metadata,
        Column("id", String, primary_key=True), Column("owner_id", String, nullable=False),
        Column("study_id", String, ForeignKey("studies.id"), nullable=False), Column("backlink_id", String),
        UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(
            ["backlink_id", "owner_id"], ["cycle_nodes.id", "cycle_nodes.owner_id"], use_alter=True,
        ),
    )
    nodes = Table(
        "cycle_nodes", metadata,
        Column("id", String, primary_key=True), Column("owner_id", String, nullable=False),
        Column("root_id", String), Column("parent_id", String), UniqueConstraint("id", "owner_id"),
        ForeignKeyConstraint(["root_id", "owner_id"], ["cycle_roots.id", "cycle_roots.owner_id"]),
        ForeignKeyConstraint(["parent_id", "owner_id"], ["cycle_nodes.id", "cycle_nodes.owner_id"]),
    )
    cohorts = [("cycle-target", "owner-1"), ("cycle-sibling", "owner-1"), ("cycle-foreign", "owner-2")]
    async with journal_engine.begin() as connection:
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
        await connection.run_sync(metadata.create_all)
        await connection.execute(studies.insert(), [{"id": f"{cohort}-study"} for cohort, owner_id in cohorts])
        await connection.execute(roots.insert(), [
            {"id": cohort, "owner_id": owner_id, "study_id": f"{cohort}-study", "backlink_id": None}
            for cohort, owner_id in cohorts
        ])
        await connection.execute(nodes.insert(), [
            {"id": cohort, "owner_id": owner_id, "root_id": cohort, "parent_id": None}
            for cohort, owner_id in cohorts
        ] + [{"id": "cycle-standalone", "owner_id": "owner-1", "root_id": None, "parent_id": "cycle-sibling"}])
        for cohort, owner_id in cohorts:
            await connection.execute(roots.update().where(roots.c.id == cohort).values(backlink_id=cohort))
        assert not (await connection.execute(text("PRAGMA foreign_key_check"))).all()

        scoped = study_scoped_tables(metadata)
        remaining_scope = {
            table.name: set(await connection.scalars(select(table.c.id).where(_scoped_rows(table, study_id, scoped))))
            for table in (roots, nodes)
        }
        expected_ids = {"cycle-target"} if study_id == "cycle-target-study" else set()
        assert remaining_scope == {"cycle_roots": expected_ids, "cycle_nodes": expected_ids}


async def test_cleanup_journal_survives_database_reopen_and_worker_restart(study_cleanup_http, study_cleanup_worker_factory):
    from bebshax.db.models import Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    response = await context.client.delete("/api/studies/cleanup-study")
    assert response.status_code == 200
    await context.engine.dispose()
    restarted = study_cleanup_worker_factory()
    assert await restarted.service.cleanup_pending_files() == len(context.expected_cleanup)
    async with restarted.maker() as session:
        assert await session.get(Studies, "cleanup-study") is None
        entries = list(await session.scalars(select(JobFileCleanup)))
        assert len(entries) == len(context.expected_cleanup)
        assert all(entry.status == "completed" and entry.attempts == 1 and entry.completed_at for entry in entries)
        assert not (await session.execute(text("PRAGMA foreign_key_check"))).all()
    assert not any(path.exists() for path in context.files)
    assert context.kept_path.exists()
    second_restart = study_cleanup_worker_factory()
    assert await second_restart.service.cleanup_pending_files() == 0


async def test_committed_delete_succeeds_despite_unlink_failure_and_retries_after_restart(
    study_cleanup_http, study_cleanup_worker_factory, monkeypatch,
):
    from bebshax.db.models import DatasetSources, Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    unlink = Path.unlink
    failed_paths = []

    def locked_file(path, *args, **kwargs):
        if path in context.files:
            failed_paths.append(path)
            raise PermissionError("Synthetic file lock")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as permissions:
        permissions.setattr(Path, "unlink", locked_file)
        response = await context.client.delete("/api/studies/cleanup-study")
        assert response.status_code == 200
        assert failed_paths == []
        context.optional_cleanup.assert_not_awaited()
        restarted = study_cleanup_worker_factory()
        assert await restarted.service.cleanup_pending_files() == 0
        assert set(failed_paths) == set(context.files)
        async with restarted.maker() as session:
            assert await session.get(Studies, "cleanup-study") is None
            assert not list(await session.scalars(select(DatasetSources).where(DatasetSources.study_id == "cleanup-study")))
            entries = list(await session.scalars(select(JobFileCleanup)))
            assert len(entries) == len(context.expected_cleanup)
            assert all(entry.status == "failed" and entry.error_code == "file_unlink_failed" and entry.attempts == 1 for entry in entries)
        for path, records in context.files.items():
            assert path.read_bytes() == records

    second_restart = study_cleanup_worker_factory()
    assert await second_restart.service.cleanup_pending_files() == len(context.expected_cleanup)
    async with second_restart.maker() as session:
        entries = list(await session.scalars(select(JobFileCleanup)))
        assert all(entry.status == "completed" and entry.attempts == 2 for entry in entries)
    assert not any(path.exists() for path in context.files)
    assert context.kept_path.exists()


async def test_delete_empty_study_does_not_enqueue_unrelated_files(study_cleanup_http):
    from bebshax.db.models import Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    async with context.maker() as session, session.begin():
        session.add(Studies(id="empty-study", user_id="owner-1", title="Empty synthetic study"))
    response = await context.client.delete("/api/studies/empty-study")
    assert response.status_code == 200
    async with context.maker() as session:
        assert await session.get(Studies, "empty-study") is None
        assert await session.get(Studies, "cleanup-study") is not None
        assert not list(await session.scalars(select(JobFileCleanup)))
    assert all(path.exists() for path in context.files)
    context.optional_cleanup.assert_not_awaited()


async def test_repeated_study_delete_does_not_duplicate_cleanup_entries(study_cleanup_http):
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    assert (await context.client.delete("/api/studies/cleanup-study")).status_code == 200
    repeated = await context.client.delete("/api/studies/cleanup-study")
    assert repeated.status_code == 404
    async with context.maker() as session:
        assert len(list(await session.scalars(select(JobFileCleanup)))) == len(context.expected_cleanup)
    assert all(path.exists() for path in context.files)
    context.optional_cleanup.assert_not_awaited()


@pytest.mark.parametrize("case, study_id, status_code", [
    ("missing", "absent-study", 404),
    ("foreign", "keep-study", 404),
    ("demo", "keep-study", 403),
    ("anonymous", "cleanup-study", 404),
])
async def test_study_delete_denials_preserve_rows_files_and_journal(study_cleanup_http, case, study_id, status_code):
    from bebshax.api import deps
    from bebshax.db.models import DatasetSources, Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http
    if case == "demo":
        async with context.maker() as session, session.begin():
            await session.execute(update(Studies).where(Studies.id == "keep-study").values(is_demo=True))
    elif case == "anonymous":
        context.app.dependency_overrides[deps.get_optional_tenant_user] = lambda: None
    response = await context.client.delete(f"/api/studies/{study_id}")
    assert response.status_code == status_code, response.text
    async with context.maker() as session:
        assert await session.get(Studies, "cleanup-study") is not None
        assert await session.get(Studies, "keep-study") is not None
        assert len(list(await session.scalars(select(DatasetSources)))) == 4
        assert not list(await session.scalars(select(JobFileCleanup)))
    assert all(path.exists() for path in context.files)
    assert context.kept_path.exists()
    context.optional_cleanup.assert_not_awaited()


@pytest.mark.parametrize("failure_stage", ["enqueue", "cascade", "commit"])
async def test_delete_rolls_back_database_and_journal_without_touching_files(study_cleanup_http, monkeypatch, failure_stage):
    from bebshax.api import studies
    from bebshax.datasets.service import enqueue_dataset_cleanup
    from bebshax.datasets.orm import DatasetVersions
    from bebshax.db.models import DatasetSources, Studies
    from bebshax.jobs.orm import JobFileCleanup

    context = study_cleanup_http

    async def fail_enqueue(session, dataset):
        await enqueue_dataset_cleanup(session, dataset)
        await session.flush()
        raise RuntimeError("Synthetic enqueue failure")

    def fail_cascade(connection, cursor, statement, parameters, execution_context, executemany):
        compiled = execution_context.compiled
        if compiled is not None and isinstance(compiled.statement, Delete) and compiled.statement.table.name == "dataset_sources":
            raise RuntimeError("Synthetic cascade failure")

    async def fail_commit(session):
        await session.flush()
        raise RuntimeError("Synthetic commit failure")

    if failure_stage == "enqueue":
        monkeypatch.setattr(studies, "enqueue_dataset_cleanup", fail_enqueue, raising=False)
    elif failure_stage == "cascade":
        event.listen(context.engine.sync_engine, "before_cursor_execute", fail_cascade)
    else:
        monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match=f"Synthetic {failure_stage} failure"):
            await context.client.delete("/api/studies/cleanup-study")
    finally:
        if failure_stage == "cascade":
            event.remove(context.engine.sync_engine, "before_cursor_execute", fail_cascade)
    context.request_sessions[-1].rollback.assert_awaited_once()
    async with context.maker() as session:
        assert await session.get(Studies, "cleanup-study") is not None
        assert len(list(await session.scalars(select(DatasetSources).where(DatasetSources.study_id == "cleanup-study")))) == 3
        assert len(list(await session.scalars(select(DatasetVersions)))) == 2
        assert not list(await session.scalars(select(JobFileCleanup)))
        assert not (await session.execute(text("PRAGMA foreign_key_check"))).all()
    for path, records in context.files.items():
        assert path.read_bytes() == records
    assert context.kept_path.exists()
    context.optional_cleanup.assert_not_awaited()
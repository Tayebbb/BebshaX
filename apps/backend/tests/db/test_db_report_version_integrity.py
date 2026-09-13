"""Report version backstops and data-preserving forward migration contracts."""

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.db.models import StudyReports


REVISION = "f2b4d6e8a013"
PREDECESSOR = "e7a9c1d3f205"
SCRIPT_PATH = Path(__file__).resolve().parents[2] / "alembic"
UNIQUE_NAME = "uq_study_reports_study_version"
CHECK_NAME = "ck_study_reports_positive_version"


def _report(identity: str, *, study_id: str = "report-study", version: int = 1, user_id: str | None = None) -> StudyReports:
    return StudyReports(
        id=identity, study_id=study_id, user_id=user_id, version=version,
        title="Synthetic report", executive_summary="Complete synthetic report history " * 100,
        key_findings=["Synthetic finding"],
    )


@pytest.mark.parametrize("user_id", [None, "different-owner"])
async def test_report_versions_are_unique_per_study_even_with_different_or_null_owners(
    async_session: AsyncSession, user_id: str | None,
) -> None:
    async_session.add(_report("retained-report", user_id="report-owner"))
    await async_session.commit()
    with pytest.raises(IntegrityError):
        async with async_session.begin_nested():
            async_session.add(_report("duplicate-report", user_id=user_id))
            await async_session.flush()
    assert await async_session.get(StudyReports, "retained-report") is not None
    assert await async_session.get(StudyReports, "duplicate-report") is None


@pytest.mark.parametrize("version", [0, -1])
async def test_report_versions_must_be_positive(async_session: AsyncSession, version: int) -> None:
    async_session.add(_report("invalid-report", version=version))
    with pytest.raises(IntegrityError):
        await async_session.flush()


async def test_report_version_sequence_is_independent_for_each_study(async_session: AsyncSession) -> None:
    async_session.add_all([
        _report("first-report"), _report("next-report", version=2),
        _report("other-report", study_id="other-study"),
    ])
    await async_session.commit()
    assert await async_session.scalar(sa.select(sa.func.count()).select_from(StudyReports)) == 3


@pytest.fixture
def report_revision() -> ModuleType:
    path = SCRIPT_PATH / "versions" / f"{REVISION}_report_version_integrity.py"
    assert path.is_file(), "Report version integrity requires a new forward migration"
    return ScriptDirectory(str(SCRIPT_PATH)).get_revision(REVISION).module


@pytest.fixture
def legacy_report_connection(monkeypatch: pytest.MonkeyPatch, report_revision: ModuleType) -> Iterator[Connection]:
    table = sa.Table(
        "study_reports", sa.MetaData(),
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("study_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("key_findings", sa.JSON(), nullable=False),
    )
    engine = sa.create_engine("sqlite:///:memory:", hide_parameters=True)
    try:
        with engine.begin() as connection:
            table.create(connection)
            connection.execute(table.insert().values(
                id="legacy-report", study_id="legacy-study", user_id=None, version=7,
                title="Unattributed synthetic report", executive_summary="Complete historical report " * 100,
                key_findings=["Complete synthetic historical finding"],
            ))
            monkeypatch.setattr(report_revision, "op", Operations(MigrationContext.configure(connection)))
            yield connection
    finally:
        engine.dispose()


def test_report_backstops_extend_the_existing_single_head(report_revision: ModuleType) -> None:
    scripts = ScriptDirectory(str(SCRIPT_PATH))
    assert scripts.get_heads() == ["1a3c5e7f9b2d"]
    assert scripts.get_revision("1a3c5e7f9b2d").down_revision == REVISION
    assert report_revision.down_revision == PREDECESSOR
    assert scripts.get_revision(PREDECESSOR).down_revision == "d4e6f8a0b219"


def test_report_upgrade_preserves_complete_history_and_null_owners(
    legacy_report_connection: Connection, report_revision: ModuleType,
) -> None:
    before = legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all()
    report_revision.upgrade()
    report_revision.upgrade()
    after = legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all()
    assert after == before
    inspector = sa.inspect(legacy_report_connection)
    assert {constraint["name"] for constraint in inspector.get_unique_constraints("study_reports")} == {UNIQUE_NAME}
    assert {constraint["name"] for constraint in inspector.get_check_constraints("study_reports")} == {CHECK_NAME}
    with pytest.raises(IntegrityError):
        legacy_report_connection.execute(sa.text("UPDATE study_reports SET version = 0"))


@pytest.mark.parametrize("invalid_history", ["duplicate", "zero", "negative"])
def test_ambiguous_report_history_aborts_before_ddl_without_deleting_or_renumbering(
    legacy_report_connection: Connection, report_revision: ModuleType, invalid_history: str,
) -> None:
    if invalid_history == "duplicate":
        legacy_report_connection.execute(sa.text(
            "INSERT INTO study_reports SELECT 'duplicate-report', study_id, 'different-owner', version, "
            "title, executive_summary, key_findings FROM study_reports"
        ))
    else:
        legacy_report_connection.execute(sa.text("UPDATE study_reports SET version = :version"), {
            "version": 0 if invalid_history == "zero" else -1,
        })
    before = legacy_report_connection.execute(sa.text("SELECT * FROM study_reports ORDER BY id")).mappings().all()
    with pytest.raises(RuntimeError, match="[Rr]eport.*history"):
        report_revision.upgrade()
    assert legacy_report_connection.execute(sa.text("SELECT * FROM study_reports ORDER BY id")).mappings().all() == before
    assert sa.inspect(legacy_report_connection).get_unique_constraints("study_reports") == []
    assert sa.inspect(legacy_report_connection).get_check_constraints("study_reports") == []


@pytest.mark.parametrize("constraint", ["unique", "check"])
def test_conflicting_report_constraint_shape_aborts_before_other_ddl(
    legacy_report_connection: Connection, report_revision: ModuleType, constraint: str,
) -> None:
    with report_revision.op.batch_alter_table("study_reports") as batch:
        if constraint == "unique":
            batch.create_unique_constraint(UNIQUE_NAME, ["study_id", "version", "user_id"])
        else:
            batch.create_check_constraint(CHECK_NAME, "version >= 0")
    before = legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all()
    with pytest.raises(RuntimeError, match="conflict"):
        report_revision.upgrade()
    assert legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all() == before
    inspector = sa.inspect(legacy_report_connection)
    assert len(inspector.get_unique_constraints("study_reports")) == (constraint == "unique")
    assert len(inspector.get_check_constraints("study_reports")) == (constraint == "check")


@pytest.mark.parametrize("empty", [False, True])
def test_report_constraint_roundtrip_retains_rows(
    legacy_report_connection: Connection, report_revision: ModuleType, empty: bool,
) -> None:
    if empty:
        legacy_report_connection.execute(sa.text("DELETE FROM study_reports"))
    before = legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all()
    report_revision.upgrade()
    report_revision.downgrade()
    assert sa.inspect(legacy_report_connection).get_unique_constraints("study_reports") == []
    assert sa.inspect(legacy_report_connection).get_check_constraints("study_reports") == []
    assert legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all() == before
    report_revision.upgrade()
    assert legacy_report_connection.execute(sa.text("SELECT * FROM study_reports")).mappings().all() == before


def test_report_offline_postgresql_sql_only_adds_validated_constraints(report_revision: ModuleType) -> None:
    config = Config()
    config.set_main_option("script_location", str(SCRIPT_PATH))
    config.attributes["database_url"] = "postgresql+asyncpg://offline.invalid/synthetic"
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, f"{PREDECESSOR}:{REVISION}", sql=True)
    sql = output.getvalue()
    assert f"CONSTRAINT {UNIQUE_NAME} UNIQUE (study_id, version)" in sql
    assert f"CONSTRAINT {CHECK_NAME} CHECK (version >= 1) NOT VALID" in sql
    assert f"VALIDATE CONSTRAINT {CHECK_NAME}" in sql
    assert "DROP " not in sql and "DELETE " not in sql
    assert "UPDATE study_reports" not in sql
    assert "COMMIT;" in sql
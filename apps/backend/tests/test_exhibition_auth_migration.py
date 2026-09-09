"""Session-version migration checks without loading Alembic's online environment."""

from io import StringIO
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from bebshax.auth.models import Users


_REVISION = "a9c2e7b6d410"
_PARENT = "f2a3b4c5d6e7"


@pytest.fixture
def migration():
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
    matches = [revision for revision in scripts.walk_revisions() if revision.revision == _REVISION]
    assert len(matches) == 1, "Expected the new, uniquely named auth session migration"
    return matches[0]


def test_session_migration_is_the_unique_child_of_the_current_head(migration):
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
    revisions = list(scripts.walk_revisions())

    assert migration.down_revision == _PARENT
    assert scripts.get_heads() == [_REVISION]
    assert len(revisions) == len({revision.revision for revision in revisions})
    assert "test" not in Path(migration.path).name.lower()


def test_users_session_version_has_nonnullable_integer_and_zero_defaults():
    column = Users.__table__.columns.get("session_version")

    assert column is not None
    assert isinstance(column.type, sa.Integer)
    assert column.nullable is False
    assert column.default.arg == 0
    assert str(column.server_default.arg) == "0"


def test_migration_backfills_preserves_and_reverses_existing_users(migration):
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    users = sa.Table(
        "users", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
    )
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(users.insert().values(id="usr_existing", email="existing@example.com"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.module.upgrade()
                migration.module.upgrade()
            migrated = sa.Table("users", sa.MetaData(), autoload_with=connection)
            assert connection.execute(sa.select(migrated.c.session_version)).scalar_one() == 0
            connection.execute(users.insert().values(id="usr_new", email="new@example.com"))
            assert connection.execute(
                sa.select(migrated.c.session_version).where(migrated.c.id == "usr_new"),
            ).scalar_one() == 0
            assert migrated.c.session_version.nullable is False
            with Operations.context(MigrationContext.configure(connection)):
                migration.module.downgrade()
            assert {column["name"] for column in sa.inspect(connection).get_columns("users")} == {
                "id", "email",
            }
            assert connection.execute(sa.select(users).order_by(users.c.id)).all() == [
                ("usr_existing", "existing@example.com"), ("usr_new", "new@example.com"),
            ]
    finally:
        engine.dispose()


def test_migration_emits_additive_postgresql_sql_without_a_database(migration):
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output},
    )

    with Operations.context(context):
        migration.module.upgrade()

    sql = output.getvalue().upper()
    assert "ALTER TABLE USERS ADD COLUMN SESSION_VERSION INTEGER" in sql
    assert "DEFAULT" in sql and "0" in sql and "NOT NULL" in sql
    assert "DROP" not in sql and "DELETE" not in sql
"""Integrate existing modernization mappings without rewriting applied revisions.

Revision ID: c6f8a2d4e901
Revises: b1bf09c4d2e7

The owner confirmed on 2026-09-10 that this revision has never been applied
to a user database. The memory attribution correction is pre-deployment only.
"""

from alembic import op
from alembic.operations.ops import CreateIndexOp, CreateTableOp
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6f8a2d4e901"
down_revision: str = "b1bf09c4d2e7"
branch_labels: str | None = None
depends_on: str | None = None


def _new_tables() -> tuple[sa.Table, ...]:
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(64), primary_key=True))
    sa.Table("personas", metadata, sa.Column("id", sa.String(64), primary_key=True))
    sa.Table("dataset_sources", metadata, sa.Column("id", sa.String(64), primary_key=True))
    owners = sa.Table(
        "job_owners", metadata,
        sa.Column("owner_id", sa.String(255), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    jobs = sa.Table(
        "durable_jobs", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(255), sa.ForeignKey("job_owners.owner_id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_revision", sa.String(255), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(64), nullable=True),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("result_refs", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_job_idempotency"),
        sa.Index("ix_jobs_owner_status", "owner_id", "status"),
        sa.Index("ix_jobs_recovery", "status", "lease_expires_at"),
    )
    attempts = sa.Table(
        "job_attempts", metadata,
        sa.Column("job_id", sa.String(64), sa.ForeignKey("durable_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("worker_id", sa.String(64), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    checkpoints = sa.Table(
        "job_checkpoints", metadata,
        sa.Column("job_id", sa.String(64), sa.ForeignKey("durable_jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_key", sa.String(255), primary_key=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("input_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("result_refs", sa.JSON(), nullable=True),
        sa.Column("lease_token", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    cleanup = sa.Table(
        "job_file_cleanup", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index("ix_job_file_cleanup_dataset_id", "dataset_id"),
        sa.Index("ix_job_file_cleanup_status", "status"),
    )
    datasets = sa.Table(
        "dataset_versions", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_id", sa.String(64), sa.ForeignKey("dataset_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("records_hash", sa.String(64), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_file_path", sa.Text(), nullable=True),
        sa.Column("file_type", sa.String(64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("schema_metadata", sa.JSON(), nullable=False),
        sa.Column("statistics", sa.JSON(), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
        sa.Index("ix_dataset_versions_dataset_id", "dataset_id"),
        sa.Index("ix_dataset_versions_owner_id", "owner_id"),
    )
    personas = sa.Table(
        "persona_versions", metadata,
        sa.Column("persona_id", sa.String(64), sa.ForeignKey("personas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("study_id", sa.String(64), nullable=True),
        sa.Column("snapshot", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("legacy_profile", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("capture_kind", sa.String(32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_persona_versions_positive_version"),
        sa.CheckConstraint("capture_kind IN ('generated', 'observed_current')", name="ck_persona_versions_capture_kind"),
        sa.Index("ix_persona_versions_study_id", "study_id"),
        sa.Index("ix_persona_versions_owner_persona", "owner_id", "persona_id"),
    )
    sessions = sa.Table(
        "auth_sessions", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("family_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Index("ix_auth_sessions_family_id", "family_id"),
        sa.Index("ix_auth_sessions_user_id", "user_id"),
    )
    rate_limits = sa.Table(
        "auth_rate_limits", metadata,
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Index("ix_auth_rate_limits_expires_at", "expires_at"),
    )
    return owners, jobs, attempts, checkpoints, cleanup, datasets, personas, sessions, rate_limits


def _added_columns() -> tuple[tuple[str, sa.Column], ...]:
    return (
        ("users", sa.Column("role", sa.String(32), nullable=False, server_default="user")),
        ("users", sa.Column("legacy_tokens_revoked_at", sa.DateTime(timezone=True), nullable=True)),
        ("studies", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")),
        ("email_verification_tokens", sa.Column("purpose", sa.String(32), nullable=False, server_default="email-verification")),
        ("email_verification_tokens", sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0")),
        ("email_verification_tokens", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0")),
        ("conversations", sa.Column("persona_snapshot", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True)),
        ("llm_requests", sa.Column("owner_id", sa.String(64), nullable=True,
                                  comment="Immutable request-time owner; NULL means private unknown owner; no FK")),
        ("memory_items", sa.Column("owner_id", sa.String(64), nullable=True)),
        ("behavioral_test_runs", sa.Column("job_id", sa.String(64), nullable=True)),
        ("behavioral_test_runs", sa.Column("execution_token", sa.String(64), nullable=True)),
        ("behavioral_test_runs", sa.Column("input_manifest", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True)),
    )


def _added_indexes() -> tuple[sa.Index, ...]:
    metadata = sa.MetaData()
    memory = sa.Table("memory_items", metadata, sa.Column("owner_id", sa.String(64)))
    runs = sa.Table("behavioral_test_runs", metadata, sa.Column("job_id", sa.String(64)))
    provenance = sa.Table(
        "llm_requests", metadata,
        sa.Column("owner_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    return (
        sa.Index("ix_memory_items_owner_id", memory.c.owner_id),
        sa.Index("ix_behavioral_test_runs_job_id", runs.c.job_id),
        sa.Index("ix_llm_requests_owner_created_at", provenance.c.owner_id, provenance.c.created_at.desc()),
    )


def _assert_column_shape(expected: sa.Column, actual: dict, dialect) -> None:
    if (
        actual["nullable"] != expected.nullable
        or str(actual["type"].compile(dialect=dialect)) != str(expected.type.compile(dialect=dialect))
    ):
        raise RuntimeError("Existing modernization column conflicts with the frozen migration; reconcile before upgrading")


def _assert_existing_table(table: sa.Table, inspector, dialect) -> None:
    columns = {column["name"]: column for column in inspector.get_columns(table.name)}
    if set(columns) != set(table.columns.keys()):
        raise RuntimeError(f"Existing {table.name} columns conflict with the frozen migration; reconcile before upgrading")
    for column in table.columns:
        _assert_column_shape(column, columns[column.name], dialect)
    primary_key = inspector.get_pk_constraint(table.name)["constrained_columns"]
    if primary_key != list(table.primary_key.columns.keys()):
        raise RuntimeError(f"Existing {table.name} primary key conflicts with the frozen migration")
    expected_foreign_keys = {
        (tuple(element.parent.name for element in constraint.elements),
         constraint.referred_table.name,
         tuple(element.column.name for element in constraint.elements), constraint.ondelete)
        for constraint in table.foreign_key_constraints
    }
    actual_foreign_keys = {
        (tuple(constraint["constrained_columns"]), constraint["referred_table"],
         tuple(constraint["referred_columns"]), constraint.get("options", {}).get("ondelete"))
        for constraint in inspector.get_foreign_keys(table.name)
    }
    expected_uniques = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints if isinstance(constraint, sa.UniqueConstraint)
    }
    actual_uniques = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table.name)
    }
    expected_named_uniques = {
        (constraint.name, tuple(constraint.columns.keys()))
        for constraint in table.constraints if isinstance(constraint, sa.UniqueConstraint) and constraint.name is not None
    }
    actual_named_uniques = {
        (constraint["name"], tuple(constraint["column_names"]))
        for constraint in inspector.get_unique_constraints(table.name)
    }
    expected_checks = {constraint.name for constraint in table.constraints if isinstance(constraint, sa.CheckConstraint)}
    actual_checks = {constraint["name"] for constraint in inspector.get_check_constraints(table.name)}
    if ((expected_foreign_keys, expected_uniques, expected_checks) != (actual_foreign_keys, actual_uniques, actual_checks)
            or not expected_named_uniques <= actual_named_uniques):
        raise RuntimeError(f"Existing {table.name} constraints conflict with the frozen migration")


def _ensure_index(index: sa.Index) -> None:
    if not op.get_context().as_sql:
        indexes = sa.inspect(op.get_bind()).get_indexes(index.table.name)
        existing = next((current for current in indexes if current["name"] == index.name), None)
        if existing is not None:
            if existing["column_names"] != list(index.columns.keys()) or bool(existing["unique"]) != bool(index.unique):
                raise RuntimeError(f"Existing {index.name} conflicts with the frozen migration")
            return
    op.invoke(CreateIndexOp.from_index(index))


def _ensure_unique(table_name: str, name: str, column_names: tuple[str, ...]) -> None:
    offline = op.get_context().as_sql
    bind = op.get_bind()
    if not offline:
        for constraint in sa.inspect(bind).get_unique_constraints(table_name):
            if constraint["name"] == name:
                if tuple(constraint["column_names"]) != column_names:
                    raise RuntimeError(f"Existing {name} conflicts with the frozen migration")
                return
    table = sa.table(table_name, *(sa.column(column_name) for column_name in column_names))
    duplicates = (
        sa.select(sa.literal(1)).select_from(table)
        .where(*(column.is_not(None) for column in table.c))
        .group_by(*table.c).having(sa.func.count() > 1).limit(1)
    )
    message = f"Legacy duplicates block {name}; reconcile without deleting history before upgrading"
    if offline:
        query = str(duplicates.compile(dialect=bind.dialect, compile_kwargs={"literal_binds": True}))
        op.execute(f"DO $$ BEGIN IF EXISTS ({query}) THEN RAISE EXCEPTION '{message}'; END IF; END $$")
    elif bind.execute(duplicates).first() is not None:
        raise RuntimeError(message)
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table_name) as batch:
            batch.create_unique_constraint(name, list(column_names))
    else:
        op.create_unique_constraint(name, table_name, list(column_names))


def _backfill_memory_owners() -> None:
    memory = sa.table("memory_items", sa.column("owner_id"), sa.column("persona_id"), sa.column("conversation_id"))
    conversations = sa.table(
        "conversations", sa.column("id"), sa.column("persona_id"), sa.column("user_id"), sa.column("study_id"),
    )
    personas = sa.table(
        "personas", sa.column("id"), sa.column("owner_id"), sa.column("user_id"),
        sa.column("study_id"), sa.column("business_id"),
    )
    businesses = sa.table("businesses", sa.column("id"), sa.column("owner_id"))
    studies = sa.table("studies", sa.column("id"), sa.column("user_id"))
    users = sa.table("users", sa.column("id"))
    shared_owners = ("usr_system_holder", "usr_default", "anonymous")
    verified_owner = (
        sa.select(conversations.c.user_id)
        .select_from(
            conversations.join(users, users.c.id == conversations.c.user_id)
            .join(personas, personas.c.id == conversations.c.persona_id)
            .outerjoin(studies, studies.c.id == conversations.c.study_id)
            .outerjoin(businesses, businesses.c.id == personas.c.business_id)
        )
        .where(
            conversations.c.id == memory.c.conversation_id,
            conversations.c.persona_id == memory.c.persona_id,
            conversations.c.user_id.not_in(shared_owners),
            sa.func.length(sa.func.trim(conversations.c.user_id)) > 0,
            sa.or_(personas.c.owner_id == conversations.c.user_id, personas.c.owner_id.in_(shared_owners)),
            sa.or_(
                personas.c.user_id.is_(None), personas.c.user_id == conversations.c.user_id,
                personas.c.user_id.in_(shared_owners),
            ),
            sa.or_(
                personas.c.business_id.is_(None), businesses.c.owner_id == conversations.c.user_id,
                businesses.c.owner_id.in_(shared_owners),
            ),
            sa.or_(personas.c.study_id.is_(None), personas.c.study_id == conversations.c.study_id),
            sa.or_(conversations.c.study_id.is_(None), studies.c.user_id == conversations.c.user_id),
        )
        .scalar_subquery()
    )
    op.execute(sa.update(memory).where(memory.c.owner_id.is_(None)).values(owner_id=verified_owner))


def upgrade() -> None:
    bind = op.get_bind()
    offline = op.get_context().as_sql
    tables = _new_tables()
    existing_tables = set() if offline else set(sa.inspect(bind).get_table_names())
    for table in tables:
        if table.name in existing_tables:
            _assert_existing_table(table, sa.inspect(bind), bind.dialect)
    for table in tables:
        if table.name not in existing_tables:
            op.invoke(CreateTableOp.from_table(table))
        for index in sorted(table.indexes, key=lambda item: item.name):
            _ensure_index(index)
    for table_name, column in _added_columns():
        existing_columns = {} if offline else {
            existing["name"]: existing for existing in sa.inspect(bind).get_columns(table_name)
        }
        if column.name in existing_columns:
            _assert_column_shape(column, existing_columns[column.name], bind.dialect)
        else:
            op.add_column(table_name, column)

    _backfill_memory_owners()
    for column_name in ("personality", "detailed_attributes"):
        op.execute(f"UPDATE personas SET {column_name} = '{{}}' WHERE {column_name} IS NULL")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("personas") as batch:
                batch.alter_column(column_name, existing_type=sa.JSON(), nullable=False)
        else:
            op.alter_column(column_name=column_name, table_name="personas", existing_type=postgresql.JSONB(), nullable=False)

    op.execute("UPDATE conversations SET started_at = created_at WHERE started_at IS NULL")
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("conversations") as batch:
            batch.alter_column("started_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    else:
        op.alter_column("conversations", "started_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    checks = set() if offline else {constraint["name"] for constraint in sa.inspect(bind).get_check_constraints("users")}
    if "ck_users_role" not in checks:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("users") as batch:
                batch.create_check_constraint("ck_users_role", "role IN ('user', 'developer', 'admin')")
        else:
            op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'developer', 'admin')")

    _ensure_unique("memory_items", "uq_memory_owner_persona_content", ("owner_id", "persona_id", "content_hash"))
    _ensure_unique("behavioral_test_results", "uq_behavioral_run_persona", ("test_run_id", "persona_id"))
    for index in _added_indexes():
        _ensure_index(index)


def downgrade() -> None:
    raise RuntimeError("Automatic downgrade would discard durable jobs or immutable history; use a reviewed restore plan")
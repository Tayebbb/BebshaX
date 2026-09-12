"""Typed dataset persona origins and scoped immutable-source selections.

Revision ID: e7a9c1d3f205
Revises: d4e6f8a0b219
"""

import re
import uuid

from alembic import op
from alembic.operations.ops import AddConstraintOp, CreateIndexOp, CreateTableOp
import sqlalchemy as sa


revision: str = "e7a9c1d3f205"
down_revision: str = "d4e6f8a0b219"
branch_labels: str | None = None
depends_on: str | None = None


def _contract_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(64), primary_key=True))
    sa.Table("dataset_versions", metadata, sa.Column("id", sa.String(64), primary_key=True))
    for table_name, owner_name, constraint_name in (
        ("businesses", "owner_id", "uq_businesses_id_owner"),
        ("studies", "user_id", "uq_studies_id_owner"),
        ("dataset_sources", "user_id", "uq_dataset_sources_id_owner"),
        ("dataset_persona_runs", "user_id", "uq_dataset_persona_runs_id_owner"),
    ):
        sa.Table(
            table_name, metadata, sa.Column("id", sa.String(64), primary_key=True), sa.Column(owner_name, sa.String(64)),
            sa.UniqueConstraint("id", owner_name, name=constraint_name),
        )
    sa.Table(
        "persona_versions", metadata,
        sa.Column("persona_id", sa.String(64), primary_key=True), sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.UniqueConstraint("persona_id", "version", "owner_id", name="uq_persona_versions_identity_owner"),
    )
    sa.Table(
        "personas", metadata,
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("generation_run_id", sa.String(64)), sa.Column("segment_id", sa.String(64)),
        sa.Column("dataset_persona_run_id", sa.String(64)), sa.Column("dataset_version_id", sa.String(64)),
        sa.Column("dataset_segment_key", sa.String(256)),
        sa.ForeignKeyConstraint(
            ["dataset_persona_run_id", "owner_id"], ["dataset_persona_runs.id", "dataset_persona_runs.user_id"],
            name="fk_personas_dataset_run_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], name="fk_personas_dataset_version", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("dataset_persona_run_id IS NULL OR generation_run_id IS NULL", name="ck_personas_generation_origin"),
        sa.CheckConstraint("dataset_segment_key IS NULL OR segment_id IS NULL", name="ck_personas_segment_origin"),
        sa.CheckConstraint("dataset_version_id IS NULL OR dataset_persona_run_id IS NOT NULL", name="ck_personas_dataset_version_run"),
        sa.CheckConstraint(
            "dataset_segment_key IS NULL OR (dataset_version_id IS NOT NULL AND length(trim(dataset_segment_key)) > 0)",
            name="ck_personas_dataset_segment_version",
        ),
        sa.Index("ix_personas_dataset_persona_run_id", "dataset_persona_run_id"),
        sa.Index("ix_personas_dataset_version_id", "dataset_version_id"),
    )
    return metadata


def _added_columns() -> tuple[tuple[str, sa.Column], ...]:
    return (
        ("personas", sa.Column("dataset_persona_run_id", sa.String(64), nullable=True)),
        ("personas", sa.Column("dataset_version_id", sa.String(64), nullable=True)),
        ("personas", sa.Column("dataset_segment_key", sa.String(256), nullable=True)),
    )


def _added_constraints() -> tuple[tuple[str, sa.Constraint], ...]:
    metadata = _contract_metadata()
    table_names = ("businesses", "studies", "dataset_sources", "dataset_persona_runs", "persona_versions", "personas")
    return tuple(
        (table_name, constraint)
        for table_name in table_names
        for constraint in sorted(metadata.tables[table_name].constraints, key=lambda item: item.name or "")
        if constraint.name is not None
    )


def _added_indexes() -> tuple[sa.Index, ...]:
    return tuple(sorted(_contract_metadata().tables["personas"].indexes, key=lambda item: item.name))


def _new_tables() -> tuple[sa.Table, ...]:
    metadata = _contract_metadata()
    selections = sa.Table(
        "persona_source_selections", metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("owner_id", sa.String(64), sa.ForeignKey("users.id", name="fk_source_selection_owner", ondelete="RESTRICT"), nullable=False),
        sa.Column("scope_owner_id", sa.String(64), nullable=False),
        sa.Column("persona_id", sa.String(64), nullable=False),
        sa.Column("persona_version", sa.Integer(), nullable=False),
        sa.Column("persona_owner_id", sa.String(64), nullable=False),
        sa.Column("study_id", sa.String(64), nullable=True),
        sa.Column("business_id", sa.String(64), nullable=True),
        sa.Column("dataset_id", sa.String(64), nullable=True),
        sa.Column("source_namespace", sa.String(256), nullable=False),
        sa.Column("source_record_id", sa.String(256), nullable=False),
        sa.Column("source_name", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["persona_id", "persona_version", "persona_owner_id"],
            ["persona_versions.persona_id", "persona_versions.version", "persona_versions.owner_id"],
            name="fk_source_selection_version_owner", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["study_id", "scope_owner_id"], ["studies.id", "studies.user_id"],
            name="fk_source_selection_study_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "scope_owner_id"], ["businesses.id", "businesses.owner_id"],
            name="fk_source_selection_business_owner", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "scope_owner_id"], ["dataset_sources.id", "dataset_sources.user_id"],
            name="fk_source_selection_dataset_owner", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "(CASE WHEN study_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN business_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN dataset_id IS NOT NULL THEN 1 ELSE 0 END) = 1", name="ck_source_selection_one_scope",
        ),
        sa.CheckConstraint(
            "length(trim(owner_id)) > 0 AND owner_id NOT IN ('usr_system_holder', 'usr_default', 'anonymous')",
            name="ck_source_selection_private_owner",
        ),
        sa.CheckConstraint(
            "scope_owner_id = owner_id OR (study_id IS NULL AND scope_owner_id IN ('usr_system_holder', 'usr_default', 'anonymous'))",
            name="ck_source_selection_scope_owner",
        ),
        sa.CheckConstraint(
            "persona_owner_id = owner_id OR persona_owner_id IN ('usr_system_holder', 'usr_default', 'anonymous')",
            name="ck_source_selection_persona_owner",
        ),
        sa.CheckConstraint(
            "length(trim(source_namespace)) > 0 AND length(trim(source_record_id)) > 0",
            name="ck_source_selection_identity",
        ),
        sa.CheckConstraint("released_at IS NULL OR released_at >= created_at", name="ck_source_selection_release_time"),
        sa.Index("ix_source_selections_persona_version", "persona_id", "persona_version"),
        sa.Index(
            "uq_source_active_study", "owner_id", "study_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=sa.text("released_at IS NULL AND study_id IS NOT NULL"),
            sqlite_where=sa.text("released_at IS NULL AND study_id IS NOT NULL"),
        ),
        sa.Index(
            "uq_source_active_business", "owner_id", "business_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=sa.text("released_at IS NULL AND business_id IS NOT NULL"),
            sqlite_where=sa.text("released_at IS NULL AND business_id IS NOT NULL"),
        ),
        sa.Index(
            "uq_source_active_dataset", "owner_id", "dataset_id", "source_namespace", "source_record_id", unique=True,
            postgresql_where=sa.text("released_at IS NULL AND dataset_id IS NOT NULL"),
            sqlite_where=sa.text("released_at IS NULL AND dataset_id IS NOT NULL"),
        ),
    )
    return (selections,)


def _postgresql_check_expression(constraint: sa.CheckConstraint) -> str:
    bind = op.get_bind()
    temporary = sa.Table(
        f"_source_check_{uuid.uuid4().hex}", sa.MetaData(),
        *(sa.Column(column.name, column.type) for column in constraint.table.columns),
        sa.CheckConstraint(str(constraint.sqltext), name="expected_check"),
        prefixes=["TEMPORARY"], postgresql_on_commit="DROP",
    )
    bind.execute(sa.schema.CreateTable(temporary))
    checks = sa.inspect(bind).get_check_constraints(temporary.name)
    expected = next(item["sqltext"] for item in checks if item["name"] == "expected_check")
    bind.execute(sa.schema.DropTable(temporary))
    return expected


def _constraint_exists(table_name: str, constraint: sa.Constraint) -> bool:
    if op.get_context().as_sql:
        return False
    inspector = sa.inspect(op.get_bind())
    if isinstance(constraint, sa.UniqueConstraint):
        candidates = inspector.get_unique_constraints(table_name)
        expected = list(constraint.columns.keys())
        actual = lambda item: item["column_names"]
    elif isinstance(constraint, sa.ForeignKeyConstraint):
        candidates = inspector.get_foreign_keys(table_name)
        expected = (
            list(constraint.columns.keys()), constraint.referred_table.name,
            [element.column.name for element in constraint.elements], constraint.ondelete,
        )
        actual = lambda item: (
            item["constrained_columns"], item["referred_table"], item["referred_columns"],
            item.get("options", {}).get("ondelete"),
        )
    else:
        candidates = inspector.get_check_constraints(table_name)
        expected = str(constraint.sqltext)
        actual = lambda item: item["sqltext"]
    found = next((item for item in candidates if item["name"] == constraint.name), None)
    if found is not None and isinstance(constraint, sa.CheckConstraint) and op.get_bind().dialect.name == "postgresql":
        expected = _postgresql_check_expression(constraint)
    if found is not None and actual(found) != expected:
        raise RuntimeError("Existing source-lineage constraint conflicts with the frozen migration")
    return found is not None


def _assert_columns(table_name: str, columns: list[sa.Column], *, exact: bool = False) -> None:
    bind = op.get_bind()
    existing = {column["name"]: column for column in sa.inspect(bind).get_columns(table_name)}
    if exact and set(existing) != {column.name for column in columns}:
        raise RuntimeError("Existing source-lineage table conflicts with the frozen migration")
    for column in columns:
        actual = existing.get(column.name)
        if actual is not None and (
            actual["nullable"] != column.nullable
            or str(actual["type"].compile(dialect=bind.dialect)) != str(column.type.compile(dialect=bind.dialect))
        ):
            raise RuntimeError("Existing source-lineage column conflicts with the frozen migration")


def _partial_predicate_key(expression: object) -> str:
    return re.sub(r'[()\s"]+', " ", str(expression)).strip().lower()


def _ensure_index(index: sa.Index) -> None:
    if not op.get_context().as_sql:
        existing = next((item for item in sa.inspect(op.get_bind()).get_indexes(index.table.name) if item["name"] == index.name), None)
        if existing is not None:
            dialect_name = op.get_bind().dialect.name
            expected_predicate = index.dialect_options[dialect_name].get("where")
            actual_predicate = existing.get("dialect_options", {}).get(f"{dialect_name}_where")
            if (existing["column_names"] != list(index.columns.keys()) or bool(existing["unique"]) != bool(index.unique)
                    or _partial_predicate_key(actual_predicate) != _partial_predicate_key(expected_predicate)):
                raise RuntimeError("Existing source-lineage index conflicts with the frozen migration")
            return
    op.invoke(CreateIndexOp.from_index(index))


def upgrade() -> None:
    bind = op.get_bind()
    offline = op.get_context().as_sql
    [table] = _new_tables()
    columns = _added_columns()
    constraints = _added_constraints()
    table_exists = not offline and table.name in sa.inspect(bind).get_table_names()
    if not offline:
        _assert_columns("personas", [column for _table_name, column in columns])
        if table_exists:
            _assert_columns(table.name, list(table.columns), exact=True)
            if sa.inspect(bind).get_pk_constraint(table.name)["constrained_columns"] != ["id"]:
                raise RuntimeError("Existing source-lineage primary key conflicts with the frozen migration")
            if not all(_constraint_exists(table.name, constraint) for constraint in table.constraints if constraint.name is not None):
                raise RuntimeError("Existing source-lineage table constraints conflict with the frozen migration")
    missing_constraints = [(name, constraint) for name, constraint in constraints if not _constraint_exists(name, constraint)]
    existing_columns = set() if offline else {column["name"] for column in sa.inspect(bind).get_columns("personas")}
    for table_name, column in columns:
        if column.name not in existing_columns:
            op.add_column(table_name, column)
    for table_name, constraint in missing_constraints:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch:
                if isinstance(constraint, sa.UniqueConstraint):
                    batch.create_unique_constraint(constraint.name, list(constraint.columns.keys()))
                elif isinstance(constraint, sa.ForeignKeyConstraint):
                    batch.create_foreign_key(
                        constraint.name, constraint.referred_table.name, list(constraint.columns.keys()),
                        [element.column.name for element in constraint.elements], ondelete=constraint.ondelete,
                    )
                else:
                    batch.create_check_constraint(constraint.name, str(constraint.sqltext))
        else:
            if isinstance(constraint, (sa.ForeignKeyConstraint, sa.CheckConstraint)):
                constraint.dialect_options["postgresql"]["not_valid"] = True
            op.invoke(AddConstraintOp.from_constraint(constraint))
    if bind.dialect.name == "postgresql":
        for table_name, constraint in constraints:
            if isinstance(constraint, (sa.ForeignKeyConstraint, sa.CheckConstraint)):
                op.execute(f"ALTER TABLE {table_name} VALIDATE CONSTRAINT {constraint.name}")
    if not table_exists:
        op.invoke(CreateTableOp.from_table(table))
    for index in (*_added_indexes(), *sorted(table.indexes, key=lambda item: item.name)):
        _ensure_index(index)


def downgrade() -> None:
    raise RuntimeError("Automatic downgrade would discard source selections and typed lineage; use a reviewed restore plan")
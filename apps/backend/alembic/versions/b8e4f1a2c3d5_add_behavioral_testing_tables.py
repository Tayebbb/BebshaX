"""add behavioral testing tables: behavioral_tests, scenarios, runs, results, insights

Revision ID: b8e4f1a2c3d5
Revises: af1e2d3c4b5a
Create Date: 2026-08-26 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8e4f1a2c3d5'
down_revision: Union[str, Sequence[str], None] = 'af1e2d3c4b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create behavioral_tests table
    op.create_table(
        'behavioral_tests',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('test_type', sa.String(length=64), nullable=False, server_default='pricing_test'),
        sa.Column('configuration', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='ready'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_tests_study_id', 'behavioral_tests', ['study_id'], unique=False)
    op.create_index('ix_behavioral_tests_user_id', 'behavioral_tests', ['user_id'], unique=False)
    op.create_index('ix_behavioral_tests_test_type', 'behavioral_tests', ['test_type'], unique=False)

    # 2. Create behavioral_test_scenarios table
    op.create_table(
        'behavioral_test_scenarios',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('behavioral_test_id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('scenario_text', sa.Text(), nullable=False),
        sa.Column('structured_parameters', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['behavioral_test_id'], ['behavioral_tests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_test_scenarios_behavioral_test_id', 'behavioral_test_scenarios', ['behavioral_test_id'], unique=False)

    # 3. Create behavioral_test_runs table
    op.create_table(
        'behavioral_test_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('behavioral_test_id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('scenario_id', sa.String(length=64), nullable=True),
        sa.Column('scenario_snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('target_population_type', sa.String(length=64), nullable=False, server_default='all'),
        sa.Column('target_segment_id', sa.String(length=64), nullable=True),
        sa.Column('target_persona_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='pending'),
        sa.Column('persona_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('aggregate_metrics', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('segment_analysis', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('cross_persona_patterns', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('risks', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('opportunities', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['behavioral_test_id'], ['behavioral_tests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_test_runs_behavioral_test_id', 'behavioral_test_runs', ['behavioral_test_id'], unique=False)
    op.create_index('ix_behavioral_test_runs_study_id', 'behavioral_test_runs', ['study_id'], unique=False)
    op.create_index('ix_behavioral_test_runs_user_id', 'behavioral_test_runs', ['user_id'], unique=False)

    # 4. Create behavioral_test_results table
    op.create_table(
        'behavioral_test_results',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('test_run_id', sa.String(length=64), nullable=False),
        sa.Column('behavioral_test_id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('persona_id', sa.String(length=64), nullable=False),
        sa.Column('persona_name', sa.String(length=256), nullable=False),
        sa.Column('persona_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('segment_id', sa.String(length=64), nullable=True),
        sa.Column('segment_name', sa.String(length=256), nullable=True),
        sa.Column('decision', sa.String(length=64), nullable=False),
        sa.Column('decision_label', sa.String(length=128), nullable=False),
        sa.Column('probability', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('confidence', sa.String(length=32), nullable=False, server_default='medium'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.8'),
        sa.Column('key_factors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('motivators', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('objections', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('reasoning_summary', sa.Text(), nullable=False),
        sa.Column('simulation_context_sources', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'),
        sa.Column('interview_signals_used', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='completed'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provenance_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['test_run_id'], ['behavioral_test_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_test_results_test_run_id', 'behavioral_test_results', ['test_run_id'], unique=False)
    op.create_index('ix_behavioral_test_results_behavioral_test_id', 'behavioral_test_results', ['behavioral_test_id'], unique=False)
    op.create_index('ix_behavioral_test_results_study_id', 'behavioral_test_results', ['study_id'], unique=False)
    op.create_index('ix_behavioral_test_results_persona_id', 'behavioral_test_results', ['persona_id'], unique=False)

    # 5. Create behavioral_insights table
    op.create_table(
        'behavioral_insights',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('test_run_id', sa.String(length=64), nullable=False),
        sa.Column('behavioral_test_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('supporting_persona_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['test_run_id'], ['behavioral_test_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_behavioral_insights_study_id', 'behavioral_insights', ['study_id'], unique=False)
    op.create_index('ix_behavioral_insights_test_run_id', 'behavioral_insights', ['test_run_id'], unique=False)
    op.create_index('ix_behavioral_insights_behavioral_test_id', 'behavioral_insights', ['behavioral_test_id'], unique=False)
    op.create_index('ix_behavioral_insights_user_id', 'behavioral_insights', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('behavioral_insights')
    op.drop_table('behavioral_test_results')
    op.drop_table('behavioral_test_runs')
    op.drop_table('behavioral_test_scenarios')
    op.drop_table('behavioral_tests')

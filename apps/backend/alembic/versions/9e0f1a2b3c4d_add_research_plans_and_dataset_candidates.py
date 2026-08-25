"""add research_plans and dataset_candidates tables and update research_runs

Revision ID: 9e0f1a2b3c4d
Revises: 8d9e0f1a2b3c
Create Date: 2026-08-26 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9e0f1a2b3c4d'
down_revision: Union[str, Sequence[str], None] = '8d9e0f1a2b3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create research_plans table
    op.create_table(
        'research_plans',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('run_id', sa.String(length=64), nullable=True),
        sa.Column('business_idea', sa.Text(), nullable=False),
        sa.Column('target_market', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('problem_areas', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('behavioral_questions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('economic_questions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('competition_questions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('market_questions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('dataset_requirements', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_research_plans')),
    )
    op.create_index(op.f('ix_research_plans_study_id'), 'research_plans', ['study_id'], unique=False)
    op.create_index(op.f('ix_research_plans_user_id'), 'research_plans', ['user_id'], unique=False)
    op.create_index(op.f('ix_research_plans_run_id'), 'research_plans', ['run_id'], unique=False)

    # 2. Create dataset_candidates table
    op.create_table(
        'dataset_candidates',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('run_id', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=128), nullable=False),
        sa.Column('external_id', sa.String(length=256), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('download_url', sa.Text(), nullable=True),
        sa.Column('publisher', sa.String(length=256), nullable=True),
        sa.Column('license', sa.String(length=128), nullable=True),
        sa.Column('license_url', sa.Text(), nullable=True),
        sa.Column('format', sa.String(length=64), nullable=False, server_default='csv'),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('sample_rows', sa.Integer(), nullable=True),
        sa.Column('sample_columns', sa.Integer(), nullable=True),
        sa.Column('geographic_coverage', sa.String(length=128), nullable=True),
        sa.Column('population_coverage', sa.String(length=128), nullable=True),
        sa.Column('relevant_variables', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=False, server_default='0.75'),
        sa.Column('quality_score', sa.Float(), nullable=False, server_default='0.80'),
        sa.Column('selection_status', sa.String(length=64), nullable=False, server_default='discovered'),
        sa.Column('selection_reason', sa.Text(), nullable=True),
        sa.Column('evaluation_details', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('imported_dataset_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_candidates')),
    )
    op.create_index(op.f('ix_dataset_candidates_study_id'), 'dataset_candidates', ['study_id'], unique=False)
    op.create_index(op.f('ix_dataset_candidates_user_id'), 'dataset_candidates', ['user_id'], unique=False)
    op.create_index(op.f('ix_dataset_candidates_run_id'), 'dataset_candidates', ['run_id'], unique=False)
    op.create_index(op.f('ix_dataset_candidates_source'), 'dataset_candidates', ['source'], unique=False)
    op.create_index(op.f('ix_dataset_candidates_imported_dataset_id'), 'dataset_candidates', ['imported_dataset_id'], unique=False)

    # 3. Update research_runs table
    with op.batch_alter_table('research_runs') as batch_op:
        batch_op.add_column(sa.Column('dataset_candidate_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('dataset_imported_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('current_step', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('step_progress', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('research_plan', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('research_runs') as batch_op:
        batch_op.drop_column('research_plan')
        batch_op.drop_column('step_progress')
        batch_op.drop_column('current_step')
        batch_op.drop_column('dataset_imported_count')
        batch_op.drop_column('dataset_candidate_count')

    op.drop_index(op.f('ix_dataset_candidates_imported_dataset_id'), table_name='dataset_candidates')
    op.drop_index(op.f('ix_dataset_candidates_source'), table_name='dataset_candidates')
    op.drop_index(op.f('ix_dataset_candidates_run_id'), table_name='dataset_candidates')
    op.drop_index(op.f('ix_dataset_candidates_user_id'), table_name='dataset_candidates')
    op.drop_index(op.f('ix_dataset_candidates_study_id'), table_name='dataset_candidates')
    op.drop_table('dataset_candidates')

    op.drop_index(op.f('ix_research_plans_run_id'), table_name='research_plans')
    op.drop_index(op.f('ix_research_plans_user_id'), table_name='research_plans')
    op.drop_index(op.f('ix_research_plans_study_id'), table_name='research_plans')
    op.drop_table('research_plans')

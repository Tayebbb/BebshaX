"""add segmentation_runs and market_segments tables

Revision ID: 7c8d9e0f1a2b
Revises: 614fe05a6f4d
Create Date: 2026-08-26 01:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7c8d9e0f1a2b'
down_revision: Union[str, Sequence[str], None] = '614fe05a6f4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. segmentation_runs table
    op.create_table(
        'segmentation_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='pending'),
        sa.Column('method', sa.String(length=64), nullable=False, server_default='hybrid_quantile_clustering'),
        sa.Column('configuration', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('dataset_versions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('evidence_snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('segment_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_segmentation_runs')),
    )
    op.create_index(op.f('ix_segmentation_runs_study_id'), 'segmentation_runs', ['study_id'], unique=False)
    op.create_index(op.f('ix_segmentation_runs_user_id'), 'segmentation_runs', ['user_id'], unique=False)

    # 2. market_segments table
    op.create_table(
        'market_segments',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('segmentation_run_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('cluster_label', sa.String(length=64), nullable=False, server_default='cluster_0'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('population_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('population_percentage', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='data_backed'),
        sa.Column('characteristics', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('variable_distributions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('evidence_citations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('differentiation_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_market_segments')),
    )
    op.create_index(op.f('ix_market_segments_study_id'), 'market_segments', ['study_id'], unique=False)
    op.create_index(op.f('ix_market_segments_user_id'), 'market_segments', ['user_id'], unique=False)
    op.create_index(op.f('ix_market_segments_segmentation_run_id'), 'market_segments', ['segmentation_run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_market_segments_segmentation_run_id'), table_name='market_segments')
    op.drop_index(op.f('ix_market_segments_user_id'), table_name='market_segments')
    op.drop_index(op.f('ix_market_segments_study_id'), table_name='market_segments')
    op.drop_table('market_segments')

    op.drop_index(op.f('ix_segmentation_runs_user_id'), table_name='segmentation_runs')
    op.drop_index(op.f('ix_segmentation_runs_study_id'), table_name='segmentation_runs')
    op.drop_table('segmentation_runs')

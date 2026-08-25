"""add persona_generation_runs and update personas table

Revision ID: 8d9e0f1a2b3c
Revises: 7c8d9e0f1a2b
Create Date: 2026-08-26 01:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8d9e0f1a2b3c'
down_revision: Union[str, Sequence[str], None] = '7c8d9e0f1a2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. persona_generation_runs table
    op.create_table(
        'persona_generation_runs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('segmentation_run_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=64), nullable=False, server_default='pending'),
        sa.Column('configuration', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('target_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('generated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valid_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('dataset_versions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('evidence_snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_persona_generation_runs')),
    )
    op.create_index(op.f('ix_persona_generation_runs_study_id'), 'persona_generation_runs', ['study_id'], unique=False)
    op.create_index(op.f('ix_persona_generation_runs_user_id'), 'persona_generation_runs', ['user_id'], unique=False)
    op.create_index(op.f('ix_persona_generation_runs_segmentation_run_id'), 'persona_generation_runs', ['segmentation_run_id'], unique=False)

    # 2. Add columns to personas table
    op.alter_column('personas', 'business_id', existing_type=sa.String(length=64), nullable=True)
    op.add_column('personas', sa.Column('study_id', sa.String(length=64), nullable=True))
    op.add_column('personas', sa.Column('user_id', sa.String(length=64), nullable=True))
    op.add_column('personas', sa.Column('segment_id', sa.String(length=64), nullable=True))
    op.add_column('personas', sa.Column('generation_run_id', sa.String(length=64), nullable=True))
    op.add_column('personas', sa.Column('archetype', sa.String(length=256), nullable=True))
    op.add_column('personas', sa.Column('demographics', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('bio', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('quote', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('goals', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('needs', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('pain_points', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('behaviors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('preferences', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('motivations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('objections', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('commercial_profile', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('technology_profile', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('evidence_citations', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('dataset_refs', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('grounding_score', sa.Float(), nullable=True, server_default='0.88'))
    op.add_column('personas', sa.Column('confidence', sa.Float(), nullable=True, server_default='0.85'))
    op.add_column('personas', sa.Column('validation_warnings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True))
    op.add_column('personas', sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default='true'))

    op.create_index(op.f('ix_personas_study_id'), 'personas', ['study_id'], unique=False)
    op.create_index(op.f('ix_personas_user_id'), 'personas', ['user_id'], unique=False)
    op.create_index(op.f('ix_personas_segment_id'), 'personas', ['segment_id'], unique=False)
    op.create_index(op.f('ix_personas_generation_run_id'), 'personas', ['generation_run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_personas_generation_run_id'), table_name='personas')
    op.drop_index(op.f('ix_personas_segment_id'), table_name='personas')
    op.drop_index(op.f('ix_personas_user_id'), table_name='personas')
    op.drop_index(op.f('ix_personas_study_id'), table_name='personas')

    op.drop_column('personas', 'is_synthetic')
    op.drop_column('personas', 'validation_warnings')
    op.drop_column('personas', 'confidence')
    op.drop_column('personas', 'grounding_score')
    op.drop_column('personas', 'dataset_refs')
    op.drop_column('personas', 'evidence_citations')
    op.drop_column('personas', 'technology_profile')
    op.drop_column('personas', 'commercial_profile')
    op.drop_column('personas', 'objections')
    op.drop_column('personas', 'motivations')
    op.drop_column('personas', 'preferences')
    op.drop_column('personas', 'behaviors')
    op.drop_column('personas', 'pain_points')
    op.drop_column('personas', 'needs')
    op.drop_column('personas', 'goals')
    op.drop_column('personas', 'quote')
    op.drop_column('personas', 'bio')
    op.drop_column('personas', 'demographics')
    op.drop_column('personas', 'archetype')
    op.drop_column('personas', 'generation_run_id')
    op.drop_column('personas', 'segment_id')
    op.drop_column('personas', 'user_id')
    op.drop_column('personas', 'study_id')

    op.drop_index(op.f('ix_persona_generation_runs_segmentation_run_id'), table_name='persona_generation_runs')
    op.drop_index(op.f('ix_persona_generation_runs_user_id'), table_name='persona_generation_runs')
    op.drop_index(op.f('ix_persona_generation_runs_study_id'), table_name='persona_generation_runs')
    op.drop_table('persona_generation_runs')

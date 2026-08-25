"""add interview_insights table and update conversations with study-level fields

Revision ID: af1e2d3c4b5a
Revises: 9e0f1a2b3c4d
Create Date: 2026-08-26 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'af1e2d3c4b5a'
down_revision: Union[str, Sequence[str], None] = '9e0f1a2b3c4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Update conversations table with study, versioning, objectives, topics and structured findings
    with op.batch_alter_table('conversations') as batch_op:
        batch_op.add_column(sa.Column('study_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('user_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('persona_version', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('generation_run_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('custom_objective', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('interview_type', sa.String(length=64), nullable=False, server_default='adaptive_persona'))
        batch_op.add_column(sa.Column('length_tier', sa.String(length=32), nullable=False, server_default='standard'))
        batch_op.add_column(sa.Column('max_turns', sa.Integer(), nullable=False, server_default='14'))
        batch_op.add_column(sa.Column('topics_explored', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('question_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('turn_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('key_findings', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('structured_insights', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('configuration', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(op.f('ix_conversations_study_id'), ['study_id'], unique=False)
        batch_op.create_index(op.f('ix_conversations_user_id'), ['user_id'], unique=False)
        batch_op.create_index(op.f('ix_conversations_generation_run_id'), ['generation_run_id'], unique=False)

    # 2. Update conversation_turns table
    with op.batch_alter_table('conversation_turns') as batch_op:
        batch_op.add_column(sa.Column('topic', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('latency_ms', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('served_by', sa.String(length=256), nullable=True))
        batch_op.add_column(sa.Column('retrieved_memories', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'))
        batch_op.add_column(sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'))

    # 3. Create interview_insights table
    op.create_table(
        'interview_insights',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('interview_id', sa.String(length=64), nullable=False),
        sa.Column('study_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=True),
        sa.Column('persona_id', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('supporting_turn_numbers', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='[]'),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['interview_id'], ['conversations.id'], name=op.f('fk_interview_insights_interview_id_conversations')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_interview_insights')),
    )
    op.create_index(op.f('ix_interview_insights_interview_id'), 'interview_insights', ['interview_id'], unique=False)
    op.create_index(op.f('ix_interview_insights_study_id'), 'interview_insights', ['study_id'], unique=False)
    op.create_index(op.f('ix_interview_insights_user_id'), 'interview_insights', ['user_id'], unique=False)
    op.create_index(op.f('ix_interview_insights_persona_id'), 'interview_insights', ['persona_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_interview_insights_persona_id'), table_name='interview_insights')
    op.drop_index(op.f('ix_interview_insights_user_id'), table_name='interview_insights')
    op.drop_index(op.f('ix_interview_insights_study_id'), table_name='interview_insights')
    op.drop_index(op.f('ix_interview_insights_interview_id'), table_name='interview_insights')
    op.drop_table('interview_insights')

    with op.batch_alter_table('conversation_turns') as batch_op:
        batch_op.drop_column('metadata_json')
        batch_op.drop_column('retrieved_memories')
        batch_op.drop_column('served_by')
        batch_op.drop_column('latency_ms')
        batch_op.drop_column('topic')

    with op.batch_alter_table('conversations') as batch_op:
        batch_op.drop_index(op.f('ix_conversations_generation_run_id'))
        batch_op.drop_index(op.f('ix_conversations_user_id'))
        batch_op.drop_index(op.f('ix_conversations_study_id'))
        batch_op.drop_column('completed_at')
        batch_op.drop_column('started_at')
        batch_op.drop_column('configuration')
        batch_op.drop_column('structured_insights')
        batch_op.drop_column('key_findings')
        batch_op.drop_column('summary')
        batch_op.drop_column('turn_count')
        batch_op.drop_column('question_count')
        batch_op.drop_column('topics_explored')
        batch_op.drop_column('max_turns')
        batch_op.drop_column('length_tier')
        batch_op.drop_column('interview_type')
        batch_op.drop_column('custom_objective')
        batch_op.drop_column('generation_run_id')
        batch_op.drop_column('persona_version')
        batch_op.drop_column('user_id')
        batch_op.drop_column('study_id')

"""add share and share open

Revision ID: f3a90c1d5b72
Revises: c41d7b60ae92
Create Date: 2026-09-01 11:20:44.512038

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'f3a90c1d5b72'
down_revision = 'c41d7b60ae92'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'share',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('author_id', sa.Uuid(), nullable=False),
        sa.Column('connector_id', sa.Uuid(), nullable=False),
        sa.Column('node_id', sa.String(length=1024), nullable=False),
        sa.Column('connector_label', sa.String(length=255), nullable=False),
        sa.Column('node_label', sa.String(length=255), nullable=False),
        sa.Column('view', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # The same view shared twice is the same address. Held here rather than
        # only by the lookup before the insert, because two windows of one
        # person can press the button at the same moment.
        sa.UniqueConstraint('author_id', 'fingerprint', name='uq_share_author_view'),
    )
    op.create_index('ix_share_token', 'share', ['token'], unique=True)
    op.create_index('ix_share_author_id', 'share', ['author_id'], unique=False)
    # The dialog lists every link to one connection, and the landing route
    # looks one up by token; both are the whole read pattern of this table.
    op.create_index('ix_share_connector_id', 'share', ['connector_id'], unique=False)

    op.create_table(
        'shareopen',
        sa.Column('share_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('opens', sa.Integer(), nullable=False),
        sa.Column('first_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['share_id'], ['share.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('share_id', 'user_id'),
    )


def downgrade():
    op.drop_table('shareopen')
    op.drop_index('ix_share_connector_id', table_name='share')
    op.drop_index('ix_share_author_id', table_name='share')
    op.drop_index('ix_share_token', table_name='share')
    op.drop_table('share')

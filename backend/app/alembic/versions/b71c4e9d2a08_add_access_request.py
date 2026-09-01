"""add access request

Revision ID: b71c4e9d2a08
Revises: f3a90c1d5b72
Create Date: 2026-09-01 13:05:19.774210

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b71c4e9d2a08'
down_revision = 'f3a90c1d5b72'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'accessrequest',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('connector_id', sa.Uuid(), nullable=False),
        sa.Column('requester_id', sa.Uuid(), nullable=False),
        # The link the person came through is context, not the subject: the ask
        # is about the connection, so it outlives the address that led to it.
        sa.Column('share_id', sa.Uuid(), nullable=True),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['connector_id'], ['connector.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requester_id'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['share_id'], ['share.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_accessrequest_connector_id', 'accessrequest', ['connector_id'], unique=False
    )
    op.create_index(
        'ix_accessrequest_requester_id', 'accessrequest', ['requester_id'], unique=False
    )
    # One open ask per person and connection, held by the database and not only
    # by the lookup before the insert. Partial, because the rule is about what
    # is waiting: somebody refused today may ask again next month.
    op.create_index(
        'uq_accessrequest_pending',
        'accessrequest',
        ['connector_id', 'requester_id'],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade():
    op.drop_index('uq_accessrequest_pending', table_name='accessrequest')
    op.drop_index('ix_accessrequest_requester_id', table_name='accessrequest')
    op.drop_index('ix_accessrequest_connector_id', table_name='accessrequest')
    op.drop_table('accessrequest')

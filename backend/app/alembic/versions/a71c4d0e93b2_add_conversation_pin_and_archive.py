"""add conversation pin and archive

A conversation is kept above the rest of the history, or out of it without
being lost (D141).

Revision ID: a71c4d0e93b2
Revises: d8f3a61c2b75
Create Date: 2026-09-18 10:12:41.118204

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c4d0e93b2'
down_revision = 'd8f3a61c2b75'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'conversation',
        sa.Column('pinned', sa.Boolean(), server_default='false', nullable=False),
    )
    op.add_column(
        'conversation',
        sa.Column('archived', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade():
    op.drop_column('conversation', 'archived')
    op.drop_column('conversation', 'pinned')

"""add connector third-party transfer

Revision ID: c4f82b6e1d39
Revises: a7c3e9d1f264
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f82b6e1d39'
down_revision = 'a7c3e9d1f264'
branch_labels = None
depends_on = None


def upgrade():
    # Off for every connection that already exists: nobody has said its data
    # may leave, and a default of yes would say it for them (D135).
    op.add_column(
        'connector',
        sa.Column(
            'allow_third_party_transfer',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade():
    op.drop_column('connector', 'allow_third_party_transfer')

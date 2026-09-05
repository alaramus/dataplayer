"""add connector cache ttl

Revision ID: b3d75f21c8ea
Revises: e29b60d41c83
Create Date: 2026-09-05

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3d75f21c8ea'
down_revision = 'e29b60d41c83'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'connector', sa.Column('cache_ttl_seconds', sa.Integer(), nullable=True)
    )


def downgrade():
    op.drop_column('connector', 'cache_ttl_seconds')

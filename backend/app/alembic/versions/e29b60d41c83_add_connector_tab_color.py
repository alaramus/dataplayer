"""add connector tab color

Revision ID: e29b60d41c83
Revises: 3c9a51de70b4
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa


revision = 'e29b60d41c83'
down_revision = '3c9a51de70b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'connector', sa.Column('tab_color', sa.String(length=7), nullable=True)
    )


def downgrade():
    op.drop_column('connector', 'tab_color')

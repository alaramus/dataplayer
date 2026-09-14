"""add dashboard color

Revision ID: a7c3e9d1f264
Revises: e5a1c7d3b940
Create Date: 2026-09-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c3e9d1f264'
down_revision = 'e5a1c7d3b940'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'dashboard', sa.Column('color', sa.String(length=7), nullable=True)
    )


def downgrade():
    op.drop_column('dashboard', 'color')

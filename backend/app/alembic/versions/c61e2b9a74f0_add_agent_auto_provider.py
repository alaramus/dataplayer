"""Add provider-scoped automatic model selection (D157).

Revision ID: c61e2b9a74f0
Revises: a8c3f5e1d204
"""

from alembic import op
import sqlalchemy as sa


revision = "c61e2b9a74f0"
down_revision = "a8c3f5e1d204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agentpreferences", sa.Column("auto_provider", sa.String(length=16), nullable=True))
    op.add_column("conversation", sa.Column("auto_provider", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("conversation", "auto_provider")
    op.drop_column("agentpreferences", "auto_provider")

"""a person's cloud accounts (D451)

Revision ID: e4b7c2a9f1d3
Revises: d7e2f9a4c1b8
Create Date: 2026-11-27 12:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e4b7c2a9f1d3"
down_revision = "d7e2f9a4c1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloudaccount",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("secrets", sa.LargeBinary(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_cloudaccount_owner_name"),
    )
    op.create_index("ix_cloudaccount_owner", "cloudaccount", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_cloudaccount_owner", table_name="cloudaccount")
    op.drop_table("cloudaccount")

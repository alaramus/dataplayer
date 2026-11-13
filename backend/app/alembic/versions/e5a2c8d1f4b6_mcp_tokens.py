"""personal access tokens for /mcp (D358)

Revision ID: e5a2c8d1f4b6
Revises: d4f1a7c9e2b3
Create Date: 2026-11-13 12:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5a2c8d1f4b6"
down_revision = "d4f1a7c9e2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("policy", sa.String(length=16), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("shown", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("digest"),
    )
    op.create_index("ix_mcp_token_owner", "mcp_token", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_token_owner", table_name="mcp_token")
    op.drop_table("mcp_token")

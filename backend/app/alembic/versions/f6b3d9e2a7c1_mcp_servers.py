"""outside MCP servers the agent calls (D360, D361)

Revision ID: f6b3d9e2a7c1
Revises: e5a2c8d1f4b6
Create Date: 2026-11-13 18:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f6b3d9e2a7c1"
down_revision = "e5a2c8d1f4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_server",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.LargeBinary(), nullable=True),
        sa.Column("header_names", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("has_token", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tools_off", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_mcp_server_owner_name"),
    )
    op.create_index("ix_mcp_server_owner", "mcp_server", ["owner_id"])
    op.add_column(
        "conversation",
        sa.Column("mcp_servers_off", sa.JSON(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("conversation", "mcp_servers_off")
    op.drop_index("ix_mcp_server_owner", table_name="mcp_server")
    op.drop_table("mcp_server")

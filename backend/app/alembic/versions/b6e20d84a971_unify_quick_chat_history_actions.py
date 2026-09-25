"""Give quick chats the same history actions as agent chats (D159).

Revision ID: b6e20d84a971
Revises: f4c9a1260d8b
"""

from alembic import op
import sqlalchemy as sa


revision = "b6e20d84a971"
down_revision = "f4c9a1260d8b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quickconversation",
        sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "quickconversation",
        sa.Column("archived", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "quickconversation",
        sa.Column(
            "project_id", sa.Uuid(),
            sa.ForeignKey("chatproject.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index(
        "ix_quickconversation_project_id", "quickconversation", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_quickconversation_project_id", table_name="quickconversation")
    op.drop_column("quickconversation", "project_id")
    op.drop_column("quickconversation", "archived")
    op.drop_column("quickconversation", "pinned")

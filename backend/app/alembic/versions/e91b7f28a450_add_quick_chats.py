"""Separate plain-chat transcript from agent conversations (D158).

Revision ID: e91b7f28a450
Revises: d3f4a9c17b62
"""

from alembic import op
import sqlalchemy as sa


revision = "e91b7f28a450"
down_revision = "d3f4a9c17b62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quickconversation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.LargeBinary(), nullable=False),
        sa.Column("model_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_quickconversation_owner_updated", "quickconversation", ["owner_id", "updated_at"]
    )
    op.create_table(
        "quickmessage",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id", sa.Uuid(),
            sa.ForeignKey("quickconversation.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_quickmessage_chat_created", "quickmessage", ["conversation_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_quickmessage_chat_created", table_name="quickmessage")
    op.drop_table("quickmessage")
    op.drop_index("ix_quickconversation_owner_updated", table_name="quickconversation")
    op.drop_table("quickconversation")

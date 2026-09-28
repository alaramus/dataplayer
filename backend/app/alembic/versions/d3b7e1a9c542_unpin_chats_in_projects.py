"""Unpin chats that are in a project

Pinned chats became a folder of their own, never inside a project. A chat
pinned inside one keeps its project and loses its pin.

Revision ID: d3b7e1a9c542
Revises: c8f4a2d6e913
"""

from alembic import op


revision = "d3b7e1a9c542"
down_revision = "c8f4a2d6e913"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE conversation SET pinned = false WHERE pinned AND project_id IS NOT NULL")
    op.execute("UPDATE quickconversation SET pinned = false WHERE pinned AND project_id IS NOT NULL")


def downgrade():
    # Which of them had been pinned is not kept.
    pass

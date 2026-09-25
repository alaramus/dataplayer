"""Remove query Trash and the per-user write unlock (D160).

Revision ID: f4c9a1260d8b
Revises: e91b7f28a450
"""

from alembic import op
import sqlalchemy as sa


revision = "f4c9a1260d8b"
down_revision = "e91b7f28a450"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These documents were already deleted by their owners. Run history has
    # ON DELETE SET NULL and survives without linking back to the document.
    op.execute("DELETE FROM querydocument WHERE trashed_at IS NOT NULL")
    op.drop_index("ix_querydocument_trashed_at", table_name="querydocument")
    op.drop_column("querydocument", "trashed_at")
    op.drop_table("writeunlock")


def downgrade() -> None:
    op.add_column(
        "querydocument",
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_querydocument_trashed_at", "querydocument", ["trashed_at"]
    )
    op.create_table(
        "writeunlock",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_id"], ["connector.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "connector_id"),
    )

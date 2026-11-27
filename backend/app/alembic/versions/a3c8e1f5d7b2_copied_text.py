"""a person's copy history (D460)

Revision ID: a3c8e1f5d7b2
Revises: f2a9d4c7e1b3
Create Date: 2026-11-27 20:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3c8e1f5d7b2"
down_revision = "f2a9d4c7e1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copied_text",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(length=200), nullable=True),
        sa.Column("cut", sa.Boolean(), nullable=False),
        sa.Column("copied_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_copied_text_owner_copied", "copied_text", ["owner_id", "copied_at"])


def downgrade() -> None:
    op.drop_index("ix_copied_text_owner_copied", table_name="copied_text")
    op.drop_table("copied_text")

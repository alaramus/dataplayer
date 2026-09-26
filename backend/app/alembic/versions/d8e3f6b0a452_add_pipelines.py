"""Keep a person's pipelines (D175).

One row per pipeline: a name, its cards as one JSON body read and written
whole, and a version raised by every save, as a dashboard keeps its layout.

Revision ID: d8e3f6b0a452
Revises: c7d2e5a9f341
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "d8e3f6b0a452"
down_revision = "c7d2e5a9f341"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pipeline_owner_id"), "pipeline", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pipeline_owner_id"), table_name="pipeline")
    op.drop_table("pipeline")

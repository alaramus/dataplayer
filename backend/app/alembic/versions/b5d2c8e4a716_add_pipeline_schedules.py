"""Keep a schedule for each pipeline (D179).

Beside the pipeline's body rather than in it: when a pipeline runs is not
what it runs, and a change of it is not checked against the canvas's version.

Revision ID: b5d2c8e4a716
Revises: a3c7e5d91f04
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "b5d2c8e4a716"
down_revision = "a3c7e5d91f04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipelineschedule",
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("counted_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("note_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipeline.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pipeline_id"),
    )
    op.create_index(
        op.f("ix_pipelineschedule_next_at"), "pipelineschedule", ["next_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pipelineschedule_next_at"), table_name="pipelineschedule")
    op.drop_table("pipelineschedule")

"""Keep the last run of each link of a pipeline (D176).

A row of its own beside the pipeline's body: a run changes nothing the person
drew, and must not raise the version their next save is checked against.

Revision ID: e9f4a7c1b563
Revises: d8e3f6b0a452
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "e9f4a7c1b563"
down_revision = "d8e3f6b0a452"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipelinerun",
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("link_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipeline.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("pipeline_id", "link_id"),
    )


def downgrade() -> None:
    op.drop_table("pipelinerun")

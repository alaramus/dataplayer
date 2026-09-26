"""Drop the last run of each link of a pipeline (D177).

A pipeline runs whole now, as one job, and that job keeps what every link
did: the last run is the pipeline's newest run job, and nothing beside it.

Revision ID: a3c7e5d91f04
Revises: e9f4a7c1b563
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "a3c7e5d91f04"
down_revision = "e9f4a7c1b563"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("pipelinerun")


def downgrade() -> None:
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

"""Keep every skip and miss of a schedule as a row of the history (D180).

A schedule kept only its latest one (D179); that one is carried over, its
kind read off the sentence it was written as.

Revision ID: c8f4a2d6e913
Revises: b5d2c8e4a716
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "c8f4a2d6e913"
down_revision = "b5d2c8e4a716"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schedulenote",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_id"], ["pipeline.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedulenote_pipeline_at", "schedulenote", ["pipeline_id", "at"], unique=False
    )
    # "Skipped at 03:00: the previous run was still going" → skipped, and
    # what follows the first ": ".
    op.execute(
        """
        INSERT INTO schedulenote (id, pipeline_id, kind, at, reason)
        SELECT gen_random_uuid(),
               pipeline_id,
               CASE WHEN left(note, 6) = 'Missed' THEN 'missed' ELSE 'skipped' END,
               note_at,
               CASE WHEN strpos(note, ': ') > 0
                    THEN substr(note, strpos(note, ': ') + 2)
                    ELSE note END
        FROM pipelineschedule
        WHERE note IS NOT NULL AND note_at IS NOT NULL
        """
    )
    op.drop_column("pipelineschedule", "note_at")
    op.drop_column("pipelineschedule", "note")


def downgrade() -> None:
    op.add_column(
        "pipelineschedule",
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    )
    op.add_column(
        "pipelineschedule", sa.Column("note_at", sa.DateTime(timezone=True), nullable=True)
    )
    # The latest note goes back, without the time of day it was written with.
    op.execute(
        """
        UPDATE pipelineschedule AS schedule
        SET note = left(
                CASE latest.kind WHEN 'missed' THEN 'Missed' ELSE 'Skipped' END
                || ': ' || latest.reason,
                512
            ),
            note_at = latest.at
        FROM (
            SELECT DISTINCT ON (pipeline_id) pipeline_id, kind, at, reason
            FROM schedulenote
            ORDER BY pipeline_id, at DESC
        ) AS latest
        WHERE schedule.pipeline_id = latest.pipeline_id
        """
    )
    op.drop_index("ix_schedulenote_pipeline_at", table_name="schedulenote")
    op.drop_table("schedulenote")

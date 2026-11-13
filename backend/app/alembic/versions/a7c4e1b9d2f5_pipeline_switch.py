"""a pipeline switched on with one button (D362)

Following becomes the pipeline's switch, the schedule loses its own `enabled`,
and a link's `follow` mark becomes `runs`. A pipeline kept before behaves as
it did: a link marked to follow runs continuously only where following was
on, and a schedule that was switched off is dropped from a pipeline that is
now on for its following, rather than starting to run.

Revision ID: a7c4e1b9d2f5
Revises: f6b3d9e2a7c1
Create Date: 2026-11-13 22:00:00

"""

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c4e1b9d2f5"
down_revision = "f6b3d9e2a7c1"
branch_labels = None
depends_on = None


def _loaded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def upgrade() -> None:
    op.rename_table("pipelinefollow", "pipelineswitch")
    op.execute("ALTER INDEX ix_pipelinefollow_on RENAME TO ix_pipelineswitch_on")
    bind = op.get_bind()
    following = {
        row.pipeline_id: row.on
        for row in bind.execute(sa.text("SELECT pipeline_id, \"on\" FROM pipelineswitch"))
    }
    schedules = {
        row.pipeline_id: _loaded(row.settings)
        for row in bind.execute(sa.text("SELECT pipeline_id, settings FROM pipelineschedule"))
    }
    now = datetime.now(UTC)
    for row in bind.execute(sa.text("SELECT id, content FROM pipeline")).all():
        follows = bool(following.get(row.id, False))
        content = _loaded(row.content)
        if isinstance(content, dict):
            for link in content.get("links", []):
                if isinstance(link, dict):
                    marked = bool(link.pop("follow", False))
                    link["runs"] = "continuous" if marked and follows else "scheduled"
            bind.execute(
                sa.text("UPDATE pipeline SET content = CAST(:content AS json) WHERE id = :id"),
                {"content": json.dumps(content), "id": row.id},
            )
        settings = schedules.get(row.id)
        scheduled = isinstance(settings, dict) and bool(settings.get("enabled", False))
        on = follows or scheduled
        if isinstance(settings, dict):
            if on and not scheduled:
                bind.execute(
                    sa.text("DELETE FROM pipelineschedule WHERE pipeline_id = :id"), {"id": row.id}
                )
            else:
                settings.pop("enabled", None)
                bind.execute(
                    sa.text(
                        "UPDATE pipelineschedule SET settings = CAST(:settings AS json)"
                        " WHERE pipeline_id = :id"
                    ),
                    {"settings": json.dumps(settings), "id": row.id},
                )
        if row.id in following:
            bind.execute(
                sa.text("UPDATE pipelineswitch SET \"on\" = :on WHERE pipeline_id = :id"),
                {"on": on, "id": row.id},
            )
        elif on:
            bind.execute(
                sa.text(
                    "INSERT INTO pipelineswitch (pipeline_id, \"on\", changed_at)"
                    " VALUES (:id, true, :at)"
                ),
                {"id": row.id, "at": now},
            )


def downgrade() -> None:
    bind = op.get_bind()
    switched = {
        row.pipeline_id: row.on
        for row in bind.execute(sa.text("SELECT pipeline_id, \"on\" FROM pipelineswitch"))
    }
    for row in bind.execute(sa.text("SELECT id, content FROM pipeline")).all():
        content = _loaded(row.content)
        if isinstance(content, dict):
            for link in content.get("links", []):
                if isinstance(link, dict):
                    link["follow"] = link.pop("runs", "scheduled") == "continuous"
            bind.execute(
                sa.text("UPDATE pipeline SET content = CAST(:content AS json) WHERE id = :id"),
                {"content": json.dumps(content), "id": row.id},
            )
    for row in bind.execute(sa.text("SELECT pipeline_id, settings FROM pipelineschedule")).all():
        settings = _loaded(row.settings)
        if isinstance(settings, dict):
            settings["enabled"] = bool(switched.get(row.pipeline_id, False))
            bind.execute(
                sa.text(
                    "UPDATE pipelineschedule SET settings = CAST(:settings AS json)"
                    " WHERE pipeline_id = :id"
                ),
                {"settings": json.dumps(settings), "id": row.pipeline_id},
            )
    op.execute("ALTER INDEX ix_pipelineswitch_on RENAME TO ix_pipelinefollow_on")
    op.rename_table("pipelineswitch", "pipelinefollow")

"""Pipelines, as the search finds them: by name, the owner's only (D175, D199).

Handed to the search at assembly: the engine sits below pipelines and imports
no feature (D197). A card's labels are names kept as they were and are not
searched.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlmodel import col, select

from app.pipelines.models import MAX_PIPELINES, Pipeline
from app.search.models import (
    Facts,
    Hit,
    Match,
    ObjectsPlace,
    ObjectTarget,
    ObjectType,
    target_key,
)
from app.search.providers import (
    Asked,
    Found,
    ProviderCell,
    name_match,
    ordered,
    recalled,
    uuids_of,
)


class PipelineNames:
    place = ObjectsPlace(provider="pipelines")
    title = "Pipelines"
    recalls: frozenset[ObjectType] = frozenset({"pipeline"})

    def cells(self) -> tuple[ProviderCell, ...]:
        return (ProviderCell(field="names", cost="instant"),)

    async def search(self, asked: Asked) -> Found:
        hits: list[Hit] = []
        for pipeline_id, name, changed_at in await _owned(asked):
            match = name_match(asked.words, name)
            if match is not None:
                hits.append(_hit(pipeline_id, name, changed_at, match))
        return ordered(hits, asked.limit)

    async def recall(
        self, asked: Asked, object_type: ObjectType, ids: Sequence[str]
    ) -> list[Hit]:
        return [
            _hit(pipeline_id, name, changed_at, recalled(name))
            for pipeline_id, name, changed_at in await _owned(asked, uuids_of(ids))
        ]


async def _owned(
    asked: Asked, ids: list[uuid.UUID] | None = None
) -> list[tuple[uuid.UUID, str, datetime]]:
    statement = select(Pipeline.id, Pipeline.name, Pipeline.updated_at).where(
        Pipeline.owner_id == asked.user.id
    )
    if ids is not None:
        statement = statement.where(col(Pipeline.id).in_(ids))
    # A person keeps no more than this; the query is bounded all the same.
    rows = await asked.session.exec(statement.limit(MAX_PIPELINES))
    return list(rows.all())


def _hit(pipeline_id: uuid.UUID, name: str, changed_at: datetime, match: Match) -> Hit:
    target = ObjectTarget(object_type="pipeline", object_id=str(pipeline_id))
    return Hit(
        key=target_key(target),
        target=target,
        title=name,
        detail="Pipeline",
        facts=Facts(kind="pipeline", changed_at=changed_at),
        match=match,
        open="pipeline",
    )

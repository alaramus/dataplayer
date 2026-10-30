"""Pasting into another connection: at once, or as a transfer job (D164, D168).

What a paste does is `run.py`'s; this is the door Paste and the pair window
knock at. The grid's two row commands live here too, beside it: past one
request's ceiling each becomes the same job a Paste of rows does (D43).
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.adapters.cache import DataCacheDep
from app.adapters.protocol import SupportsCreateRelation, SupportsFetch, SupportsInsert
from app.adapters.relation_changes import RelationCreated
from app.adapters.resources import ResourcesDep
from app.adapters.update import RowsInserted
from app.connectors import imports
from app.connectors.access import adapter_for
from app.connectors.names import NamesChangedDep
from app.connectors.paste.models import PasteColumn, PasteResult, PasteRun
from app.connectors.paste.rows import RowsNewRelation
from app.connectors.routes import import_sides, shape_change
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.translation import say
from app.jobs.runner import JobRunnerDep
from app.realtime.topics import TopicsDep
from app.transfers.run import Carrying, PasteAnswer, PasteStarted, run_paste
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.post("/{connector_id}/paste", response_model=PasteAnswer)
async def paste(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    request: PasteRun,
) -> PasteResult | PasteStarted:
    carrying = Carrying(session, current_user, resources, data_cache, runner, topics)
    return await run_paste(carrying, connector_id, request)


NEW_RELATION = RowsNewRelation()


@router.post("/{connector_id}/import", response_model=imports.RowsMoved | PasteStarted)
async def import_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    request: imports.ImportRowsRequest,
) -> Any:
    """
    Move a bounded set of rows from one source into a relation of another.

    Either every row arrives or none does. A value the target cannot read is
    named — row, column and the value itself — and nothing is written. A source
    holding more rows than one request carries is carried by a job instead, a
    block at a time, as Paste carries it (D43).
    """
    target, source = await import_sides(
        session, connector_id, request, current_user, resources
    )
    if not isinstance(target, SupportsInsert):
        raise Problem(501, "connectors.no_row_import", error_kind="config")
    if await shape_change(lambda: imports.exceeds_ceiling(source, request.source_node_id)):
        carrying = Carrying(session, current_user, resources, data_cache, runner, topics)
        return await run_paste(
            carrying,
            connector_id,
            PasteRun(
                kind="rows_into_relation",
                mode="copy",
                source_connector_id=uuid.UUID(request.source_connector_id),
                source_node_ids=[request.source_node_id],
                target_node_id=request.node_id,
                columns=[
                    PasteColumn(source=pair.source, target=pair.target)
                    for pair in request.columns
                ],
            ),
        )
    result, truncated = await shape_change(
        lambda: imports.insert_from_source(target, source, request)
    )
    if not isinstance(result, RowsInserted):
        # Named values that could not be read, with nothing written. A 422
        # rather than an answer, because unlike the counts of D37 this is a
        # request that cannot be carried out as given.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "rows", cell.row, cell.column],
                    "msg": say("{value} cannot be read by {column}", value=repr(cell.value), column=cell.column),
                    "type": "value_error",
                }
                for cell in result.cells
            ],
        )
    await data_cache.invalidate_connector(connector_id)
    return imports.RowsMoved(inserted=result.inserted, truncated=truncated)


@router.post(
    "/{connector_id}/relations/from-source", response_model=RelationCreated | PasteStarted
)
async def create_relation_from_source(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    names: NamesChangedDep,
    runner: JobRunnerDep,
    topics: TopicsDep,
    connector_id: uuid.UUID,
    request: imports.CreateRelationFromSourceRequest,
) -> Any:
    """Create and fill one relation from any readable source.

    Past one request's ceiling the relation is made and filled by a job, as
    Paste fills it (D43); a folder still takes at most that many as a file.
    """
    try:
        source_id = uuid.UUID(request.source_connector_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "source_connector_id"],
                    "msg": say("That is not a connector id"),
                    "type": "value_error",
                }
            ],
        ) from None
    target = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    source = await adapter_for(
        session, source_id, current_user, resources, requires="read"
    )
    if not isinstance(target, SupportsCreateRelation):
        raise Problem(501, "connectors.no_relation_create", error_kind="config")
    if not isinstance(source, SupportsFetch):
        raise Problem(501, "connectors.source_not_rows", error_kind="config")
    if await shape_change(
        lambda: imports.exceeds_ceiling(source, request.source_node_id)
    ) and NEW_RELATION.serves(source, target):
        carrying = Carrying(session, current_user, resources, data_cache, runner, topics)
        return await run_paste(
            carrying,
            connector_id,
            PasteRun(
                kind=NEW_RELATION.name,
                mode="copy",
                source_connector_id=source_id,
                source_node_ids=[request.source_node_id],
                destination_node_id=request.parent_node_id,
                name=request.name,
                columns=[
                    PasteColumn(
                        source=column.source, target=column.target, type_code=column.type_code
                    )
                    for column in request.columns
                ],
            ),
        )
    try:
        result = await shape_change(
            lambda: imports.create_from_source(target, source, request)
        )
    except imports.SourceTooLarge:
        raise Problem(
            413, "connectors.import_too_many_rows", limit=imports.IMPORT_CEILING
        ) from None
    if not isinstance(result, RelationCreated):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "rows", cell.row, cell.column],
                    "msg": say("{value} cannot be read by {column}", value=repr(cell.value), column=cell.column),
                    "type": "value_error",
                }
                for cell in result.cells
            ],
        )
    await data_cache.invalidate_connector(connector_id)
    await names(connector_id)
    return result

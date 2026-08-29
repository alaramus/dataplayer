import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

from anyio import to_thread
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.responses import FileResponse

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActionResult,
    ActsOn,
    RefusalReason,
    SupportsActions,
    TakesFile,
    TakesParams,
    UnknownAction,
    common_actions,
)
from app.adapters.cache import (
    CacheArea,
    CacheKey,
    DataCache,
    DataCacheDep,
    SupportsReadCache,
)
from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    DropColumnRequest,
    RenameColumnRequest,
)
from app.adapters.fetch import DownloadPageRequest, FetchRequest, FetchResult
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    DataAdapter,
    DescribesDraft,
    NodeNotFound,
    ParsesConnectionString,
    SupportsAddColumn,
    SupportsCatalog,
    SupportsColumnDefault,
    SupportsConnectionString,
    SupportsDelete,
    SupportsDropColumn,
    SupportsFetch,
    SupportsInsert,
    SupportsNodePath,
    SupportsRelationModel,
    SupportsRenameColumn,
    SupportsUpdate,
)
from app.adapters.registry import AdapterContext, AdapterType, UnknownAdapterType
from app.adapters.registry import get as get_adapter_type
from app.adapters.relation import RelationModel
from app.adapters.resources import Pooling, ResourcesDep, ResourceStore
from app.adapters.update import (
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    RowConflict,
    UpdateCellRequest,
    UpdateCellResult,
)
from app.connectors import crud, downloads, health, service
from app.connectors.models import (
    Connector,
    ConnectorCreate,
    ConnectorPublic,
    ConnectorsPublic,
    ConnectorUpdate,
)
from app.core.db import SessionDep
from app.core.schemas import Message, get_datetime_utc
from app.realtime.topics import TopicsDep
from app.users import storage
from app.users.deps import CurrentUser, get_current_user
from app.users.models import User

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _cache_key(
    current_user: User,
    connector_id: uuid.UUID,
    area: CacheArea,
    request: str,
) -> CacheKey:
    return CacheKey(current_user.id, connector_id, area, request)


async def _cached[T](
    *,
    data_cache: DataCache,
    adapter: DataAdapter,
    key: CacheKey,
    refresh: bool,
    response: Response,
    load: Callable[[], Awaitable[T]],
) -> T:
    if not isinstance(adapter, SupportsReadCache):
        response.headers["X-Data-Cache"] = "bypass"
        return await load()
    ttl_seconds = adapter.cache_ttl(key.area)
    if ttl_seconds <= 0:
        response.headers["X-Data-Cache"] = "bypass"
        return await load()
    cached = await data_cache.get_or_load(
        key,
        ttl_seconds=ttl_seconds,
        load=load,
        refresh=refresh,
    )
    response.headers["X-Data-Cache"] = cached.status
    return cached.value


async def _invalidate_after[T](
    run: Callable[[], Awaitable[T]], data_cache: DataCache, connector_id: uuid.UUID
) -> T:
    result = await run()
    await data_cache.invalidate_connector(connector_id)
    return result


def _resolve_type(adapter_type: str) -> AdapterType:
    try:
        return get_adapter_type(adapter_type)
    except UnknownAdapterType:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "adapter_type"],
                    "msg": f"Unknown adapter type: {adapter_type}",
                    "type": "value_error",
                }
            ],
        )


def _split_or_422(
    adapter_type: AdapterType, options: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    try:
        return service.split_options(adapter_type, options)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "options", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        )


async def _get_or_404(
    session: AsyncSession, connector_id: uuid.UUID, current_user: User
) -> Connector:
    connector = await crud.get(session, connector_id=connector_id, owner=current_user)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


def _context_for(
    owner_id: uuid.UUID,
    *,
    pooling: Pooling | None = None,
) -> AdapterContext:
    """What the driver may reach, decided here rather than by the request."""
    return AdapterContext(home_dir=storage.home_dir(owner_id), pooling=pooling)


async def _adapter_for(
    session: AsyncSession,
    connector_id: uuid.UUID,
    current_user: User,
    resources: ResourceStore | None = None,
) -> DataAdapter:
    """Resolve a stored connector into a live adapter.

    A stored connector has an identity, so whatever it keeps between requests
    can be found again. Without a store — a check, which is meant to exercise
    the credentials — the driver connects on its own.

    A disabled connector is refused here rather than in each route: this is the
    one door to a live source, so the rule is written once and cannot be
    forgotten by a route added later. Reading and editing the row go through
    ``_get_or_404`` and stay open — switching a connection off is not deleting
    it.
    """
    connector = await _get_or_404(session, connector_id, current_user)
    if not connector.enabled:
        # 409 rather than 404: the connector exists and the client knows it.
        # Nor 403: it is the caller's own, and rights are not what is missing.
        raise HTTPException(status_code=409, detail="Connector is disabled")
    adapter_type = _resolve_type(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    pooling = (
        Pooling(store=resources, connector_id=connector.id)
        if resources is not None
        else None
    )
    return service.build_adapter(
        adapter_type, options, _context_for(connector.owner_id, pooling=pooling)
    )


@router.post("/", response_model=ConnectorPublic)
async def create_connector(
    session: SessionDep, current_user: CurrentUser, connector_in: ConnectorCreate
) -> Any:
    """
    Create a new connector.
    """
    adapter_type = _resolve_type(connector_in.adapter_type)
    config, secrets = _split_or_422(adapter_type, connector_in.options)
    return await crud.create(
        session,
        name=connector_in.name,
        adapter_type=adapter_type.name,
        config=config,
        secrets=secrets,
        owner_id=current_user.id,
    )


@router.get("/", response_model=ConnectorsPublic)
async def read_connectors(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve connectors.
    """
    connectors, count = await crud.list_for(
        session, owner=current_user, skip=skip, limit=limit
    )
    return ConnectorsPublic(data=connectors, count=count)


@router.get("/{connector_id}", response_model=ConnectorPublic)
async def read_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """
    Get connector by ID.
    """
    return await _get_or_404(session, connector_id, current_user)


@router.patch("/{connector_id}", response_model=ConnectorPublic)
async def update_connector(
    session: SessionDep,
    current_user: CurrentUser,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    connector_in: ConnectorUpdate,
) -> Any:
    """
    Update a connector.
    """
    connector = await _get_or_404(session, connector_id, current_user)

    if connector_in.name is not None:
        connector.name = connector_in.name

    if connector_in.enabled is not None:
        connector.enabled = connector_in.enabled

    if connector_in.options is not None:
        adapter_type = _resolve_type(connector.adapter_type)
        options = service.fill_missing_secrets(
            adapter_type, connector_in.options, connector.secrets
        )
        connector.config, connector.secrets = _split_or_422(adapter_type, options)

    connector.updated_at = get_datetime_utc()
    saved = await crud.save(session, connector=connector)
    await data_cache.invalidate_connector(connector_id)
    return saved


@router.delete("/{connector_id}")
async def delete_connector(
    session: SessionDep,
    current_user: CurrentUser,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
) -> Message:
    """
    Delete a connector.
    """
    connector = await _get_or_404(session, connector_id, current_user)
    await crud.delete(session, connector=connector)
    await data_cache.invalidate_connector(connector_id)
    return Message(message="Connector deleted successfully")


class ConnectionCheckRequest(BaseModel):
    adapter_type: str
    options: dict[str, Any]
    connector_id: uuid.UUID | None = None


async def _draft_adapter(
    session: AsyncSession, current_user: User, body: ConnectionCheckRequest
) -> DataAdapter:
    """Build an adapter from form values, filling in secrets not retyped.

    Shared by the two routes that read a draft: checking it and describing it
    ask the same question of the same values, and a second copy of this would
    be a second place for the secret substitution to be forgotten.

    No pooling: a draft has no identity to key a pool by, and a check is meant
    to exercise the credentials rather than reuse a connection.
    """
    adapter_type = _resolve_type(body.adapter_type)
    options = body.options
    if body.connector_id is not None:
        connector = await _get_or_404(session, body.connector_id, current_user)
        options = service.fill_missing_secrets(adapter_type, options, connector.secrets)

    try:
        return service.build_adapter(
            adapter_type, options, _context_for(current_user.id)
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "options", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        )


@router.post("/check-draft", response_model=ConnectionCheckResult)
async def check_draft(
    session: SessionDep, current_user: CurrentUser, body: ConnectionCheckRequest
) -> Any:
    """
    Check a connection from form values, without storing anything.

    When connector_id is supplied, secret fields missing from the body are taken
    from the stored connector: the user edits the port without retyping the
    password.
    """
    adapter = await _draft_adapter(session, current_user, body)
    return await adapter.check_connection()


class ConnectionDescription(BaseModel):
    connection_string: str


@router.post("/describe-draft", response_model=ConnectionDescription)
async def describe_draft(
    session: SessionDep, current_user: CurrentUser, body: ConnectionCheckRequest
) -> Any:
    """
    Compose the connection string of a draft, without connecting to anything.

    Read by the form as it is filled in, so it opens nothing and costs the
    server only the string it builds. Composed here rather than on the client
    because the rule for building it belongs to the driver, and because this
    is already the layer obliged to keep the password out of what it answers.

    Answers for a form that does not validate yet as well. Defaults put a host
    and a port there before anything is typed, and that is already an address
    worth showing; the alternative was a client that composed one itself, and
    a second implementation of the driver's grammar drifts from it in the
    quoting first. What the source cannot say yet is an empty string — a
    source with no address at all is still the 501, which is a different
    answer and stays one.
    """
    driver = _resolve_type(body.adapter_type).adapter_class
    if not issubclass(driver, SupportsConnectionString):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source is not addressed by a connection string",
                "error_kind": "config",
            },
        )
    try:
        adapter = await _draft_adapter(session, current_user, body)
    except HTTPException as exc:
        # Not filled in yet is not the same as wrong: the driver is asked what
        # it can write from what there is, and answers None while that is
        # nothing at all.
        if exc.status_code != 422 or not issubclass(driver, DescribesDraft):
            raise
        drafted = driver.draft_connection_string(body.options)
        return ConnectionDescription(connection_string=drafted or "")
    # Cast rather than a second check: the class was asked above, and an
    # adapter built from it cannot have lost the capability on the way.
    return ConnectionDescription(
        connection_string=cast(SupportsConnectionString, adapter).connection_string()
    )


class ConnectionStringRequest(BaseModel):
    adapter_type: str
    url: str


class ParsedOptions(BaseModel):
    """Form values, in the shape the type's own schema declares."""

    options: dict[str, Any]


# Authentication is declared on the route rather than taken as an argument:
# nothing here reads the user — the question is about a type of source, not
# about anything of theirs — and an unused argument is a ruff error.
@router.post(
    "/parse-url",
    response_model=ParsedOptions,
    dependencies=[Depends(get_current_user)],
)
async def parse_url(body: ConnectionStringRequest) -> Any:
    """
    Take a pasted connection string apart into the fields of the form.

    Asked of the *type*: there are no options yet, and this is what produces
    them, so the question goes to the driver class exactly as `action_types`
    does. Nothing is opened, and nothing is stored.

    The driver names the way of connecting as well as the address — a form
    inferring it from the presence of a password would be a rule about
    authentication living in a component that knows nothing about it.

    The password in the answer discloses nothing: the client sent that very
    string a moment ago. It must not be written to a log, all the same.
    """
    adapter_type = _resolve_type(body.adapter_type)
    driver = adapter_type.adapter_class
    if not issubclass(driver, ParsesConnectionString):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source is not addressed by a connection string",
                "error_kind": "config",
            },
        )
    try:
        return ParsedOptions(options=driver.options_from_url(body.url))
    except ValueError as exc:
        # The driver's own message, which is written not to quote the string
        # back: a rejected one may still have carried a password.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "url"], "msg": str(exc), "type": "value_error"}],
        ) from None


@router.post("/{connector_id}/check", response_model=ConnectionCheckResult)
async def check_connector(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    topics: TopicsDep,
) -> Any:
    """
    Check the connection of a stored connector.
    """
    adapter = await _adapter_for(session, connector_id, current_user)
    result = await adapter.check_connection()
    # Told to whoever is watching, so that pressing the button and the dot on
    # the same connection cannot end up saying different things.
    await health.announce_check(topics, current_user.id, connector_id, result)
    return result


@router.post("/{connector_id}/fetch", response_model=FetchResult)
async def fetch_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    response: Response,
    connector_id: uuid.UUID,
    request: FetchRequest,
    refresh: bool = False,
) -> Any:
    """
    Read a page of rows from a relation named by request.node_id.
    """
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support reading rows",
                "error_kind": "config",
            },
        )
    try:
        return await _cached(
            data_cache=data_cache,
            adapter=adapter,
            key=_cache_key(
                current_user, connector_id, "fetch", request.model_dump_json()
            ),
            refresh=refresh,
            response=response,
            load=lambda: adapter.fetch(request),
        )
    except ValueError as exc:
        # A column the relation does not have. Caught before any SQL is built,
        # so this is a bad request rather than an upstream failure.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        )
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        )


@router.get("/{connector_id}/catalog", response_model=list[CatalogNode])
async def read_catalog(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    response: Response,
    connector_id: uuid.UUID,
    node_id: str | None = None,
    refresh: bool = False,
) -> Any:
    """
    List the children of a catalog node, or the root when node_id is omitted.

    node_id is opaque: only the adapter that produced it knows how to read it.
    """
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsCatalog):
        # Browsing is an optional capability: a queue or a plain HTTP source
        # has no catalog to walk.
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support browsing",
                "error_kind": "config",
            },
        )
    try:
        return await _cached(
            data_cache=data_cache,
            adapter=adapter,
            key=_cache_key(
                current_user, connector_id, "catalog", json.dumps(node_id)
            ),
            refresh=refresh,
            response=response,
            load=lambda: adapter.list_children(node_id),
        )
    except ValueError as exc:
        # 422: the node id names something this source may not or cannot
        # reach. That is the request being wrong, not the source failing.
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        # 502: the request was valid, the upstream source failed. An empty list
        # would hide the difference between an empty node and a broken query.
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        )


@router.post(
    "/{connector_id}/downloads/page",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}}
            },
            "description": "The visible table page as CSV",
        }
    },
)
async def download_page(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: DownloadPageRequest,
) -> FileResponse:
    """Re-read, save and return the same bounded page the grid describes."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support reading rows",
                "error_kind": "config",
            },
        )
    fetch_request = FetchRequest.model_validate(
        request.model_dump(exclude={"title", "columns"})
    )
    try:
        result = await adapter.fetch(fetch_request)
        path = await to_thread.run_sync(
            lambda: downloads.save_csv_page(
                home=storage.home_dir(current_user.id),
                connector_id=connector_id,
                title=request.title,
                columns=request.columns,
                result=result,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from None
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from None
    return FileResponse(path, media_type="text/csv", filename=path.name)


@router.patch("/{connector_id}/rows/cell", response_model=UpdateCellResult)
async def update_cell(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: UpdateCellRequest,
) -> Any:
    """Change one cell if the fetched row version is still current."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsUpdate):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support editing rows",
                "error_kind": "config",
            },
        )
    try:
        return await _invalidate_after(
            lambda: adapter.update_cell(request), data_cache, connector_id
        )
    except RowConflict:
        raise HTTPException(
            status_code=409,
            detail={"message": "The row changed or was deleted; reload it and try again"},
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.post("/{connector_id}/rows", response_model=InsertRowResult)
async def insert_row(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: InsertRowRequest,
) -> Any:
    """Insert one row, preserving defaults for columns the caller omitted."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsInsert):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support inserting rows",
                "error_kind": "config",
            },
        )
    try:
        return await _invalidate_after(
            lambda: adapter.insert_row(request), data_cache, connector_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.delete("/{connector_id}/rows", response_model=DeleteRowsResult)
async def delete_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: DeleteRowsRequest,
) -> Any:
    """Delete versioned rows only when every selected row is still current."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsDelete):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support deleting rows",
                "error_kind": "config",
            },
        )
    try:
        return await _invalidate_after(
            lambda: adapter.delete_rows(request), data_cache, connector_id
        )
    except RowConflict:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "One or more rows changed or were deleted; reload and try again"
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.get("/{connector_id}/relation-model", response_model=RelationModel)
async def read_relation_model(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    node_id: str,
) -> Any:
    """Describe one relation named by its opaque catalog node id."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsRelationModel):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not describe relations",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.relation_model(node_id)
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "node_id"],
                    "msg": str(exc),
                    "type": "value_error",
                }
            ],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


async def _change_column(
    run: Callable[[], Awaitable[ColumnChangeResult]],
) -> ColumnChangeResult:
    try:
        return await run()
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.post("/{connector_id}/columns", response_model=ColumnChangeResult)
async def add_column(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: AddColumnRequest,
) -> ColumnChangeResult:
    """Add one validated column to a relation."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsAddColumn):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support adding columns",
                "error_kind": "config",
            },
        )
    return await _invalidate_after(
        lambda: _change_column(lambda: adapter.add_column(request)),
        data_cache,
        connector_id,
    )


@router.delete("/{connector_id}/columns", response_model=ColumnChangeResult)
async def drop_column(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: DropColumnRequest,
) -> ColumnChangeResult:
    """Drop one exact column after the caller's explicit confirmation."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsDropColumn):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support dropping columns",
                "error_kind": "config",
            },
        )
    return await _invalidate_after(
        lambda: _change_column(lambda: adapter.drop_column(request)),
        data_cache,
        connector_id,
    )


@router.patch("/{connector_id}/columns", response_model=ColumnChangeResult)
async def rename_column(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: RenameColumnRequest,
) -> ColumnChangeResult:
    """Rename one exact column without recreating it or its data."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsRenameColumn):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support renaming columns",
                "error_kind": "config",
            },
        )
    return await _invalidate_after(
        lambda: _change_column(lambda: adapter.rename_column(request)),
        data_cache,
        connector_id,
    )


@router.patch("/{connector_id}/columns/default", response_model=ColumnChangeResult)
async def change_column_default(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: ColumnDefaultRequest,
) -> ColumnChangeResult:
    """Set one literal column default, or remove its current default."""
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsColumnDefault):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support changing column defaults",
                "error_kind": "config",
            },
        )
    return await _invalidate_after(
        lambda: _change_column(lambda: adapter.change_column_default(request)),
        data_cache,
        connector_id,
    )


@router.get("/{connector_id}/catalog/path", response_model=list[CatalogNode])
async def read_node_path(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    node_id: str,
) -> Any:
    """
    Every node from the root of the connector down to node_id, node_id last.

    What the id is made of stays the adapter's own business: the client sends
    back the string it was given and receives nodes, never a rule for taking
    one apart. node_id is required — the root of a connector has no path,
    because the root is the connector.
    """
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsNodePath):
        # A source may be able to list children without being able to walk
        # back up: its ids can be opaque handles from someone else's API.
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot say where a node lives",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.path_to(node_id)
    except NodeNotFound as exc:
        # 404 rather than 502: the source answered, and the answer is that
        # there is no such node. A tab outlives the table it shows.
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


class ActionInfo(BaseModel):
    """One action, as much as a client needs to offer and perform it."""

    name: str
    title: str
    destructive: bool
    # Derived from the action itself rather than declared beside it: a flag and
    # an implementation can disagree, an isinstance check cannot.
    takes_file: bool
    # What the action changes, so a client knows what to send it: the nodes
    # that were ticked, or the level they are in.
    acts_on: ActsOn
    # Whether it can be done to the nodes that were asked about. Every action
    # the source has is listed; this says which of them apply here.
    applicable: bool
    params_schema: dict[str, Any]


class ActionTargets(BaseModel):
    """The nodes a question about actions is asked of.

    None is the root. An empty list is refused rather than read as the root:
    two ways of saying the same thing is one way for a client to mean something
    else. The ceiling bounds the work, since applicability is decided per node.
    """

    node_ids: Annotated[list[str], Field(min_length=1, max_length=1000)] | None = None


class ActionRequest(BaseModel):
    node_id: str | None = None
    params: dict[str, Any] = {}


# One status per reason for refusing, in one place. A conflict is not a failure
# of the source, so none of these is a 502.
REFUSAL_STATUS: dict[RefusalReason, int] = {
    "conflict": 409,
    "not_applicable": 422,
    "too_large": 413,
}


def _describe(action: Action[Any], *, applicable: bool) -> ActionInfo:
    return ActionInfo(
        name=action.name,
        title=action.title,
        destructive=action.destructive,
        takes_file=isinstance(action, TakesFile),
        acts_on=action.acts_on,
        applicable=applicable,
        params_schema=action.params_schema(),
    )


def _acting_or_501(adapter: DataAdapter) -> SupportsActions:
    if not isinstance(adapter, SupportsActions):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support actions",
                "error_kind": "config",
            },
        )
    return adapter


async def _available_or_422(
    adapter: SupportsActions, node_id: str | None
) -> list[Action[Any]]:
    try:
        return await adapter.available(node_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


async def _action_for_node(
    adapter: SupportsActions, action_name: str, node_id: str | None
) -> Action[Any]:
    """The action to perform, or the reason it may not be performed here.

    Applicability is decided by the same call that lists what a node offers,
    so what the client is shown and what the server allows cannot drift apart.
    """
    try:
        action = adapter.action(action_name)
    except UnknownAction as exc:
        raise HTTPException(
            status_code=404, detail={"message": f"Unknown action: {action_name}"}
        ) from exc

    available = await _available_or_422(adapter, node_id)
    if action.name not in {offered.name for offered in available}:
        raise HTTPException(
            status_code=422,
            detail={"message": f"{action.title} cannot be done to this node"},
        )
    return action


async def _perform(run: Callable[[], Awaitable[ActionResult]]) -> ActionResult:
    try:
        return await run()
    except ValidationError as exc:
        # ValidationError before ValueError on purpose: it is one of those, and
        # only it can say which field was wrong.
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "params", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()
            ],
        ) from exc
    except ActionRefused as exc:
        raise HTTPException(
            status_code=REFUSAL_STATUS[exc.reason],
            detail={"message": exc.message, "reason": exc.reason},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.post("/{connector_id}/actions", response_model=list[ActionInfo])
async def read_actions(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    body: ActionTargets,
) -> Any:
    """
    List everything the source can do, saying which of it every node admits.

    Applicability is asked per node rather than per source type: whether a node
    may be renamed depends on its state as well as its kind — the root of a
    connector is an ordinary directory that may not be removed. It arrives as a
    flag on the whole vocabulary rather than as the length of the list, so a
    menu built from this keeps its shape as the user walks the catalog and
    greys out what does not apply. Nothing is allowed by being listed: running
    an action asks `available` again.

    A read expressed as a POST for the same reason `fetch` is one: the input is
    a list of opaque identifiers with no bound on its length, and selecting a
    directory of five hundred files leaves no room in a query string.
    """
    adapter = _acting_or_501(
        await _adapter_for(session, connector_id, current_user, resources)
    )
    targets: list[str | None] = list(body.node_ids) if body.node_ids else [None]
    offers = [await _available_or_422(adapter, node_id) for node_id in targets]
    admitted = {
        action.name for action in common_actions(offers, bulk_only=len(targets) > 1)
    }
    return [
        _describe(action, applicable=action.name in admitted)
        for action in adapter.all_actions()
    ]


@router.post("/{connector_id}/actions/{action_name}", response_model=ActionResult)
async def run_action(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionRequest,
) -> Any:
    """
    Perform an action that needs nothing but its parameters.
    """
    adapter = _acting_or_501(
        await _adapter_for(session, connector_id, current_user, resources)
    )
    action = await _action_for_node(adapter, action_name, body.node_id)
    if not isinstance(action, TakesParams):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} needs a file to be sent with it"},
        )
    return await _invalidate_after(
        lambda: _perform(lambda: action.perform(body.node_id, body.params)),
        data_cache,
        connector_id,
    )


@router.post("/{connector_id}/actions/{action_name}/file", response_model=ActionResult)
async def run_action_with_file(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    action_name: str,
    file: Annotated[UploadFile, File()],
    node_id: Annotated[str, Form()] = "",
    params: Annotated[str, Form()] = "{}",
) -> Any:
    """
    Perform an action that carries a file.

    A second route rather than a second body type on the first: HTTP has two
    shapes of request body, and each refuses an action of the other transport.
    Parameters travel as a JSON field of the form, so the action validates them
    by the same model either way.
    """
    adapter = _acting_or_501(
        await _adapter_for(session, connector_id, current_user, resources)
    )
    target = node_id or None
    action = await _action_for_node(adapter, action_name, target)
    if not isinstance(action, TakesFile):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} does not take a file"},
        )

    try:
        given = json.loads(params)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": "The params field is not valid JSON"},
        ) from exc
    if not isinstance(given, dict):
        raise HTTPException(
            status_code=422, detail={"message": "The params field must be an object"}
        )

    return await _invalidate_after(
        lambda: _perform(lambda: action.perform_with_file(target, given, file)),
        data_cache,
        connector_id,
    )

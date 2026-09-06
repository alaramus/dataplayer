import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, cast

from anyio import to_thread
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, StreamingResponse

from app.adapters.actions import (
    Action,
    ActionDownloadReady,
    ActionPreview,
    ActionRefused,
    ActionResult,
    ActsOn,
    ConnectorDraft,
    PreparesConnector,
    Previews,
    PreviewsSet,
    ProducesDownload,
    RefusalReason,
    SupportsActions,
    TakesFile,
    TakesNodeSet,
    TakesParams,
    UnknownAction,
    common_actions,
)
from app.adapters.cache import (
    CacheArea,
    CacheKey,
    DataCache,
    DataCacheDep,
    cached_read,
)
from app.adapters.cache_serialization import CacheFormat
from app.adapters.catalog import CatalogNode
from app.adapters.column_changes import (
    AddColumnRequest,
    ColumnChangeResult,
    ColumnDefaultRequest,
    ColumnNullabilityRequest,
    ColumnNullabilityResult,
    ColumnTypeChanged,
    ColumnTypeChangeResult,
    ColumnTypeRequest,
    DropColumnRequest,
    NullabilityChanged,
    RenameColumnRequest,
)
from app.adapters.constraints import (
    ConstraintCreated,
    ConstraintDropped,
    CreateConstraintRequest,
    CreateConstraintResult,
    DropConstraintRequest,
)
from app.adapters.content import (
    STREAMED_CONTENT,
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    ImageContent,
    UpdateContentRequest,
)
from app.adapters.export import ExportRequest
from app.adapters.fetch import (
    DownloadPageRequest,
    FetchRequest,
    FetchResult,
    as_read_only,
)
from app.adapters.indexes import (
    CreateIndexRequest,
    CreateIndexResult,
    DropIndexRequest,
    IndexCreated,
    IndexDropped,
)
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    DataAdapter,
    DescribesDraft,
    NodeNotFound,
    ParsesConnectionString,
    SearchesContents,
    SupportsAddColumn,
    SupportsArrivingReferences,
    SupportsCatalog,
    SupportsColumnDefault,
    SupportsColumnNullability,
    SupportsColumnType,
    SupportsConnectionString,
    SupportsConstraints,
    SupportsContent,
    SupportsContentEdit,
    SupportsContentPreview,
    SupportsContentStream,
    SupportsCreateRelation,
    SupportsDelete,
    SupportsDropColumn,
    SupportsExport,
    SupportsFetch,
    SupportsIndexes,
    SupportsInsert,
    SupportsNodePath,
    SupportsNodeSearch,
    SupportsNodeSummary,
    SupportsReferences,
    SupportsRelationModel,
    SupportsRenameColumn,
    SupportsTableDesign,
    SupportsUpdate,
)
from app.adapters.references import (
    ArrivingReference,
    ArrivingReferencesRequest,
    FollowReferenceRequest,
    ReferenceConnection,
    ReferencedRows,
    ReferenceTarget,
)
from app.adapters.registry import AdapterType
from app.adapters.relation import RelationModel, without_structure_changes
from app.adapters.relation_changes import (
    CreateRelationRequest,
    NewRelationOptions,
    RelationCreated,
)
from app.adapters.resources import ResourcesDep
from app.adapters.row_commands import (
    RowCommandResult,
    SupportsRowCommands,
    UnknownRowCommand,
)
from app.adapters.search import (
    DEFAULT_MATCHES,
    MAX_MATCHES,
    MAX_QUERY_LENGTH,
    NodeSearchRequest,
    NodeSearchResult,
)
from app.adapters.summary import NodeSummary
from app.adapters.table_design import (
    TableDesignOptions,
    TableDesignTarget,
    TablePlan,
    TablePlanRequest,
)
from app.adapters.update import (
    CellsUpdated,
    DeleteRowsRequest,
    DeleteRowsResult,
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    RowConflict,
    RowsInserted,
    UpdateCellRequest,
    UpdateCellResult,
    UpdateCellsRequest,
    UpdateCellsResult,
)
from app.connectors import (
    action_downloads,
    content_tickets,
    crud,
    declared,
    downloads,
    health,
    imports,
    ranges,
    service,
)
from app.connectors.access import (
    adapter_for,
    adapter_type_or_422,
    context_for,
    get_or_404,
    resolve,
    resolve_adapter,
    resolve_source,
)
from app.connectors.models import (
    Connector,
    ConnectorCreate,
    ConnectorPublic,
    ConnectorsPublic,
    ConnectorUpdate,
    GrantPublic,
    GrantsPublic,
    GrantWrite,
)
from app.core.access import Access, at_least
from app.core.config import settings
from app.core.db import SessionDep
from app.core.schemas import Message, get_datetime_utc
from app.realtime.topics import TopicsDep
from app.users import storage
from app.users.deps import CurrentUser, get_current_user
from app.users.models import User

router = APIRouter(prefix="/connectors", tags=["connectors"])
CATALOG_CACHE_FORMAT: CacheFormat[list[CatalogNode]] = CacheFormat(list[CatalogNode])
FETCH_CACHE_FORMAT: CacheFormat[FetchResult] = CacheFormat(FetchResult)


def _cache_key(
    current_user: User,
    connector_id: uuid.UUID,
    area: CacheArea,
    request: str,
) -> CacheKey:
    return CacheKey(current_user.id, connector_id, area, request)


async def _invalidate_after[T](
    run: Callable[[], Awaitable[T]], data_cache: DataCache, connector_id: uuid.UUID
) -> T:
    result = await run()
    await data_cache.invalidate_connector(connector_id)
    return result


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


async def _public(
    session: AsyncSession, connector: Connector, access: Access
) -> ConnectorPublic:
    """A connection as the caller sees it, including what they may do with it."""
    owner_email: str | None = None
    if access != "own":
        owner = await session.get(User, connector.owner_id)
        owner_email = owner.email if owner is not None else None
    return ConnectorPublic.model_validate(
        connector, update={"access": access, "owner_email": owner_email}
    )


@router.get("/content-files/{ticket}", include_in_schema=False)
async def preview_content_file(
    session: SessionDep,
    resources: ResourcesDep,
    ticket: str,
) -> Response:
    """Redeem one short-lived inline-preview ticket."""
    claims = content_tickets.read_content_ticket(ticket)
    # The purpose is checked, not merely the signature: a ticket minted for the
    # ranged route of D52 is not authority for bytes held whole.
    if not isinstance(claims, content_tickets.ImagePreviewClaims):
        raise HTTPException(status_code=404, detail="Content not found")
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Content not found")

    adapter = await adapter_for(
        session, claims.connector_id, user, resources, requires="read"
    )
    try:
        if not isinstance(adapter, SupportsContentPreview):
            raise HTTPException(
                status_code=501,
                detail={
                    "message": "This source does not support content previews",
                    "error_kind": "config",
                },
            )
        preview = await adapter.preview_content(
            ContentRequest(
                node_id=claims.node_id,
                representation=claims.representation,
            )
        )
        return Response(
            content=preview.body,
            media_type=preview.media_type,
            headers={
                "Cache-Control": "private, no-store",
                "Content-Disposition": content_tickets.content_disposition(
                    preview.filename, inline=True
                ),
                "X-Content-Type-Options": "nosniff",
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Content not found") from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.get("/content-streams/{ticket}", include_in_schema=False)
async def stream_content_file(
    session: SessionDep,
    resources: ResourcesDep,
    ticket: str,
    request: Request,
) -> Response:
    """Redeem one short-lived stream ticket, answering `Range` (D52).

    The HTTP is here and the bytes are the source's: one range is parsed
    against the size the source states, and the source is asked only for the
    bytes between two offsets. A player asks for the end of a file before it
    asks for the beginning, so an answer of the whole body every time would
    mean downloading a recording to hear its last second.
    """
    claims = content_tickets.read_content_ticket(ticket)
    if not isinstance(claims, content_tickets.ContentStreamClaims):
        raise HTTPException(status_code=404, detail="Content not found")
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Content not found")

    adapter = await adapter_for(
        session, claims.connector_id, user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsContentStream):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not stream content",
                "error_kind": "config",
            },
        )
    try:
        stream = await adapter.open_content_stream(
            ContentRequest(
                node_id=claims.node_id, representation=claims.representation
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Content not found") from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, no-store",
        "Content-Disposition": content_tickets.content_disposition(
            stream.filename, inline=True
        ),
        "X-Content-Type-Options": "nosniff",
    }
    try:
        wanted = ranges.parse_range(
            request.headers.get("range"), stream.size_bytes
        )
    except ranges.UnsatisfiableRange:
        headers["Content-Range"] = f"bytes */{stream.size_bytes}"
        raise HTTPException(
            status_code=416, detail="Requested range not satisfiable", headers=headers
        ) from None

    if wanted is None:
        return StreamingResponse(
            stream.read(0, max(stream.size_bytes - 1, 0)),
            media_type=stream.media_type,
            headers={**headers, "Content-Length": str(stream.size_bytes)},
        )
    return StreamingResponse(
        stream.read(wanted.start, wanted.end),
        status_code=206,
        media_type=stream.media_type,
        headers={
            **headers,
            "Content-Length": str(wanted.length),
            "Content-Range": wanted.content_range(stream.size_bytes),
        },
    )


@router.get("/action-downloads/{ticket}", include_in_schema=False)
async def download_action_result(
    session: SessionDep,
    resources: ResourcesDep,
    ticket: str,
) -> StreamingResponse:
    """Redeem one source action ticket after rechecking access and targets."""
    claims = action_downloads.read_action_download_ticket(ticket)
    if claims is None:
        raise HTTPException(status_code=404, detail="Download not found")
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Download not found")

    adapter, access = await resolve_adapter(
        session, claims.connector_id, user, resources, requires="read"
    )
    action = await _action_for_nodes(
        _acting_or_501(adapter), claims.action_name, claims.node_ids
    )
    _allowed_or_403(action, access)
    if not isinstance(action, ProducesDownload):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} does not produce a download"},
        )
    prepared = await _perform(
        lambda: action.download(claims.node_ids, claims.params)
    )
    return StreamingResponse(
        prepared.body,
        media_type=prepared.metadata.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": content_tickets.content_disposition(
                prepared.metadata.filename, inline=False
            ),
            "Content-Length": str(prepared.metadata.size_bytes),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/export-downloads/{ticket}", response_class=FileResponse)
async def download_finished_export(ticket: str) -> FileResponse:
    """Redeem a short-lived ticket for one finished export.

    Two places a signed claim may name, and the difference is whose the file
    is: one written to be kept is in the user's own directory and stays; one
    written only to be handed over is outside it and is taken away as soon as
    it has been sent.
    """
    claims = downloads.read_export_ticket(ticket)
    if claims is None:
        raise HTTPException(status_code=404, detail="Export not found")
    scratch = await to_thread.run_sync(
        lambda: downloads.scratch_export_path(claims)
    )
    path = scratch or await to_thread.run_sync(
        lambda: downloads.stored_export_path(
            storage.home_dir(claims.user_id), claims
        )
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path,
        media_type="text/csv",
        filename=path.name,
        headers={"Cache-Control": "private, no-store"},
        background=(
            BackgroundTask(downloads.forget_scratch, path)
            if scratch is not None
            else None
        ),
    )


@router.post("/", response_model=ConnectorPublic)
async def create_connector(
    session: SessionDep, current_user: CurrentUser, connector_in: ConnectorCreate
) -> Any:
    """
    Create a new connector.
    """
    adapter_type = adapter_type_or_422(connector_in.adapter_type)
    config, secrets = _split_or_422(adapter_type, connector_in.options)
    connector = await crud.create(
        session,
        name=connector_in.name,
        adapter_type=adapter_type.name,
        config=config,
        secrets=secrets,
        owner_id=current_user.id,
        execution_policy=connector_in.execution_policy,
        tab_color=connector_in.tab_color,
        cache_ttl_seconds=connector_in.cache_ttl_seconds,
    )
    return await _public(session, connector, "own")


@router.get("/", response_model=ConnectorsPublic)
async def read_connectors(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve connectors.
    """
    connectors, count = await crud.list_for(
        session, user=current_user, skip=skip, limit=limit
    )
    return ConnectorsPublic(
        data=[
            ConnectorPublic.model_validate(
                connector, update={"access": access, "owner_email": owner_email}
            )
            for connector, access, owner_email in connectors
        ],
        count=count,
    )


@router.get("/{connector_id}", response_model=ConnectorPublic)
async def read_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """
    Get connector by ID.
    """
    connector, access = await resolve(
        session, connector_id, current_user, requires="read"
    )
    return await _public(session, connector, access)


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
    connector = await get_or_404(
        session, connector_id, current_user, requires="own"
    )

    if connector_in.name is not None:
        connector.name = connector_in.name

    # An explicit null restores the theme; an omitted field keeps the color.
    if "tab_color" in connector_in.model_fields_set:
        connector.tab_color = connector_in.tab_color

    if connector_in.enabled is not None:
        connector.enabled = connector_in.enabled

    if connector_in.execution_policy is not None:
        # Only reachable by the owner: this route asks for `own` above.
        connector.execution_policy = connector_in.execution_policy

    # An explicit null hands the window back to the source; an omitted field
    # leaves it alone. The same distinction `tab_color` makes above, for the
    # same reason: null is an answer here rather than the absence of one.
    if "cache_ttl_seconds" in connector_in.model_fields_set:
        connector.cache_ttl_seconds = connector_in.cache_ttl_seconds

    if connector_in.options is not None:
        adapter_type = adapter_type_or_422(connector.adapter_type)
        options = service.fill_missing_secrets(
            adapter_type, connector_in.options, connector.secrets
        )
        connector.config, connector.secrets = _split_or_422(adapter_type, options)

    connector.updated_at = get_datetime_utc()
    saved = await crud.save(session, connector=connector)
    await data_cache.invalidate_connector(connector_id)
    return await _public(session, saved, "own")


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
    connector = await get_or_404(
        session, connector_id, current_user, requires="own"
    )
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
    adapter_type = adapter_type_or_422(body.adapter_type)
    options = body.options
    if body.connector_id is not None:
        # Reading a draft against a stored connection only substitutes the
        # secrets the caller did not retype, so seeing it is enough.
        connector = await get_or_404(
            session, body.connector_id, current_user, requires="read"
        )
        options = service.fill_missing_secrets(adapter_type, options, connector.secrets)

    try:
        return service.build_adapter(
            adapter_type, options, context_for(current_user.id)
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
    driver = adapter_type_or_422(body.adapter_type).adapter_class
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
    adapter_type = adapter_type_or_422(body.adapter_type)
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
    adapter = await adapter_for(
        session, connector_id, current_user, requires="read"
    )
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
    source = await resolve_source(
        session, connector_id, current_user, resources, requires="read"
    )
    adapter, access = source.adapter, source.access
    if not isinstance(adapter, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support reading rows",
                "error_kind": "config",
            },
        )
    try:
        result = await cached_read(
            data_cache=data_cache,
            adapter=adapter,
            key=_cache_key(
                current_user, connector_id, "fetch", request.model_dump_json()
            ),
            refresh=refresh,
            response=response,
            load=lambda: adapter.fetch(request),
            cache_format=FETCH_CACHE_FORMAT,
            cache_ttl_seconds=source.cache_ttl_seconds,
        )
        result = result.model_copy(
            update={
                # After the cache with everything else here, and for the same
                # reason: what a source produced is the same page for everyone,
                # and which references this person has drawn over it is not
                # (D106).
                "references": [
                    *result.references,
                    *await declared.references_for(
                        session,
                        user=current_user,
                        connector_id=connector_id,
                        node_id=request.node_id,
                    ),
                ],
                "export_supported": isinstance(adapter, SupportsExport),
                "export_reason": (
                    None
                    if isinstance(adapter, SupportsExport)
                    else "This source cannot export all matching rows"
                ),
                # What this relation offers to do to selected rows. Asked of
                # the composed adapter for the reason export is: a capability
                # belongs to the whole source, not to the module that read the
                # page (D70). Filtered by what the caller holds, so a command
                # nobody may run is not drawn at all.
                "row_commands": [
                    command
                    for command in (
                        adapter.row_commands(request.node_id)
                        if isinstance(adapter, SupportsRowCommands)
                        else []
                    )
                    if at_least(access, command.requires)
                ],
            }
        )
        # After the cache and not before it: the page a source produced is the
        # same page for everyone, and what one caller may do with it is not.
        if not at_least(access, "write"):
            return as_read_only(result, "You have read-only access to this connection")
        return result
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


@router.post("/{connector_id}/content", response_model=ContentResult)
async def read_content(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: ContentRequest,
) -> Any:
    """Read the requested bounded, content-native representation of a node."""
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsContent):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support content viewers",
                "error_kind": "config",
            },
        )
    try:
        result = await adapter.read_content(request)
        if isinstance(result, ImageContent):
            if not isinstance(adapter, SupportsContentPreview):
                raise HTTPException(
                    status_code=501,
                    detail={
                        "message": "This source does not support content previews",
                        "error_kind": "config",
                    },
                )
            ticket = content_tickets.issue_content_ticket(
                user_id=current_user.id,
                connector_id=connector_id,
                node_id=request.node_id,
            )
            return result.model_copy(
                update={"preview_url": content_tickets.content_ticket_url(ticket)}
            )
        if isinstance(result, STREAMED_CONTENT):
            if not isinstance(adapter, SupportsContentStream):
                raise HTTPException(
                    status_code=501,
                    detail={
                        "message": "This source does not stream content",
                        "error_kind": "config",
                    },
                )
            stream_ticket = content_tickets.issue_stream_ticket(
                representation=result.kind,
                user_id=current_user.id,
                connector_id=connector_id,
                node_id=request.node_id,
            )
            return result.model_copy(
                update={
                    "stream_url": content_tickets.content_stream_url(stream_ticket)
                }
            )
        return result
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


@router.post("/{connector_id}/content/editor", response_model=EditorContent)
async def read_editor_content(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: EditorContentRequest,
) -> Any:
    """Read bounded source text and the opaque version required to save it."""
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsContentEdit):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support editing content",
                "error_kind": "config",
            },
        )
    try:
        result = await adapter.read_editor_content(request)
        if not at_least(access, "write"):
            return result.model_copy(
                update={
                    "writable": False,
                    "reason": "You have read-only access to this connection",
                }
            )
        return result
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


@router.patch("/{connector_id}/content/editor", response_model=ContentUpdated)
async def update_content(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: UpdateContentRequest,
) -> Any:
    """Atomically replace editable content while its loaded version still matches."""
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
    if not isinstance(adapter, SupportsContentEdit):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support editing content",
                "error_kind": "config",
            },
        )
    try:
        return await _invalidate_after(
            lambda: adapter.update_content(request), data_cache, connector_id
        )
    except ContentConflict:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The file changed or was deleted; reload it and try again"
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
    source = await resolve_source(
        session, connector_id, current_user, resources, requires="read"
    )
    adapter = source.adapter
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
        return await cached_read(
            data_cache=data_cache,
            adapter=adapter,
            key=_cache_key(
                current_user, connector_id, "catalog", json.dumps(node_id)
            ),
            refresh=refresh,
            response=response,
            load=lambda: adapter.list_children(node_id),
            cache_format=CATALOG_CACHE_FORMAT,
            cache_ttl_seconds=source.cache_ttl_seconds,
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
) -> Response:
    """Re-read the bounded page the grid describes and hand it over.

    Nothing is left behind. Keeping a copy is the route below, asked for
    separately, because a download that also filed itself away was leaving
    litter in the personal storage of everyone who only wanted the file (D28).
    """
    result = await _page_for_download(
        session, current_user, resources, connector_id, request
    )
    try:
        body = downloads.page_csv(columns=request.columns, result=result)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from None
    filename = downloads.page_filename(request.title)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": content_tickets.content_disposition(
                filename, inline=False
            ),
        },
    )


@router.post(
    "/{connector_id}/downloads/page/keep",
    response_model=downloads.KeptDownload,
)
async def keep_page(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: DownloadPageRequest,
) -> downloads.KeptDownload:
    """Write the same page into the caller's own files, and send nothing back."""
    result = await _page_for_download(
        session, current_user, resources, connector_id, request
    )
    try:
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
    except OSError:
        raise HTTPException(
            status_code=507,
            detail={"message": "The page could not be stored", "error_kind": "config"},
        ) from None
    return downloads.KeptDownload(filename=path.name, row_count=len(result.rows))


async def _page_for_download(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: DownloadPageRequest,
) -> FetchResult:
    """The fresh page both destinations are written from.

    Read again rather than taken from the client: the columns a stale layout
    names are checked against this answer, so nothing can shift a value under
    the wrong heading.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
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
        return await adapter.fetch(fetch_request)
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


@router.post(
    "/{connector_id}/downloads/export",
    response_model=downloads.ExportReady,
)
async def export_all_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: downloads.ExportDownloadRequest,
) -> downloads.ExportReady:
    """Stage every matching row, outside personal storage, to be handed over.

    Staged rather than streamed into the answer because a native browser
    download is what keeps a whole relation out of the browser's memory, and
    a native download needs an address to point at (D28). The file lives in a
    directory of its own and goes when the ticket is redeemed, so nothing is
    kept by a download nobody asked to keep.
    """
    adapter = _exporting_adapter(
        await adapter_for(
            session, connector_id, current_user, resources, requires="read"
        )
    )
    export_request = ExportRequest.model_validate(
        request.model_dump(exclude={"title"})
    )
    try:
        path, row_count = await downloads.stream_csv_export(
            title=request.title,
            columns=request.columns,
            batches=adapter.export_rows(export_request),
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
    except OSError:
        raise HTTPException(
            status_code=507,
            detail={"message": "The export could not be stored", "error_kind": "config"},
        ) from None

    ticket = downloads.issue_export_ticket(
        user_id=current_user.id,
        connector_id=connector_id,
        filename=path.name,
        scratch=path.parent.name,
    )
    return downloads.ExportReady(
        filename=path.name,
        row_count=row_count,
        download_url=f"{settings.API_V1_STR}/connectors/export-downloads/{ticket}",
    )


@router.post(
    "/{connector_id}/downloads/export/keep",
    response_model=downloads.KeptDownload,
)
async def keep_all_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: downloads.ExportDownloadRequest,
) -> downloads.KeptDownload:
    """Write every matching row into the caller's own files, and send nothing back."""
    adapter = _exporting_adapter(
        await adapter_for(
            session, connector_id, current_user, resources, requires="read"
        )
    )
    export_request = ExportRequest.model_validate(
        request.model_dump(exclude={"title"})
    )
    try:
        path, row_count = await downloads.save_csv_export(
            home=storage.home_dir(current_user.id),
            connector_id=connector_id,
            title=request.title,
            columns=request.columns,
            batches=adapter.export_rows(export_request),
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
    except OSError:
        raise HTTPException(
            status_code=507,
            detail={"message": "The export could not be stored", "error_kind": "config"},
        ) from None
    return downloads.KeptDownload(filename=path.name, row_count=row_count)


def _exporting_adapter(adapter: object) -> SupportsExport:
    if not isinstance(adapter, SupportsExport):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support exporting all rows",
                "error_kind": "config",
            },
        )
    return adapter


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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
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


@router.patch("/{connector_id}/rows/cells", response_model=UpdateCellsResult)
async def update_cells(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: UpdateCellsRequest,
) -> Any:
    """
    Change a block of cells across several rows, or none of them.

    Values the column's type cannot read are an answer naming every such cell,
    with nothing written; a row that no longer holds the version it was read
    with is the same conflict a single-cell edit gives.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
    if not isinstance(adapter, SupportsUpdate):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot change rows",
                "error_kind": "config",
            },
        )
    try:
        result = await adapter.update_cells(request)
    except RowConflict:
        raise HTTPException(
            status_code=409,
            detail={"message": "A row changed or was deleted; reload and try again"},
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
    if isinstance(result, CellsUpdated):
        await data_cache.invalidate_connector(connector_id)
    return result


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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
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


async def _import_sides(
    session: SessionDep,
    connector_id: uuid.UUID,
    request: imports.ImportRowsRequest,
    current_user: CurrentUser,
    resources: ResourcesDep,
) -> tuple[DataAdapter, SupportsFetch]:
    """The two connectors this command names, each with its own permission.

    Writing into the target and reading the source are separate grants (D33),
    and neither implies the other.
    """
    try:
        source_id = uuid.UUID(request.source_connector_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "source_connector_id"],
                    "msg": "That is not a connector id",
                    "type": "value_error",
                }
            ],
        ) from None
    target = await adapter_for(
        session, connector_id, current_user, resources, requires="write"
    )
    source = await adapter_for(
        session, source_id, current_user, resources, requires="read"
    )
    if not isinstance(source, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "That source cannot be read as rows",
                "error_kind": "config",
            },
        )
    return target, source


async def _read_for_import(
    source: SupportsFetch,
    request: imports.ImportRowsRequest | imports.CreateRelationFromSourceRequest,
    ceiling: int,
) -> imports.ReadRows:
    try:
        pairs = (
            request.columns
            if isinstance(request, imports.ImportRowsRequest)
            else request.pairs()
        )
        return await imports.read_rows(source, request.source_node_id, pairs, ceiling)
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


@router.post("/{connector_id}/import/preview", response_model=imports.ImportPreview)
async def preview_import(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: imports.ImportRowsRequest,
) -> Any:
    """
    The first rows as they would arrive, through the pairing that was given.

    It answers "have I paired these columns correctly", and deliberately says
    nothing about the target: the move itself checks every value and writes
    nothing when one cannot be read, so a second validating call would be the
    same answer one step earlier and a second contract to keep in step.
    """
    _, source = await _import_sides(
        session, connector_id, request, current_user, resources
    )
    read = await _read_for_import(source, request, imports.PREVIEW_ROWS)
    return imports.ImportPreview(
        columns=read.columns, rows=read.rows, more=read.truncated
    )


@router.post("/{connector_id}/import", response_model=imports.RowsMoved)
async def import_rows(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: imports.ImportRowsRequest,
) -> Any:
    """
    Move a bounded set of rows from one source into a relation of another.

    Either every row arrives or none does. A value the target cannot read is
    named — row, column and the value itself — and nothing is written. A source
    holding more rows than the ceiling is not refused, but the answer says the
    rows were cut off.
    """
    target, source = await _import_sides(
        session, connector_id, request, current_user, resources
    )
    if not isinstance(target, SupportsInsert):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot accept rows",
                "error_kind": "config",
            },
        )
    read = await _read_for_import(source, request, imports.IMPORT_CEILING)
    if not read.rows:
        return imports.RowsMoved(inserted=0, truncated=False)
    result = await _shape_change(
        lambda: target.insert_rows(
            InsertRowsRequest(
                node_id=request.node_id, columns=read.columns, rows=read.rows
            )
        )
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
                    "msg": f"{cell.value!r} cannot be read by {cell.column}",
                    "type": "value_error",
                }
                for cell in result.cells
            ],
        )
    await data_cache.invalidate_connector(connector_id)
    return imports.RowsMoved(inserted=result.inserted, truncated=read.truncated)


class RowCommandRequest(BaseModel):
    """One command, the relation it belongs to, and the rows it is about.

    The keys are the values of the column the command declared as its own
    `identified_by`. They are the source's to read: nothing here knows what a
    process id is, and a key that means nothing to the source is refused by it
    rather than validated by a rule restated in this module.
    """

    node_id: str
    name: str
    keys: Annotated[list[str], Field(min_length=1, max_length=500)]


@router.post("/{connector_id}/rows/command", response_model=RowCommandResult)
async def run_row_command(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    body: RowCommandRequest,
) -> Any:
    """
    Do one source-declared thing to the rows somebody selected.

    The command is resolved through what the node offers, so what a client is
    shown and what the server allows cannot drift apart — and the level it
    needs is the command's own statement, checked after the name has resolved
    for the reason an action's is (D70).
    """
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsRowCommands):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source has no commands over rows",
                "error_kind": "config",
            },
        )
    offered = {
        command.name: command for command in adapter.row_commands(body.node_id)
    }
    command = offered.get(body.name)
    if command is None:
        raise HTTPException(
            status_code=404,
            detail={"message": f"Unknown row command: {body.name}"},
        )
    if not at_least(access, command.requires):
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"{command.title} needs {command.requires} access",
                "required": command.requires,
                "held": access,
            },
        )
    try:
        result = await adapter.run_row_command(body.node_id, body.name, body.keys)
    except UnknownRowCommand as exc:
        raise HTTPException(
            status_code=404, detail={"message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc
    # What the command did is not in the page that was read a moment ago.
    await data_cache.invalidate_connector(connector_id)
    return result


@router.post("/{connector_id}/relations/options", response_model=NewRelationOptions)
async def new_relation_options(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: imports.NewRelationTarget,
) -> Any:
    """What one source-owned container accepts for a new relation."""
    target = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(target, SupportsCreateRelation):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot create relations",
                "error_kind": "config",
            },
        )
    return await _shape_change(
        lambda: target.new_relation_options(request.parent_node_id)
    )


@router.post("/{connector_id}/relations/from-source", response_model=RelationCreated)
async def create_relation_from_source(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: imports.CreateRelationFromSourceRequest,
) -> Any:
    """Create and fill one relation from any bounded readable source."""
    try:
        source_id = uuid.UUID(request.source_connector_id)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "source_connector_id"],
                    "msg": "That is not a connector id",
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
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot create relations",
                "error_kind": "config",
            },
        )
    if not isinstance(source, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "That source cannot be read as rows",
                "error_kind": "config",
            },
        )
    read = await _read_for_import(source, request, imports.IMPORT_CEILING)
    if read.truncated:
        raise HTTPException(
            status_code=413,
            detail={
                "message": "A new table may be filled with at most "
                f"{imports.IMPORT_CEILING} rows"
            },
        )
    result = await _shape_change(
        lambda: target.create_relation(
            CreateRelationRequest(
                parent_node_id=request.parent_node_id,
                name=request.name,
                columns=request.new_columns(),
                rows=read.rows,
            )
        )
    )
    if not isinstance(result, RelationCreated):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "rows", cell.row, cell.column],
                    "msg": f"{cell.value!r} cannot be read by {cell.column}",
                    "type": "value_error",
                }
                for cell in result.cells
            ],
        )
    await data_cache.invalidate_connector(connector_id)
    return result


def _in_connection(target: ReferenceTarget, connector: Connector) -> ReferenceTarget:
    """Say which connection the rows are in, which the source cannot (D108).

    An adapter knows itself and not its own identity, so it answers with a node
    and a predicate; this is the one place that knows which connection was
    asked. A declared reference has already named its own, and that one stands.
    """
    if not isinstance(target, ReferencedRows) or target.connector is not None:
        return target
    return target.model_copy(
        update={
            "connector": ReferenceConnection(
                id=connector.id,
                name=connector.name,
                adapter_type=connector.adapter_type,
            )
        }
    )


@router.post("/{connector_id}/references", response_model=ReferenceTarget)
async def follow_reference(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: FollowReferenceRequest,
) -> Any:
    """
    Follow one foreign key of one row to the rows it names.

    The answer carries the target node as the catalog describes it and the
    predicate the source built against that target's own columns. Reading is
    enough: following a key looks at rows the caller may already read.
    """
    # Through the one door to a live source, declared reference or not: that is
    # where a switched-off connection is refused, and a route that reached past
    # it would be the exception that unlearns the rule.
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    connector = await get_or_404(session, connector_id, current_user, requires="read")
    try:
        # A name this application issued is answered by this application: the
        # source has never heard of it, and a file source has no references at
        # all yet still has the ones somebody drew (D107).
        if declared.parse_name(request.reference) is not None:
            return _in_connection(
                await declared.follow(
                    session,
                    user=current_user,
                    resources=resources,
                    connector_id=connector_id,
                    request=request,
                ),
                connector,
            )
        if not isinstance(adapter, SupportsReferences):
            raise HTTPException(
                status_code=501,
                detail={
                    "message": "This source has no references to follow",
                    "error_kind": "config",
                },
            )
        if request.direction == "incoming" and not isinstance(
            adapter, SupportsArrivingReferences
        ):
            raise HTTPException(
                status_code=501,
                detail={
                    "message": "This source cannot say what points at a relation",
                    "error_kind": "config",
                },
            )
        return _in_connection(await adapter.follow_reference(request), connector)
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        # The reference or its columns, checked against what the source says
        # now. A bad request rather than an upstream failure: nothing was run.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body"], "msg": str(exc), "type": "value_error"}],
        ) from exc
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        ) from exc


@router.post(
    "/{connector_id}/references/arriving", response_model=list[ArrivingReference]
)
async def arriving_references(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: ArrivingReferencesRequest,
) -> Any:
    """
    List the keys of other relations that land on this one (D110).

    Asked when somebody wants the way back, not on every page: this is a
    search of the catalog for arriving keys rather than a reading of one
    relation's own definition. Following one is the ordinary follow route with
    `direction="incoming"`, so nothing here says where anything is.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsArrivingReferences):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot say what points at a relation",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.arriving_references(request.node_id)
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


@router.get("/{connector_id}/relation-model", response_model=RelationModel)
async def read_relation_model(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    node_id: str,
) -> Any:
    """Describe one relation named by its opaque catalog node id."""
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsRelationModel):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not describe relations",
                "error_kind": "config",
            },
        )
    try:
        model = await adapter.relation_model(node_id)
        if not at_least(access, "structure"):
            return without_structure_changes(
                model, "You may not change the structure of this connection"
            )
        return model
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


@router.get("/{connector_id}/catalog/search", response_model=NodeSearchResult)
async def search_catalog(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    # Bounded by the route as well as by the model, from the same numbers: a
    # query string is validated before a handler runs, and that is where a
    # caller's mistake should be answered.
    query: str = Query(min_length=1, max_length=MAX_QUERY_LENGTH),
    node_id: str | None = None,
    limit: int = Query(default=DEFAULT_MATCHES, ge=1, le=MAX_MATCHES),
) -> Any:
    """Find nodes by name below one level of the catalog.

    A read of the catalog and nothing more: what comes back are the same nodes
    the listing gives, each with the place it was found in (D76). The query is
    matched as a substring and never compiled, and every bound the walk has
    belongs to the source.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsNodeSearch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot be searched",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.search_nodes(
            NodeSearchRequest(node_id=node_id, query=query, limit=limit)
        )
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "query"],
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


@router.get(
    "/{connector_id}/catalog/search-contents", response_model=NodeSearchResult
)
async def search_catalog_contents(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    query: str = Query(min_length=1, max_length=MAX_QUERY_LENGTH),
    node_id: str | None = None,
    limit: int = Query(default=DEFAULT_MATCHES, ge=1, le=MAX_MATCHES),
) -> Any:
    """Find nodes whose contents hold the words, below one level.

    A separate route from the one above because it is a separate promise: this
    one opens files, and a source that lists names without being able to read
    them answers 501 here and is never offered the gesture (D76).
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SearchesContents):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot be searched inside its files",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.search_contents(
            NodeSearchRequest(node_id=node_id, query=query, limit=limit)
        )
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["query", "query"],
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


@router.get("/{connector_id}/node-summary", response_model=NodeSummary)
async def read_node_summary(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    node_id: str,
) -> Any:
    """Describe one node itself: its facts, and what its format states.

    Reading is enough, and nothing here depends on the grant beyond it: a
    summary says what a node is, and everything in it is already visible to
    somebody who may list the level it sits in (D75).
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
    if not isinstance(adapter, SupportsNodeSummary):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not describe its nodes",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.node_summary(node_id)
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
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


async def _change_column_nullability(
    adapter: SupportsColumnNullability, request: ColumnNullabilityRequest
) -> ColumnNullabilityResult:
    try:
        return await adapter.change_column_nullability(request)
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


@router.patch(
    "/{connector_id}/columns/nullability", response_model=ColumnNullabilityResult
)
async def change_column_nullability(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: ColumnNullabilityRequest,
) -> Any:
    """
    Require a value in one column, or stop requiring one.

    Rows that already contradict the constraint are an answer rather than a
    failure: the source counts them and says how many, having changed nothing.
    Only a change invalidates what the connector cached.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(adapter, SupportsColumnNullability):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support changing nullability",
                "error_kind": "config",
            },
        )
    result = await _change_column_nullability(adapter, request)
    if isinstance(result, NullabilityChanged):
        await data_cache.invalidate_connector(connector_id)
    return result


async def _change_column_type(
    adapter: SupportsColumnType, request: ColumnTypeRequest
) -> ColumnTypeChangeResult:
    try:
        return await adapter.change_column_type(request)
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


@router.patch("/{connector_id}/columns/type", response_model=ColumnTypeChangeResult)
async def change_column_type(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: ColumnTypeRequest,
) -> Any:
    """
    Give one column another type from the source's published list.

    The conversion is written by the source; there is no field a cast is read
    from. Rows the new type cannot read are an answer with a count where the
    source can produce one, and only a change invalidates what it cached.
    """
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(adapter, SupportsColumnType):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support changing column types",
                "error_kind": "config",
            },
        )
    result = await _change_column_type(adapter, request)
    if isinstance(result, ColumnTypeChanged):
        await data_cache.invalidate_connector(connector_id)
    return result


async def _shape_change[T](adapter_call: Callable[[], Awaitable[T]]) -> T:
    """One reading of what an adapter can say about changing a shape."""
    try:
        return await adapter_call()
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


async def _indexing_adapter(
    session: SessionDep,
    connector_id: uuid.UUID,
    current_user: CurrentUser,
    resources: ResourcesDep,
) -> SupportsIndexes:
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(adapter, SupportsIndexes):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support changing indexes",
                "error_kind": "config",
            },
        )
    return adapter


@router.post("/{connector_id}/indexes", response_model=CreateIndexResult)
async def create_index(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: CreateIndexRequest,
) -> Any:
    """
    Index the named columns of one relation, in the order they are given.

    The source names the index; the request carries no name and no expression.
    Rows that already repeat under a unique index are an answer with a count,
    and only a created index invalidates what the connector cached.
    """
    adapter = await _indexing_adapter(session, connector_id, current_user, resources)
    result = await _shape_change(lambda: adapter.create_index(request))
    if isinstance(result, IndexCreated):
        await data_cache.invalidate_connector(connector_id)
    return result


@router.delete("/{connector_id}/indexes", response_model=IndexDropped)
async def drop_index(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: DropIndexRequest,
) -> IndexDropped:
    """Drop one index of a relation, without an implicit cascade."""
    adapter = await _indexing_adapter(session, connector_id, current_user, resources)
    return await _invalidate_after(
        lambda: _shape_change(lambda: adapter.drop_index(request)),
        data_cache,
        connector_id,
    )


async def _designing_adapter(
    session: SessionDep,
    connector_id: uuid.UUID,
    current_user: CurrentUser,
    resources: ResourcesDep,
) -> SupportsTableDesign:
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(adapter, SupportsTableDesign):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source cannot design a table",
                "error_kind": "config",
            },
        )
    return adapter


@router.post("/{connector_id}/table-design/options", response_model=TableDesignOptions)
async def table_design_options(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: TableDesignTarget,
) -> Any:
    """
    What one destination will accept a designed table with.

    The vocabulary of types, index methods, functions and operator classes,
    read from this server rather than written down by the editor: which of them
    exist depends on the version and on what is installed, and a table kept in
    the browser would be wrong within a release.
    """
    adapter = await _designing_adapter(session, connector_id, current_user, resources)
    return await _shape_change(lambda: adapter.table_design_options(request.node_id))


@router.post("/{connector_id}/table-design/plan", response_model=TablePlan)
async def plan_table(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: TablePlanRequest,
) -> Any:
    """
    The statements a definition would become, composed and not executed.

    Nothing is created and nothing is rolled back: this is a plan, not D46's
    rehearsal, because DDL that runs and is undone still takes locks. It needs
    the level the creation needs — the answer names objects of the schema, and
    a plan is how somebody decides whether to go ahead.

    A definition with problems is an answer rather than a refusal: which object
    is at fault is the useful part, and the editor shows every one of them at
    once.
    """
    adapter = await _designing_adapter(session, connector_id, current_user, resources)
    return await _shape_change(lambda: adapter.plan_table(request))


async def _constraining_adapter(
    session: SessionDep,
    connector_id: uuid.UUID,
    current_user: CurrentUser,
    resources: ResourcesDep,
) -> SupportsConstraints:
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="structure"
    )
    if not isinstance(adapter, SupportsConstraints):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support changing constraints",
                "error_kind": "config",
            },
        )
    return adapter


@router.post("/{connector_id}/constraints", response_model=CreateConstraintResult)
async def create_constraint(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: CreateConstraintRequest,
) -> Any:
    """
    Promise uniqueness over columns, or a reference to another relation.

    The source names the constraint, and rows that already contradict the
    promise are an answer with a count rather than a failure. Only a created
    constraint invalidates what the connector cached.
    """
    adapter = await _constraining_adapter(
        session, connector_id, current_user, resources
    )
    result = await _shape_change(lambda: adapter.create_constraint(request))
    if isinstance(result, ConstraintCreated):
        await data_cache.invalidate_connector(connector_id)
    return result


@router.delete("/{connector_id}/constraints", response_model=ConstraintDropped)
async def drop_constraint(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    request: DropConstraintRequest,
) -> ConstraintDropped:
    """Drop one constraint of a relation, without an implicit cascade."""
    adapter = await _constraining_adapter(
        session, connector_id, current_user, resources
    )
    return await _invalidate_after(
        lambda: _shape_change(lambda: adapter.drop_constraint(request)),
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
    adapter = await adapter_for(
        session, connector_id, current_user, resources, requires="read"
    )
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
    # The sentence the confirmation asks, when the action has one of its own.
    # Empty for everything that removes what it names, where the client's
    # wording names the node and is better for it.
    question: str | None = None
    # Derived from the action itself rather than declared beside it: a flag and
    # an implementation can disagree, an isinstance check cannot.
    takes_file: bool
    # Whether one filled form may be carried by several files, one request
    # each. Declared by the action rather than derived: both shapes use the
    # same route, and a client needs the answer to offer one picker or a
    # set.
    takes_many_files: bool
    # Whether it can be asked what it would do before it is done. Derived the
    # same way, and for the same reason.
    previews: bool
    # Whether a selection is carried out in one request rather than repeated
    # per node, and whether that one request can be previewed. Derived from
    # the capabilities, so what the API says cannot drift from what the action
    # does — and a client needs both to know which route to call.
    takes_set: bool
    previews_set: bool
    # Whether selecting this action produces bytes through the native browser
    # download transport. Derived from the callable action capability.
    downloads: bool
    prepares_connector: bool = False
    # What the action changes, so a client knows what to send it: selected
    # nodes, the places whose children are shown, or the level itself.
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


class DownloadActionTargets(BaseModel):
    """The non-empty selection one download action receives, and its form."""

    node_ids: Annotated[list[str], Field(min_length=1, max_length=1000)]
    params: dict[str, Any] = {}


class ActionRequest(BaseModel):
    node_id: str | None = None
    params: dict[str, Any] = {}


class ActionSetRequest(BaseModel):
    """One filled form and the whole selection it is about.

    A separate model rather than a second optional field on `ActionRequest`:
    the two are different requests — one names a node and the other a set —
    and a body where exactly one of two fields must be filled is a shape that
    has to be argued about at every call site.
    """

    node_ids: Annotated[list[str], Field(min_length=1, max_length=1000)]
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
        takes_many_files=action.many_files,
        previews=isinstance(action, Previews),
        takes_set=isinstance(action, TakesNodeSet),
        previews_set=isinstance(action, PreviewsSet),
        downloads=isinstance(action, ProducesDownload),
        prepares_connector=isinstance(action, PreparesConnector),
        acts_on=action.acts_on,
        applicable=applicable,
        question=action.question,
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
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
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


async def _action_for_nodes(
    adapter: SupportsActions, action_name: str, node_ids: list[str]
) -> Action[Any]:
    """One bulk action admitted by every selected node, checked together."""
    if len(set(node_ids)) != len(node_ids):
        raise HTTPException(
            status_code=422, detail={"message": "A node may be selected only once"}
        )
    action: Action[Any] | None = None
    for node_id in node_ids:
        action = await _action_for_node(adapter, action_name, node_id)
    if action is None:
        raise HTTPException(status_code=422, detail={"message": "Choose a node"})
    if len(node_ids) > 1 and not action.bulk:
        raise HTTPException(
            status_code=422,
            detail={"message": f"{action.title} cannot be done in bulk"},
        )
    return action


def _allowed_or_403(action: Action[Any], access: Access) -> None:
    """Whether this caller may run this action, asked after it resolved.

    A level cannot be checked at the door, because which one is needed is the
    action's own statement and the name has not been resolved yet. Answering
    404 for the name would be a different lie: the action exists.
    """
    if not at_least(access, action.requires):
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"{action.title} needs {action.requires} access",
                "required": action.requires,
                "held": access,
            },
        )


async def _perform[T](run: Callable[[], Awaitable[T]]) -> T:
    try:
        return await run()
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
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
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    acting = _acting_or_501(adapter)
    targets: list[str | None] = list(body.node_ids) if body.node_ids else [None]
    offers = [await _available_or_422(acting, node_id) for node_id in targets]
    admitted = {
        action.name for action in common_actions(offers, bulk_only=len(targets) > 1)
    }
    # Filtered rather than greyed out: an action the caller may not run is not
    # inapplicable here, it is not theirs, and saying so per action would put
    # the level rules into the menu as well as into the route.
    return [
        _describe(action, applicable=action.name in admitted)
        for action in acting.all_actions()
        if at_least(access, action.requires)
    ]


@router.post(
    "/{connector_id}/actions/{action_name}/connector-draft",
    response_model=ConnectorDraft,
)
async def prepare_connector_action(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionRequest,
) -> ConnectorDraft:
    """Prepare a new connector form without creating a connection or changing files."""
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await _action_for_node(
        _acting_or_501(adapter), action_name, body.node_id
    )
    _allowed_or_403(action, access)
    if not isinstance(action, PreparesConnector):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} does not prepare a connector"},
        )
    return await _perform(lambda: action.prepare_connector(body.node_id, body.params))


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
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await _action_for_node(
        _acting_or_501(adapter), action_name, body.node_id
    )
    _allowed_or_403(action, access)
    if not isinstance(action, TakesParams):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} uses a different request transport"},
        )
    return await _invalidate_after(
        lambda: _perform(lambda: action.perform(body.node_id, body.params)),
        data_cache,
        connector_id,
    )


@router.post(
    "/{connector_id}/actions/{action_name}/preview", response_model=ActionPreview
)
async def preview_action(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionRequest,
) -> Any:
    """
    What one action would do, without doing it.

    Asked again whenever the form changes, because the answer depends on the
    parameters — a cascade takes things with it that a plain drop does not.
    Nothing is written and nothing the connector cached is dropped: this is a
    question, and the source answers it in its own words.

    It needs the level the action itself needs. Reading what a drop would
    destroy is not a lesser thing than the drop for anyone deciding whether it
    is safe, and the answer names objects the caller may not otherwise see.
    """
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    target = body.node_id or None
    action = await _action_for_node(_acting_or_501(adapter), action_name, target)
    _allowed_or_403(action, access)
    if not isinstance(action, Previews):
        raise HTTPException(
            status_code=501,
            detail={
                "message": f"{action.title} cannot say what it would do first",
                "error_kind": "config",
            },
        )
    return await _perform(lambda: action.preview(target, body.params))


@router.post("/{connector_id}/actions/{action_name}/set", response_model=ActionResult)
async def run_action_on_set(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    data_cache: DataCacheDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionSetRequest,
) -> Any:
    """
    Perform one action on a whole selection, in one request.

    For an action whose answer is about the set rather than about each node in
    it: dropping three relations that depend on each other succeeds together
    and is refused apart. Every node is checked exactly as it is for a single
    request, and an action that does not take a set says so with 415 rather
    than quietly acting on the first of them.
    """
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await _action_for_nodes(
        _acting_or_501(adapter), action_name, body.node_ids
    )
    _allowed_or_403(action, access)
    if not isinstance(action, TakesNodeSet):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} is done to one node at a time"},
        )
    return await _invalidate_after(
        lambda: _perform(lambda: action.perform_on_set(body.node_ids, body.params)),
        data_cache,
        connector_id,
    )


@router.post(
    "/{connector_id}/actions/{action_name}/set/preview", response_model=ActionPreview
)
async def preview_action_on_set(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionSetRequest,
) -> Any:
    """
    Ask what one action would do to a whole selection, without doing it.
    """
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await _action_for_nodes(
        _acting_or_501(adapter), action_name, body.node_ids
    )
    _allowed_or_403(action, access)
    if not isinstance(action, PreviewsSet):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} cannot say what it would do"},
        )
    return await _perform(lambda: action.preview_on_set(body.node_ids, body.params))


@router.post(
    "/{connector_id}/actions/{action_name}/download",
    response_model=ActionDownloadReady,
)
async def prepare_action_download(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    action_name: str,
    body: DownloadActionTargets,
) -> ActionDownloadReady:
    """Issue a short-lived native-browser ticket for one download action."""
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    action = await _action_for_nodes(
        _acting_or_501(adapter), action_name, body.node_ids
    )
    _allowed_or_403(action, access)
    if not isinstance(action, ProducesDownload):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} does not produce a download"},
        )
    ticket = action_downloads.issue_action_download_ticket(
        user_id=current_user.id,
        connector_id=connector_id,
        action_name=action_name,
        node_ids=body.node_ids,
        params=body.params,
    )
    return ActionDownloadReady(
        download_url=action_downloads.action_download_url(ticket)
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
    adapter, access = await resolve_adapter(
        session, connector_id, current_user, resources, requires="read"
    )
    target = node_id or None
    action = await _action_for_node(_acting_or_501(adapter), action_name, target)
    _allowed_or_403(action, access)
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


@router.get("/{connector_id}/grants", response_model=GrantsPublic)
async def read_grants(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """Who else may reach this connection, and at what level.

    The owner's business alone. Somebody holding a grant sees that the
    connection is shared with them and not who else has it: that is a list of
    people, and it is not theirs to read.
    """
    await get_or_404(session, connector_id, current_user, requires="own")
    return GrantsPublic(
        data=[
            GrantPublic(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                access=access,
            )
            for user, access in await crud.list_grants(
                session, connector_id=connector_id
            )
        ]
    )


@router.put("/{connector_id}/grants", response_model=GrantPublic)
async def write_grant(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    body: GrantWrite,
) -> Any:
    """Give somebody a level on this connection, or change the one they have.

    One route for both because they are the same statement: this person's
    standing is now this. A client that had to know whether a grant already
    existed would race with another window of the same owner.
    """
    await get_or_404(session, connector_id, current_user, requires="own")
    if body.user_id == current_user.id:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "user_id"],
                    "msg": "You already own this connection",
                    "type": "value_error",
                }
            ],
        )
    user = await session.get(User, body.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "user_id"],
                    "msg": "No such user",
                    "type": "value_error",
                }
            ],
        )
    grant = await crud.set_grant(
        session,
        connector_id=connector_id,
        user_id=body.user_id,
        access=body.access,
    )
    return GrantPublic(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        access=grant.access,
    )


@router.delete("/{connector_id}/grants/{user_id}")
async def revoke_grant(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Message:
    """Take a level away.

    Nothing cached needs clearing: a cache entry is keyed by the caller who
    filled it, and the person who lost the grant can no longer reach a route
    that would read one.
    """
    await get_or_404(session, connector_id, current_user, requires="own")
    if not await crud.remove_grant(
        session, connector_id=connector_id, user_id=user_id
    ):
        raise HTTPException(status_code=404, detail="Grant not found")
    return Message(message="Access revoked")

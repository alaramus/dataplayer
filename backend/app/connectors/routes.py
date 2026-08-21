import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.actions import (
    Action,
    ActionRefused,
    ActionResult,
    RefusalReason,
    SupportsActions,
    TakesFile,
    TakesParams,
    UnknownAction,
)
from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import (
    AdapterError,
    ConnectionCheckResult,
    DataAdapter,
    SupportsCatalog,
    SupportsFetch,
)
from app.adapters.registry import AdapterContext, AdapterType, UnknownAdapterType
from app.adapters.registry import get as get_adapter_type
from app.connectors import crud, service
from app.connectors.models import (
    Connector,
    ConnectorCreate,
    ConnectorPublic,
    ConnectorsPublic,
    ConnectorUpdate,
)
from app.core.db import SessionDep
from app.core.schemas import Message, get_datetime_utc
from app.users import storage
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/connectors", tags=["connectors"])


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


def _context_for(owner_id: uuid.UUID) -> AdapterContext:
    """What the driver may reach, decided here rather than by the request."""
    return AdapterContext(home_dir=storage.home_dir(owner_id))


async def _adapter_for(
    session: AsyncSession, connector_id: uuid.UUID, current_user: User
) -> DataAdapter:
    """Resolve a stored connector into a live adapter."""
    connector = await _get_or_404(session, connector_id, current_user)
    adapter_type = _resolve_type(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    return service.build_adapter(
        adapter_type, options, _context_for(connector.owner_id)
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
    connector_id: uuid.UUID,
    connector_in: ConnectorUpdate,
) -> Any:
    """
    Update a connector.
    """
    connector = await _get_or_404(session, connector_id, current_user)

    if connector_in.name is not None:
        connector.name = connector_in.name

    if connector_in.options is not None:
        adapter_type = _resolve_type(connector.adapter_type)
        options = service.fill_missing_secrets(
            adapter_type, connector_in.options, connector.secrets
        )
        connector.config, connector.secrets = _split_or_422(adapter_type, options)

    connector.updated_at = get_datetime_utc()
    return await crud.save(session, connector=connector)


@router.delete("/{connector_id}")
async def delete_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Message:
    """
    Delete a connector.
    """
    connector = await _get_or_404(session, connector_id, current_user)
    await crud.delete(session, connector=connector)
    return Message(message="Connector deleted successfully")


class ConnectionCheckRequest(BaseModel):
    adapter_type: str
    options: dict[str, Any]
    connector_id: uuid.UUID | None = None


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
    adapter_type = _resolve_type(body.adapter_type)
    options = body.options
    if body.connector_id is not None:
        connector = await _get_or_404(session, body.connector_id, current_user)
        options = service.fill_missing_secrets(adapter_type, options, connector.secrets)

    try:
        adapter = service.build_adapter(
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
    return await adapter.check_connection()


@router.post("/{connector_id}/check", response_model=ConnectionCheckResult)
async def check_connector(
    session: SessionDep, current_user: CurrentUser, connector_id: uuid.UUID
) -> Any:
    """
    Check the connection of a stored connector.
    """
    adapter = await _adapter_for(session, connector_id, current_user)
    return await adapter.check_connection()


@router.post("/{connector_id}/fetch", response_model=FetchResult)
async def fetch_rows(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    request: FetchRequest,
) -> Any:
    """
    Read a page of rows from a relation named by request.node_id.
    """
    adapter = await _adapter_for(session, connector_id, current_user)
    if not isinstance(adapter, SupportsFetch):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not support reading rows",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.fetch(request)
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
    connector_id: uuid.UUID,
    node_id: str | None = None,
) -> Any:
    """
    List the children of a catalog node, or the root when node_id is omitted.

    node_id is opaque: only the adapter that produced it knows how to read it.
    """
    adapter = await _adapter_for(session, connector_id, current_user)
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
        return await adapter.list_children(node_id)
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


class ActionInfo(BaseModel):
    """One action, as much as a client needs to offer and perform it."""

    name: str
    title: str
    destructive: bool
    # Derived from the action itself rather than declared beside it: a flag and
    # an implementation can disagree, an isinstance check cannot.
    takes_file: bool
    params_schema: dict[str, Any]


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


def _describe(action: Action[Any]) -> ActionInfo:
    return ActionInfo(
        name=action.name,
        title=action.title,
        destructive=action.destructive,
        takes_file=isinstance(action, TakesFile),
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


@router.get("/{connector_id}/actions", response_model=list[ActionInfo])
async def read_actions(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    node_id: str | None = None,
) -> Any:
    """
    List the actions this node admits, with the schema of their parameters.

    Asked per node rather than per source type: whether a node may be renamed
    depends on its state as well as its kind — the root of a connector is an
    ordinary directory that may not be removed.
    """
    adapter = _acting_or_501(await _adapter_for(session, connector_id, current_user))
    return [_describe(action) for action in await _available_or_422(adapter, node_id)]


@router.post("/{connector_id}/actions/{action_name}", response_model=ActionResult)
async def run_action(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
    action_name: str,
    body: ActionRequest,
) -> Any:
    """
    Perform an action that needs nothing but its parameters.
    """
    adapter = _acting_or_501(await _adapter_for(session, connector_id, current_user))
    action = await _action_for_node(adapter, action_name, body.node_id)
    if not isinstance(action, TakesParams):
        raise HTTPException(
            status_code=415,
            detail={"message": f"{action.title} needs a file to be sent with it"},
        )
    return await _perform(lambda: action.perform(body.node_id, body.params))


@router.post("/{connector_id}/actions/{action_name}/file", response_model=ActionResult)
async def run_action_with_file(
    session: SessionDep,
    current_user: CurrentUser,
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
    adapter = _acting_or_501(await _adapter_for(session, connector_id, current_user))
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

    return await _perform(lambda: action.perform_with_file(target, given, file))

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterType, UnknownAdapterType
from app.adapters.registry import get as get_adapter_type
from app.api.deps import CurrentUser, SessionDep
from app.connectors import crud, service
from app.connectors.models import (
    Connector,
    ConnectorCreate,
    ConnectorPublic,
    ConnectorsPublic,
    ConnectorUpdate,
)
from app.models import Message, User, get_datetime_utc

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
        adapter = service.build_adapter(adapter_type, options)
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
    connector = await _get_or_404(session, connector_id, current_user)
    adapter_type = _resolve_type(connector.adapter_type)
    options = service.merge_options(connector.config, connector.secrets)
    adapter = service.build_adapter(adapter_type, options)
    return await adapter.check_connection()

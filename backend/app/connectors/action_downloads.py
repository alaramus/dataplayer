"""Short-lived authority for a source-declared download action."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import security
from app.core.config import settings

ACTION_DOWNLOAD_TICKET_SECONDS = 60


class ActionDownloadClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["action_download"] = "action_download"
    user_id: uuid.UUID
    connector_id: uuid.UUID
    action_name: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=1, max_length=1000)
    # The filled form, carried in the signed ticket rather than in the URL a
    # browser follows: the ticket is the authority for this one invocation,
    # and what was chosen is part of what was authorised.
    params: dict[str, Any] = Field(default_factory=dict)
    exp: int


def issue_action_download_ticket(
    *,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    action_name: str,
    node_ids: list[str],
    params: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = ActionDownloadClaims(
        user_id=user_id,
        connector_id=connector_id,
        action_name=action_name,
        node_ids=node_ids,
        params=params or {},
        exp=int(issued_at.timestamp()) + ACTION_DOWNLOAD_TICKET_SECONDS,
    )
    return jwt.encode(
        claims.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def read_action_download_ticket(ticket: str) -> ActionDownloadClaims | None:
    try:
        payload = jwt.decode(
            ticket, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        claims = ActionDownloadClaims.model_validate(payload)
        return claims if claims.purpose == "action_download" else None
    except (InvalidTokenError, ValidationError):
        return None


def action_download_url(ticket: str) -> str:
    return f"{settings.API_V1_STR}/connectors/action-downloads/{ticket}"

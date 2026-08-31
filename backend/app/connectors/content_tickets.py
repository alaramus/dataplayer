"""Short-lived authority for inline content-preview byte responses."""

import uuid
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote

import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core import security
from app.core.config import settings

CONTENT_TICKET_SECONDS = 60


class _TicketBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    connector_id: uuid.UUID
    node_id: str
    exp: int


class ImagePreviewClaims(_TicketBase):
    purpose: Literal["image_preview"]
    representation: Literal["image"]


def issue_content_ticket(
    *,
    purpose: Literal["image_preview"],
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    node_id: str,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    expires = int(issued_at.timestamp()) + CONTENT_TICKET_SECONDS
    claims = ImagePreviewClaims(
        purpose=purpose,
        representation="image",
        user_id=user_id,
        connector_id=connector_id,
        node_id=node_id,
        exp=expires,
    )
    return jwt.encode(
        claims.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def read_content_ticket(ticket: str) -> ImagePreviewClaims | None:
    try:
        payload = jwt.decode(
            ticket, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return ImagePreviewClaims.model_validate(payload)
    except (InvalidTokenError, ValidationError):
        return None


def content_ticket_url(ticket: str) -> str:
    return f"{settings.API_V1_STR}/connectors/content-files/{ticket}"


def content_disposition(filename: str, *, inline: bool) -> str:
    """A header-safe fallback plus the exact UTF-8 source filename."""
    cleaned = "".join(
        character
        if 32 <= ord(character) < 127 and character not in {'"', "\\"}
        else "_"
        for character in filename
    ).strip()
    fallback = cleaned or "download"
    kind = "inline" if inline else "attachment"
    return (
        f"{kind}; filename=\"{fallback}\"; "
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )

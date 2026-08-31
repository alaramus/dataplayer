"""Short-lived authority for inline content-preview byte responses."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import quote

import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.adapters.content import StreamableRepresentationKind
from app.core import security
from app.core.config import settings

CONTENT_TICKET_SECONDS = 60

# A stream lives as long as the thing it carries is being watched or read: a
# preview is fetched once and at once, while a recording is played, paused and
# seeked over its own length, and every seek is a new request for the same URL.
# The ticket is authority to ask, not a copy of the bytes — each redemption
# re-checks the user, the connection, the access level and the node.
CONTENT_STREAM_SECONDS = 60 * 60


class _TicketBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    connector_id: uuid.UUID
    node_id: str
    exp: int


class ImagePreviewClaims(_TicketBase):
    purpose: Literal["image_preview"]
    representation: Literal["image"]


class ContentStreamClaims(_TicketBase):
    """Authority for one ranged representation of one node.

    The representation is in the ticket, so one minted for a sound file cannot
    be redeemed for a recording or a document (D52).
    """

    purpose: Literal["content_stream"]
    representation: StreamableRepresentationKind


ContentTicketClaims = Annotated[
    ImagePreviewClaims | ContentStreamClaims,
    Field(discriminator="purpose"),
]
_CLAIMS: TypeAdapter[ImagePreviewClaims | ContentStreamClaims] = TypeAdapter(
    ContentTicketClaims
)


def issue_content_ticket(
    *,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    node_id: str,
    now: datetime | None = None,
) -> str:
    """A ticket for the bounded image preview of D49."""
    return _encode(
        ImagePreviewClaims(
            purpose="image_preview",
            representation="image",
            user_id=user_id,
            connector_id=connector_id,
            node_id=node_id,
            exp=_expiry(now),
        )
    )


def issue_stream_ticket(
    *,
    representation: StreamableRepresentationKind,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    node_id: str,
    now: datetime | None = None,
) -> str:
    """A ticket for the ranged byte route of D52."""
    return _encode(
        ContentStreamClaims(
            purpose="content_stream",
            representation=representation,
            user_id=user_id,
            connector_id=connector_id,
            node_id=node_id,
            exp=_expiry(now, CONTENT_STREAM_SECONDS),
        )
    )


def _expiry(now: datetime | None, seconds: int = CONTENT_TICKET_SECONDS) -> int:
    issued_at = now or datetime.now(UTC)
    return int(issued_at.timestamp()) + seconds


def _encode(claims: ImagePreviewClaims | ContentStreamClaims) -> str:
    return jwt.encode(
        claims.model_dump(mode="json"),
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )


def read_content_ticket(ticket: str) -> ImagePreviewClaims | ContentStreamClaims | None:
    try:
        payload = jwt.decode(
            ticket, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        claims: ImagePreviewClaims | ContentStreamClaims = _CLAIMS.validate_python(
            payload
        )
        return claims
    except (InvalidTokenError, ValidationError):
        return None


def content_ticket_url(ticket: str) -> str:
    return f"{settings.API_V1_STR}/connectors/content-files/{ticket}"


def content_stream_url(ticket: str) -> str:
    return f"{settings.API_V1_STR}/connectors/content-streams/{ticket}"


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

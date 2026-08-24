"""What may travel over the socket, in both directions.

Every frame is a model with ``extra="forbid"`` and the direction is a
discriminated union, so a frame the server does not understand fails to
validate rather than being half-read. The same reasoning as for ``CatalogNode``:
a forgotten case has to fail loudly.

Nothing here names a topic. The transport carries frames for topics it has
never heard of.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bumped when a frame changes shape in a way an older client cannot read. The
# client is told the number on connect, so it can refuse rather than
# misinterpret.
WS_PROTOCOL_VERSION = 1

ErrorCode = Literal[
    # The frame did not validate: unknown type, missing field, extra key.
    "malformed",
    # Anything but `auth` arrived before the socket said who it was.
    "unauthenticated",
    # A second `auth` on a socket that already has an identity.
    "already_authenticated",
    # No topic is registered under that name.
    "unknown_topic",
]


class _ClientFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WsAuth(_ClientFrame):
    """Present the token. Nothing is served until this arrives.

    A browser cannot set a header on the WebSocket handshake, and a token in
    the query string is written into every access log, into browser history
    and into the Referer of anything the page loads afterwards.
    """

    type: Literal["auth"]
    token: str


class WsSubscribe(_ClientFrame):
    type: Literal["subscribe"]
    topic: str


class WsUnsubscribe(_ClientFrame):
    type: Literal["unsubscribe"]
    topic: str


ClientFrame = Annotated[
    WsAuth | WsSubscribe | WsUnsubscribe, Field(discriminator="type")
]


class WsReady(BaseModel):
    """First frame the server sends, and only once the token checked out."""

    type: Literal["ready"] = "ready"
    protocol: int = WS_PROTOCOL_VERSION


class WsEvent[T: BaseModel](BaseModel):
    """Something a topic has to say. The payload is the topic's own model."""

    type: Literal["event"] = "event"
    topic: str
    payload: T


class WsError(BaseModel):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str

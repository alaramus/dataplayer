"""What a terminal's socket says in text (D148).

Keystrokes and output travel as binary frames and are not modelled: they are
bytes, and wrapping each in JSON would cost a base64 of every character typed.
Text frames are the few things that are not the shell's — who is opening it,
the size of the window, why it will not open, and that it has ended.

Written out again in `frontend/src/features/terminals/frames.ts`, for the
reason `app/realtime/messages.py` gives: OpenAPI has no WebSocket channel.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.protocol import ErrorKind
from app.adapters.terminal import MAX_COLUMNS, MAX_ROWS


class _ClientFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TerminalOpen(_ClientFrame):
    """Who is asking, for which connection, at what size. The first frame.

    The token travels here rather than in the address for the reason the
    application's socket gives (D18): an address is written into access logs
    and browser history.
    """

    type: Literal["open"]
    token: str
    connector_id: uuid.UUID
    cols: int = Field(ge=1, le=MAX_COLUMNS)
    rows: int = Field(ge=1, le=MAX_ROWS)


class TerminalResize(_ClientFrame):
    type: Literal["resize"]
    cols: int = Field(ge=1, le=MAX_COLUMNS)
    rows: int = Field(ge=1, le=MAX_ROWS)


# Only the first frame is an `open`; every text frame after it is a resize.
# A union all the same, so a second `open` fails to validate as one rather
# than being taken for something else.
ClientFrame = Annotated[TerminalOpen | TerminalResize, Field(discriminator="type")]

RefusalCode = Literal[
    # No `open` in time, or a token that is nobody's.
    "unauthenticated",
    # The first frame was not an `open` that validates.
    "malformed",
    # No such connection, or none this person can see.
    "not_found",
    # A connection somebody shared with this person: a terminal is its
    # owner's alone (D149).
    "forbidden",
    # Switched off by its owner.
    "disabled",
    # A source that has no shell to give.
    "unsupported",
    # As many terminals open as one person may hold.
    "too_many",
    # The source itself said no: `error_kind` says in what way.
    "source",
]


class TerminalReady(BaseModel):
    """The shell is running; binary frames flow both ways from here on."""

    type: Literal["ready"] = "ready"


class TerminalRefused(BaseModel):
    """Why no shell was opened. The socket closes straight after."""

    type: Literal["refused"] = "refused"
    code: RefusalCode
    message: str
    error_kind: ErrorKind | None = None


class TerminalEnded(BaseModel):
    """The shell is over. The socket closes straight after."""

    type: Literal["ended"] = "ended"
    exit_status: int | None = None


class TerminalError(BaseModel):
    """A text frame after `ready` that was not understood. Nothing closes."""

    type: Literal["error"] = "error"
    message: str

"""A terminal: one socket carrying one shell, for as long as both last (D148).

The socket opens unauthenticated, as the application's own does (D18), and
its first frame says who is asking and for which connection. Everything after
`ready` is the shell's: binary frames of keystrokes one way and of output the
other, and a text frame now and then to say the window changed size.

Nothing outlives the socket. A page that closes or loses its connection takes
the shell with it, and a new socket is a new shell (D149).
"""

import asyncio
import logging
from contextlib import AsyncExitStack, suppress

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, TypeAdapter, ValidationError

from app.adapters.protocol import AdapterError, ErrorKind
from app.adapters.terminal import (
    SupportsConsoleProgram,
    SupportsTerminal,
    Terminal,
    TerminalSize,
)
from app.connectors.access import adapter_for
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.translation import N_, say
from app.terminals.consoles import ConsoleRefused, ConsoleRunner
from app.terminals.messages import (
    ClientFrame,
    RefusalCode,
    TerminalEnded,
    TerminalError,
    TerminalOpen,
    TerminalReady,
    TerminalRefused,
    TerminalResize,
)
from app.terminals.slots import SLOTS, TooManyTerminals
from app.users.deps import user_for_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["terminals"])

_frames: TypeAdapter[ClientFrame] = TypeAdapter(ClientFrame)

# Close codes: "policy violation" for a socket that never said who it was or
# said it in a frame that does not validate, as the application's socket
# answers; "normal" for everything the client was told about in a frame.
_POLICY = 1008
_NORMAL = 1000

# What sending to a client that has already gone raises: the disconnect when
# the server noticed, the runtime error when the socket was already closed.
_GONE = (WebSocketDisconnect, RuntimeError)

# What each refusal of the access check (D33) is to a terminal.
_REFUSALS_BY_STATUS: dict[int, tuple[RefusalCode, str]] = {
    404: ("not_found", N_("No such connection")),
    403: ("forbidden", N_("A terminal opens only on a connection of your own")),
    409: ("disabled", N_("This connection is switched off")),
    422: ("unsupported", N_("This kind of connection has no terminal")),
}
_ANY_OTHER_REFUSAL: tuple[RefusalCode, str] = ("source", N_("The connection could not be opened"))


class _Refusal(Exception):
    def __init__(
        self, code: RefusalCode, message: str, error_kind: ErrorKind | None = None
    ) -> None:
        super().__init__(message)
        self.frame = TerminalRefused(code=code, message=message, error_kind=error_kind)


class _Sender:
    """Output and the odd notice are sent from two tasks; one frame at a time."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()

    async def text(self, frame: BaseModel) -> None:
        async with self._lock:
            await self._websocket.send_text(frame.model_dump_json())

    async def binary(self, data: bytes) -> None:
        async with self._lock:
            await self._websocket.send_bytes(data)


@router.websocket("/terminals")
async def terminal_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    sender = _Sender(websocket)
    async with AsyncExitStack() as held:
        try:
            terminal = await _opened(websocket, held)
        except _Refusal as refusal:
            policy = refusal.frame.code in ("unauthenticated", "malformed")
            with suppress(*_GONE):
                await sender.text(refusal.frame)
                await websocket.close(code=_POLICY if policy else _NORMAL)
            return
        except WebSocketDisconnect:
            return

        try:
            await sender.text(TerminalReady())
        except _GONE:
            return
        if await _relay(websocket, sender, terminal):
            status = await terminal.exit_status()
            with suppress(*_GONE):
                await sender.text(TerminalEnded(exit_status=status))
                await websocket.close(code=_NORMAL)


async def _opened(websocket: WebSocket, held: AsyncExitStack) -> Terminal:
    """A running shell, closed and counted by `held`, or the reason for none."""
    opening = await _opening(websocket)
    async with async_session_maker() as session:
        user = await user_for_token(session, opening.token)
        if user is None:
            raise _Refusal("unauthenticated", say("Sign in again to open a terminal"))
        try:
            # `own`: a terminal types into the server as the account the
            # connection signs in as, which is more than any grant gives (D149).
            adapter = await adapter_for(
                session, opening.connector_id, user, requires="own"
            )
        except HTTPException as refusal:
            code, message = _REFUSALS_BY_STATUS.get(refusal.status_code, _ANY_OTHER_REFUSAL)
            raise _Refusal(code, say(message)) from None
        except (ValueError, ValidationError):
            raise _Refusal("source", say("The settings of this connection are not valid")) from None

    if not isinstance(adapter, SupportsTerminal | SupportsConsoleProgram):
        raise _Refusal("unsupported", say("This kind of connection has no terminal"))
    try:
        held.enter_context(SLOTS.taken(user.id))
    except TooManyTerminals:
        raise _Refusal(
            "too_many",
            say("You have {count} terminals open already; close one first", count=SLOTS.limit),
        ) from None
    size = TerminalSize(cols=opening.cols, rows=opening.rows)
    try:
        if isinstance(adapter, SupportsTerminal):
            terminal = await adapter.open_terminal(size)
        else:
            runner = getattr(websocket.app.state, "console_runner", None)
            if not isinstance(runner, ConsoleRunner):
                raise _Refusal("unsupported", say("This server cannot start a console"))
            terminal = await runner.open_console(
                await adapter.console_program(), size, owner=user.id
            )
    except AdapterError as failure:
        raise _Refusal("source", failure.message, failure.error_kind) from None
    except ConsoleRefused as refusal:
        raise _Refusal("source", refusal.message) from None
    held.push_async_callback(terminal.close)
    return terminal


async def _opening(websocket: WebSocket) -> TerminalOpen:
    """The first frame, which must be an `open`, within the time a socket gets.

    A socket that says nothing holds a connection for as long as it likes, so
    the wait has the ceiling the application's socket has.
    """
    try:
        async with asyncio.timeout(settings.WS_AUTH_TIMEOUT_SECONDS):
            message = await websocket.receive()
    except TimeoutError:
        raise _Refusal("unauthenticated", say("Say who you are first")) from None
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(code=message.get("code", _NORMAL))
    text = message.get("text")
    try:
        frame = _frames.validate_json(text if isinstance(text, str) else "")
    except ValidationError:
        raise _Refusal("malformed", say("The first frame opens a terminal")) from None
    if not isinstance(frame, TerminalOpen):
        raise _Refusal("malformed", say("The first frame opens a terminal"))
    return frame


async def _relay(websocket: WebSocket, sender: _Sender, terminal: Terminal) -> bool:
    """Carry bytes both ways until one side stops. True when the shell did."""
    output = asyncio.create_task(_output(sender, terminal))
    typing = asyncio.create_task(_typing(websocket, sender, terminal))
    try:
        done, _ = await asyncio.wait(
            {output, typing}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        # Also when this is cancelled itself, on shutdown: a task left behind
        # would go on reading a shell nobody is watching.
        for task in (output, typing):
            task.cancel()
        await asyncio.gather(output, typing, return_exceptions=True)
    for task in done:
        failure = task.exception()
        # A client gone mid-send is the usual way a terminal ends; anything
        # else is worth a line in the log, never a word to the client.
        if failure is not None and not isinstance(failure, WebSocketDisconnect):
            logger.warning("Terminal relay stopped: %r", failure)
    return output in done and output.exception() is None


async def _output(sender: _Sender, terminal: Terminal) -> None:
    while data := await terminal.read():
        await sender.binary(data)


async def _typing(websocket: WebSocket, sender: _Sender, terminal: Terminal) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        data = message.get("bytes")
        if isinstance(data, bytes):
            await terminal.write(data)
            continue
        text = message.get("text")
        if not isinstance(text, str):
            continue
        try:
            frame = _frames.validate_json(text)
        except ValidationError:
            await sender.text(TerminalError(message=say("Frame not understood")))
            continue
        if isinstance(frame, TerminalResize):
            terminal.resize(TerminalSize(cols=frame.cols, rows=frame.rows))
        else:
            await sender.text(TerminalError(message=say("This terminal is already open")))


"""A failure nobody caught, written down whole and answered with a ref (D184)."""

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logs import current_request, record_failure, with_ref

logger = logging.getLogger(__name__)

FAILED = "Something went wrong on the server"


class RecordFailures:
    """Names the request in everything logged while it is answered, and answers
    an exception that reached it with a sentence and a ref instead of a bare 500.

    Inside the CORS middleware, so the answer carries its headers: Starlette's
    own 500 did not, and a browser reported it as a network failure.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "WEBSOCKET")
        token = current_request.set(f"{method} {scope['path']}")
        started = False

        async def watched(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, watched)
        except Exception as failure:
            ref = record_failure(logger, "A request failed", failure)
            # Half an answer cannot be taken back; the server closes it.
            if scope["type"] != "http" or started:
                raise
            response = JSONResponse(
                {"detail": {"message": with_ref(FAILED, ref), "ref": ref}},
                status_code=500,
            )
            await response(scope, receive, send)
        finally:
            current_request.reset(token)

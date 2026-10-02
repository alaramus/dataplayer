"""What the application writes down about itself, where, and what never gets there (D184).

Every process calls `configure` once at start. Standard output keeps the text
it always had; with `LOG_DIR` set, each process also writes a file of JSON
lines, rotated by size, which the log panel reads. Everything written to either
passes `redact` first.
"""

import json
import logging
import logging.config
import re
import secrets
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Literal

from app.core.config import settings

ProcessName = Literal["backend", "metrics"]
PROCESSES: tuple[ProcessName, ...] = ("backend", "metrics")

# The request being answered, as its method and path, written beside anything
# logged meanwhile. Set by `RecordFailures`; the query string is left out,
# because a download ticket travels in it.
current_request: ContextVar[str | None] = ContextVar("current_request", default=None)

# Requests nobody made by hand, left out of the log: Docker asks for the health
# check every ten seconds, and the log panel reads the log every three while it
# follows it. Written down, they buried everything else.
ROUTINE_PATHS = (
    f"{settings.API_V1_STR}/utils/health-check/",
    f"{settings.API_V1_STR}/logs/",
)

# A key whose value is a secret, spelled as a DSN, an environment line, a query
# string or JSON spells it: `password=x`, `ticket=x`, `"api_key": "x"`.
_SECRET_KEY = r"[a-z_]*(?:password|passwd|pwd|secret|token|ticket|api_?key)"
_SECRETS: tuple[tuple[re.Pattern[str], str], ...] = (
    # user:password@ in any address.
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s/@:]*:)[^\s/@]+@"), r"\1***@"),
    (
        re.compile(rf"(?i)\b({_SECRET_KEY})([\"']?\s*[=:]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s&,;'\"}}]+)"),
        r"\1\2***",
    ),
    (re.compile(r"(?i)\b(bearer\s+)[a-z0-9._~+/=-]+"), r"\1***"),
)

# Letters and digits nobody misreads when a person reads a ref out loud.
_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def redact(text: str) -> str:
    """The text with every secret it spells replaced by `***`.

    Driver messages carry a connection string with its password, and a URL
    written to the access log carries a download ticket: neither is kept.
    """
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def new_ref() -> str:
    """Six characters naming one failure in the log and on the screen."""
    return "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))


def with_ref(message: str, ref: str) -> str:
    """The sentence a person is shown, carrying where to find the rest."""
    return f"{message} · ref {ref}"


def record_failure(
    logger: logging.Logger, what: str, failure: BaseException, *, private: bool = False
) -> str:
    """Write an unexpected failure down, and answer the ref to show with it.

    Private leaves the failure's own text out and keeps its type and where it
    was raised: a model provider's words may carry the conversation, and a
    driver's the statement somebody ran.
    """
    ref = new_ref()
    if private:
        frames = "".join(traceback.format_tb(failure.__traceback__))
        logger.error(
            "%s: %s\n%s", what, type(failure).__qualname__, frames.rstrip(), extra={"ref": ref}
        )
    else:
        logger.error("%s", what, exc_info=failure, extra={"ref": ref})
    return ref


def _ref_of(record: logging.LogRecord) -> str | None:
    ref = getattr(record, "ref", None)
    return ref if isinstance(ref, str) else None


class JsonLines(logging.Formatter):
    """One JSON object per line: what the log panel reads back."""

    def __init__(self, process: ProcessName) -> None:
        super().__init__()
        self._process = process

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="microseconds"
            ),
            "process": self._process,
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        ref = _ref_of(record)
        if ref is not None:
            entry["ref"] = ref
        request = current_request.get()
        if request is not None:
            entry["request"] = request
        if record.exc_info:
            entry["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False)


class RedactedText(logging.Formatter):
    """The text standard output always had, with secrets masked and the ref added."""

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802 - the stdlib's name
        text = super().formatMessage(record)
        ref = _ref_of(record)
        if ref is None:
            return text
        # On the first line, where a person scanning the output looks.
        first, newline, rest = text.partition("\n")
        return with_ref(first, ref) + newline + rest

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class SkipRoutineReads(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        line = record.getMessage()
        return not any(f" {path}" in line for path in ROUTINE_PATHS)


class DropQueryStrings(logging.Filter):
    """An access line names the path and never what follows the `?`.

    The words of a search travel there, and they are neither stored nor logged
    (D63); so does a download ticket. The request context already leaves
    the query string out, and this is the same rule for uvicorn's own line.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        # uvicorn's arguments: client, method, path with its query, version,
        # status. Anything else is left as it came.
        arguments = record.args
        if isinstance(arguments, tuple) and len(arguments) >= 3:
            path = arguments[2]
            if isinstance(path, str) and "?" in path:
                record.args = (*arguments[:2], path.partition("?")[0], *arguments[3:])
        return True


def configure(process: ProcessName) -> None:
    """Send every logger, the server's own included, through the two handlers."""
    handlers: dict[str, dict[str, Any]] = {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "text",
            "filters": ["routine", "query"],
        },
    }
    if settings.LOG_DIR is not None:
        settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(settings.LOG_DIR / f"{process}.log"),
            "maxBytes": settings.LOG_FILE_MAX_BYTES,
            "backupCount": settings.LOG_FILE_COUNT - 1,
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["routine", "query"],
        }
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "routine": {"()": SkipRoutineReads},
            "query": {"()": DropQueryStrings},
        },
        "formatters": {
            "text": {"()": RedactedText, "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s"},
            "json": {"()": JsonLines, "process": process},
        },
        "handlers": handlers,
        "root": {"level": "INFO", "handlers": list(handlers)},
        # The server configured these before the application was imported; their
        # own handlers go, and what they say reaches the file through the root.
        "loggers": {
            name: {"level": "INFO", "handlers": [], "propagate": True}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        },
    })

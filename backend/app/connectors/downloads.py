"""CSV made from what a grid is showing: handed to the browser, or kept.

Two destinations and not one. A download used to do both at once — the file
went to the browser and a copy stayed in personal storage — and a person who
wanted one of the two got the other as litter. So the caller says which is
meant, and only one of them happens.

Keeping is the simple half: the file is written under `downloads/` in the
user's own directory and stays there. Handing it over is the half with a
complication — a bounded page fits in a response, while a whole-relation
export is streamed to a file first, because a native browser download is what
keeps ten million rows out of the browser's memory (D28). That file is written
outside personal storage and removed as soon as it has been sent.
"""

import csv
import io
import shutil
import tempfile
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import jwt
from anyio import AsyncFile, open_file, to_thread
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchResult
from app.core import security
from app.core.config import settings

# SQL NULL is an empty unquoted field and every other value is quoted, so the
# empty string stays distinguishable from the absence of one. This is the
# convention PostgreSQL's own COPY ... CSV writes and reads back; a sentinel
# such as \N would collide with a value that happens to equal it.
NULL_QUOTING: Final = csv.QUOTE_NOTNULL
EXPORT_TICKET_SECONDS: Final = 60

# The mark on the temporary directory an export is streamed into when nobody
# asked to keep it. Named so that the redemption route can tell a file it made
# from any other path a signed claim might name.
SCRATCH_PREFIX: Final = "dataplayer-export-"

# What Excel needs at the start of a UTF-8 file to read it as UTF-8.
BYTE_ORDER_MARK: Final = b"\xef\xbb\xbf"


class ExportDownloadRequest(ExportRequest):
    """A whole-row export plus the human title of the open table."""

    title: str = Field(min_length=1, max_length=255)


class ExportReady(BaseModel):
    filename: str
    row_count: int
    download_url: str


class KeptDownload(BaseModel):
    """A copy that stayed: what it is called and how much of it there is.

    No URL, deliberately. Keeping a file and handing it to the browser are the
    two things this module was asked to stop doing at once, and an address in
    the answer would be an invitation to do both again.
    """

    filename: str
    row_count: int


class ExportTicketClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["export_download"]
    user_id: uuid.UUID
    connector_id: uuid.UUID
    filename: str
    exp: int
    # The temporary directory the file is in, when it was made only to be
    # handed over. Absent for one that was kept, which lives in the user's own
    # directory and is found from `user_id` instead.
    scratch: str | None = None


def safe_stem(title: str) -> str:
    stem = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in title.strip()
    ).strip("._-")
    return stem[:120] or "table"


def _csv_paths(
    *,
    home: Path,
    connector_id: uuid.UUID,
    title: str,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    downloaded_at = now or datetime.now(UTC)
    filename = f"{safe_stem(title)}-{downloaded_at:%Y%m%d-%H%M%S-%f}.csv"
    downloads = home / "downloads"
    directory = downloads / str(connector_id)
    if home.is_symlink() or downloads.is_symlink() or directory.is_symlink():
        raise ValueError("The downloads directory is not safe")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        directory.resolve().relative_to(home.resolve(strict=True))
    except (OSError, ValueError):
        raise ValueError("The downloads directory is not safe") from None
    destination = directory / filename
    return destination, destination.with_suffix(".csv.part")


def page_csv(*, columns: list[str], result: FetchResult) -> bytes:
    """One fetched page as the bytes of a CSV file.

    ``columns`` comes from the controlled grid layout. It is checked against
    the fresh adapter answer before any row is written, so a stale layout can
    never shift a value under the wrong heading.

    Bytes rather than a file, because a page is bounded by the limit that
    fetched it: what is kept and what is handed over are then the same
    document written to two places, rather than two ways of writing it.
    """
    available = {column.name: index for index, column in enumerate(result.columns)}
    if len(columns) != len(set(columns)):
        raise ValueError("Download columns must be unique")
    unknown = [column for column in columns if column not in available]
    if unknown:
        raise ValueError(f"Unknown download column: {unknown[0]}")

    indexes = [available[column] for column in columns]
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=NULL_QUOTING)
    writer.writerow(columns)
    for row in result.rows:
        writer.writerow(row[index] for index in indexes)
    return BYTE_ORDER_MARK + output.getvalue().encode("utf-8")


def page_filename(title: str, now: datetime | None = None) -> str:
    """What a page is called wherever it lands."""
    stamped = now or datetime.now(UTC)
    return f"{safe_stem(title)}-{stamped:%Y%m%d-%H%M%S-%f}.csv"


def save_csv_page(
    *,
    home: Path,
    connector_id: uuid.UUID,
    title: str,
    columns: list[str],
    result: FetchResult,
    now: datetime | None = None,
) -> Path:
    """Write one fetched page atomically into personal storage."""
    body = page_csv(columns=columns, result=result)
    destination, temporary = _csv_paths(
        home=home, connector_id=connector_id, title=title, now=now
    )
    try:
        temporary.write_bytes(body)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _encode_csv_rows(rows: list[list[str | None]]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, quoting=NULL_QUOTING).writerows(rows)
    return output.getvalue().encode("utf-8")


def _scratch_paths(*, title: str, now: datetime | None = None) -> tuple[Path, Path]:
    """A file outside personal storage, in a directory of its own.

    Its own directory so that redeeming the ticket can take the whole thing
    away without deciding which files in a shared one were ours.
    """
    directory = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX))
    destination = directory / page_filename(title, now)
    return destination, destination.with_suffix(".csv.part")


async def stream_csv_export(
    *,
    title: str,
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
    now: datetime | None = None,
) -> tuple[Path, int]:
    """The same file, written where nothing keeps it.

    It exists so that the browser can be sent to a plain address for it: an
    export of ten million rows must not be assembled in the browser's memory,
    and a native download needs something to point at (D28). What points at it
    is a ticket that lasts a minute, and the file goes when the ticket is used.
    """
    return await _write_export(
        paths=await to_thread.run_sync(lambda: _scratch_paths(title=title, now=now)),
        columns=columns,
        batches=batches,
    )


async def save_csv_export(
    *,
    home: Path,
    connector_id: uuid.UUID,
    title: str,
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
    now: datetime | None = None,
) -> tuple[Path, int]:
    """Write a row stream atomically into personal storage."""
    return await _write_export(
        paths=await to_thread.run_sync(
            lambda: _csv_paths(
                home=home, connector_id=connector_id, title=title, now=now
            )
        ),
        columns=columns,
        batches=batches,
    )


async def _write_export(
    *,
    paths: tuple[Path, Path],
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
) -> tuple[Path, int]:
    """Write a row stream atomically, holding at most one batch in memory."""
    destination, temporary = paths
    try:
        row_count = await write_csv(temporary, columns=columns, batches=batches)
        await to_thread.run_sync(lambda: temporary.replace(destination))
    finally:
        await to_thread.run_sync(lambda: temporary.unlink(missing_ok=True))
    return destination, row_count


class CsvTooLarge(Exception):
    """A row stream grew past the ceiling it was being written under."""


async def write_csv(
    path: Path,
    *,
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
    max_bytes: int | None = None,
) -> int:
    """Write a header and a row stream into `path`; the count of rows.

    Not atomic: the caller owns the file and decides where it is published.
    """
    row_count = 0
    written = 0
    try:
        async with await open_file(path, "wb") as output:
            header_rows: list[list[str | None]] = [list(columns)]
            header = await to_thread.run_sync(_encode_csv_rows, header_rows)
            written = await _write_within(
                output, BYTE_ORDER_MARK + header, written, max_bytes
            )
            async for batch in batches:
                if any(len(row) != len(columns) for row in batch.rows):
                    raise ValueError("The source returned an invalid export row")
                encoded = await to_thread.run_sync(_encode_csv_rows, batch.rows)
                written = await _write_within(output, encoded, written, max_bytes)
                row_count += len(batch.rows)
    finally:
        # Left open, a source's generator keeps its cursor and pooled
        # connection until the collector finalises it.
        if isinstance(batches, AsyncGenerator):
            await batches.aclose()
    return row_count


async def _write_within(
    output: AsyncFile[bytes], chunk: bytes, written: int, max_bytes: int | None
) -> int:
    written += len(chunk)
    if max_bytes is not None and written > max_bytes:
        raise CsvTooLarge
    await output.write(chunk)
    return written


def issue_export_ticket(
    *,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    filename: str,
    scratch: str | None = None,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = ExportTicketClaims(
        purpose="export_download",
        user_id=user_id,
        connector_id=connector_id,
        filename=filename,
        scratch=scratch,
        exp=int(issued_at.timestamp()) + EXPORT_TICKET_SECONDS,
    )
    return jwt.encode(
        claims.model_dump(mode="json"), settings.SECRET_KEY, algorithm=security.ALGORITHM
    )


def read_export_ticket(ticket: str) -> ExportTicketClaims | None:
    try:
        payload = jwt.decode(
            ticket, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return ExportTicketClaims.model_validate(payload)
    except (InvalidTokenError, ValidationError):
        return None


def scratch_export_path(claims: ExportTicketClaims) -> Path | None:
    """Resolve a file this module streamed outside personal storage.

    Everything about the path is checked against what this module would have
    made — the system's own temporary directory, one level down, under our
    prefix — so a signed claim naming anywhere else resolves to nothing.
    """
    if claims.scratch is None:
        return None
    if Path(claims.scratch).name != claims.scratch or not claims.scratch.startswith(
        SCRATCH_PREFIX
    ):
        return None
    if Path(claims.filename).name != claims.filename or not claims.filename.endswith(
        ".csv"
    ):
        return None
    root = Path(tempfile.gettempdir())
    directory = root / claims.scratch
    path = directory / claims.filename
    if directory.is_symlink() or path.is_symlink() or not path.is_file():
        return None
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return path


def forget_scratch(path: Path) -> None:
    """Take away the directory an export was streamed into, and the file in it."""
    shutil.rmtree(path.parent, ignore_errors=True)


def stored_export_path(home: Path, claims: ExportTicketClaims) -> Path | None:
    """Resolve only the exact generated file the signed claims name."""
    if claims.scratch is not None:
        return None
    if Path(claims.filename).name != claims.filename or not claims.filename.endswith(
        ".csv"
    ):
        return None
    downloads = home / "downloads"
    directory = downloads / str(claims.connector_id)
    path = directory / claims.filename
    if home.is_symlink() or downloads.is_symlink() or directory.is_symlink():
        return None
    try:
        path.resolve(strict=True).relative_to(home.resolve(strict=True))
    except (OSError, ValueError):
        return None
    if path.is_symlink() or not path.is_file():
        return None
    return path

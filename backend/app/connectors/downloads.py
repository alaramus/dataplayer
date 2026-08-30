"""CSV copies kept in personal storage, bounded in memory while they are made."""

import csv
import io
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

import jwt
from anyio import open_file, to_thread
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


class ExportDownloadRequest(ExportRequest):
    """A whole-row export plus the human title of the open table."""

    title: str = Field(min_length=1, max_length=255)


class ExportReady(BaseModel):
    filename: str
    row_count: int
    download_url: str


class ExportTicketClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["export_download"]
    user_id: uuid.UUID
    connector_id: uuid.UUID
    filename: str
    exp: int


def _safe_stem(title: str) -> str:
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
    filename = f"{_safe_stem(title)}-{downloaded_at:%Y%m%d-%H%M%S-%f}.csv"
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


def save_csv_page(
    *,
    home: Path,
    connector_id: uuid.UUID,
    title: str,
    columns: list[str],
    result: FetchResult,
    now: datetime | None = None,
) -> Path:
    """Write one fetched page atomically and return its path.

    ``columns`` comes from the controlled grid layout. It is checked against
    the fresh adapter answer before any row is written, so a stale layout can
    never shift a value under the wrong heading.
    """
    available = {column.name: index for index, column in enumerate(result.columns)}
    if len(columns) != len(set(columns)):
        raise ValueError("Download columns must be unique")
    unknown = [column for column in columns if column not in available]
    if unknown:
        raise ValueError(f"Unknown download column: {unknown[0]}")

    destination, temporary = _csv_paths(
        home=home, connector_id=connector_id, title=title, now=now
    )
    indexes = [available[column] for column in columns]
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output, quoting=NULL_QUOTING)
            writer.writerow(columns)
            for row in result.rows:
                writer.writerow(row[index] for index in indexes)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _encode_csv_rows(rows: list[list[str | None]]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, quoting=NULL_QUOTING).writerows(rows)
    return output.getvalue().encode("utf-8")


async def save_csv_export(
    *,
    home: Path,
    connector_id: uuid.UUID,
    title: str,
    columns: list[str],
    batches: AsyncIterator[ExportBatch],
    now: datetime | None = None,
) -> tuple[Path, int]:
    """Write a row stream atomically, holding at most one batch in memory."""
    destination, temporary = await to_thread.run_sync(
        lambda: _csv_paths(
            home=home, connector_id=connector_id, title=title, now=now
        )
    )
    row_count = 0
    try:
        async with await open_file(temporary, "wb") as output:
            await output.write(b"\xef\xbb\xbf")
            header_rows: list[list[str | None]] = [list(columns)]
            header = await to_thread.run_sync(_encode_csv_rows, header_rows)
            await output.write(header)
            async for batch in batches:
                if any(len(row) != len(columns) for row in batch.rows):
                    raise ValueError("The source returned an invalid export row")
                encoded = await to_thread.run_sync(_encode_csv_rows, batch.rows)
                await output.write(encoded)
                row_count += len(batch.rows)
        await to_thread.run_sync(lambda: temporary.replace(destination))
    finally:
        await to_thread.run_sync(lambda: temporary.unlink(missing_ok=True))
    return destination, row_count


def issue_export_ticket(
    *,
    user_id: uuid.UUID,
    connector_id: uuid.UUID,
    filename: str,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    claims = ExportTicketClaims(
        purpose="export_download",
        user_id=user_id,
        connector_id=connector_id,
        filename=filename,
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


def stored_export_path(home: Path, claims: ExportTicketClaims) -> Path | None:
    """Resolve only the exact generated file the signed claims name."""
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

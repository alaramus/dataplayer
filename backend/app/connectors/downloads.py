"""CSV copies of bounded table pages kept in a user's personal storage."""

import csv
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from app.adapters.fetch import FetchResult

# SQL NULL is an empty unquoted field and every other value is quoted, so the
# empty string stays distinguishable from the absence of one. This is the
# convention PostgreSQL's own COPY ... CSV writes and reads back; a sentinel
# such as \N would collide with a value that happens to equal it.
NULL_QUOTING: Final = csv.QUOTE_NOTNULL


def _safe_stem(title: str) -> str:
    # Keep letters from every language, but no separator or control character
    # can become part of a path. Repeated punctuation is harmless and keeping
    # this transform small makes the stored provenance readable.
    stem = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in title.strip()
    ).strip("._-")
    return stem[:120] or "table"


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
    temporary = destination.with_suffix(".csv.part")
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

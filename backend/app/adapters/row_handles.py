"""A row handle made of the values a page showed, and a digest of the row.

Shared by the sources that keep no version of a row a client can read —
MySQL (D234, D242) and ClickHouse (D272): the handle carries the values that
find the row again and a digest of the whole row as it was shown, and a
change is made only when the row read again digests the same.
"""

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.core.translation import say


def version_of(cells: list[str | None]) -> str:
    """A digest of a row's values as they are shown."""
    encoded = json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:32]


@dataclass(frozen=True)
class RowHandle:
    # A value of a row named whole may be NULL; a key's never is.
    keys: list[str | None]
    version: str


def encode_handle(keys: list[str | None], version: str, occurrence: int = 0) -> str:
    named: dict[str, object] = {"keys": keys, "version": version}
    if occurrence:
        # Rows that are the same in every value get handles of their own all
        # the same: a page and a selection tell rows apart by them.
        named["n"] = occurrence
    raw = json.dumps(named, separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_handle(value: str, width: int, *, nulls: bool) -> RowHandle:
    """A handle naming `width` values; `nulls` admits NULL among them."""
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded: Any = json.loads(base64.urlsafe_b64decode(padded).decode())
        keys = decoded["keys"]
        version = decoded["version"]
        if (
            not isinstance(keys, list)
            or not all(isinstance(item, str) or item is None for item in keys)
            or not isinstance(version, str)
        ):
            raise ValueError
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError(say("The row handle is not valid")) from None
    if len(keys) != width or (not nulls and None in keys):
        raise ValueError(say("The row handle is not valid for this relation"))
    return RowHandle(keys=keys, version=version)

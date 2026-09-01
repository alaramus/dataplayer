"""Turning what somebody wrote into stored bytes, and back.

One place, so the key used for query content is named once and a caller
cannot reach for the connector key by accident (D63).
"""

import json
from typing import Protocol, runtime_checkable

from app.core import crypto
from app.queries.models import PREVIEW_CHARS, QueryDocument


@runtime_checkable
class HasEncryptedText(Protocol):
    """Anything that keeps its text under the query content key."""

    @property
    def text(self) -> bytes: ...


def encrypted(body: str) -> bytes:
    return crypto.encrypt(body.encode(), purpose="query_content")


def body_of(document: QueryDocument) -> str:
    return crypto.decrypt(document.body, purpose="query_content").decode()


def encrypted_values(values: dict[str, str | None]) -> bytes | None:
    """Remembered bindings, as one encrypted blob, or nothing to keep."""
    if not values:
        return None
    return crypto.encrypt(json.dumps(values).encode(), purpose="query_content")


def values_of(document: QueryDocument) -> dict[str, str | None]:
    """What this document remembers, or nothing when it remembers nothing."""
    if document.parameters is None:
        return {}
    loaded: dict[str, str | None] = json.loads(
        crypto.decrypt(document.parameters, purpose="query_content")
    )
    return loaded


def text_of(kept: HasEncryptedText) -> str:
    """The text a run executed, for a list or a search that decrypts it.

    A document and a run keep their text the same way, under the same key, so
    both are opened here and nowhere else.
    """
    return crypto.decrypt(kept.text, purpose="query_content").decode()


def preview_of(body: str) -> str:
    """The first line with anything on it, shortened.

    What a library shows for a document nobody has named. Built per response
    from the decrypted body and never written down, so it is not a plaintext
    copy of the first line of every query in the database.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:PREVIEW_CHARS]
    return ""

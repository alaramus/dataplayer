"""Turning what somebody wrote into stored bytes, and back.

One place, so the key used for query content is named once and a caller
cannot reach for the connector key by accident (D63).
"""

from app.core import crypto
from app.queries.models import PREVIEW_CHARS, QueryDocument


def encrypted(body: str) -> bytes:
    return crypto.encrypt(body.encode(), purpose="query_content")


def body_of(document: QueryDocument) -> str:
    return crypto.decrypt(document.body, purpose="query_content").decode()


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

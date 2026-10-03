"""Reading and writing query documents.

The body is ciphertext in every row this module hands out; turning it back
into text is `content.py`, and nothing here logs either form.
"""

import uuid
from collections.abc import Sequence

from anyio import to_thread
from sqlalchemy import ColumnElement
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from app.core.config import settings
from app.core.schemas import get_datetime_utc
from app.queries.content import body_of, encrypted, encrypted_values
from app.queries.models import EditorLayout, QueryDocument
from app.users.models import User


async def create(
    session: AsyncSession,
    *,
    owner: User,
    connector_id: uuid.UUID,
    title: str | None,
    body: str,
    search_path: Sequence[str],
    layout: EditorLayout,
    parameters: dict[str, str | None] | None = None,
) -> QueryDocument:
    document = QueryDocument(
        owner_id=owner.id,
        connector_id=connector_id,
        title=title,
        body=encrypted(body),
        search_path=list(search_path),
        layout=layout.model_dump(),
        parameters=encrypted_values(parameters or {}),
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


async def get_owned(
    session: AsyncSession, *, document_id: uuid.UUID, owner: User
) -> QueryDocument | None:
    """One document, if it belongs to this caller.

    Ownership is checked here rather than by the route comparing ids, so a
    document belonging to somebody else is indistinguishable from one that
    does not exist — the same rule the connector routes follow (D33).
    """
    document = await session.get(QueryDocument, document_id)
    if document is None or document.owner_id != owner.id:
        return None
    return document


async def save(session: AsyncSession, *, document: QueryDocument) -> QueryDocument:
    document.updated_at = get_datetime_utc()
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


def matches(document: QueryDocument, needle: str) -> bool:
    """Whether a search text appears in this document's title or body.

    In memory and per document: D63 forbids a plaintext token index, so the
    price of searching is decrypting a bounded number of bodies and forgetting
    them again. The needle itself is neither stored nor logged.
    """
    lowered = needle.casefold()
    if lowered in (document.title or "").casefold():
        return True
    return lowered in body_of(document).casefold()


async def list_for(
    session: AsyncSession,
    *,
    owner: User,
    connector_id: uuid.UUID | None = None,
    search: str = "",
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[QueryDocument], int]:
    """The library, newest first.

    Without a search the database does the paging. With one it cannot: the
    body it would have to match is ciphertext, so the newest
    QUERY_SEARCH_MAX_DOCUMENTS are read and filtered here. The bound is the
    reason this is not a way to decrypt everything at once.
    """
    condition = _of(owner, connector_id)
    if not search:
        count = await _count(session, condition)
        page = (await session.exec(_newest_first(condition).offset(skip).limit(limit))).all()
        return list(page), count

    candidates, _ = await newest(session, owner=owner, connector_id=connector_id)
    # Up to five hundred bodies of up to a mebibyte each: decrypted on a worker
    # thread, never on the loop every other request is waiting on.
    found = await to_thread.run_sync(matching, candidates, search)
    return found[skip : skip + limit], len(found)


async def newest(
    session: AsyncSession, *, owner: User, connector_id: uuid.UUID | None = None
) -> tuple[list[QueryDocument], bool]:
    """The documents a search may decrypt, and whether older ones were left out.

    The newest QUERY_SEARCH_MAX_DOCUMENTS: the one bound on searching bodies,
    shared by the library and the search (D63, D204).
    """
    bound = settings.QUERY_SEARCH_MAX_DOCUMENTS
    condition = _of(owner, connector_id)
    rows = list((await session.exec(_newest_first(condition).limit(bound))).all())
    left_out = len(rows) == bound and await _count(session, condition) > bound
    return rows, left_out


def _of(owner: User, connector_id: uuid.UUID | None) -> ColumnElement[bool]:
    condition = col(QueryDocument.owner_id) == owner.id
    if connector_id is not None:
        condition = condition & (col(QueryDocument.connector_id) == connector_id)
    return condition


def _newest_first(condition: ColumnElement[bool]) -> SelectOfScalar[QueryDocument]:
    return (
        select(QueryDocument)
        .where(condition)
        .order_by(col(QueryDocument.updated_at).desc(), col(QueryDocument.id))
    )


async def _count(session: AsyncSession, condition: ColumnElement[bool]) -> int:
    return (
        await session.exec(select(func.count()).select_from(QueryDocument).where(condition))
    ).one()


def matching(documents: Sequence[QueryDocument], needle: str) -> list[QueryDocument]:
    """The documents whose title or body holds the needle. Blocking: decrypts."""
    return [document for document in documents if matches(document, needle)]


async def delete(session: AsyncSession, *, document: QueryDocument) -> None:
    await session.delete(document)
    await session.commit()

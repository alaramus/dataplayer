"""Reading and writing query documents.

The body is ciphertext in every row this module hands out; turning it back
into text is `content.py`, and nothing here logs either form.
"""

import uuid
from collections.abc import Sequence

from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

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
    condition = col(QueryDocument.owner_id) == owner.id
    if connector_id is not None:
        condition = condition & (col(QueryDocument.connector_id) == connector_id)

    ordered = (
        select(QueryDocument)
        .where(condition)
        .order_by(col(QueryDocument.updated_at).desc(), col(QueryDocument.id))
    )
    if not search:
        count = (
            await session.exec(
                select(func.count()).select_from(QueryDocument).where(condition)
            )
        ).one()
        page = (await session.exec(ordered.offset(skip).limit(limit))).all()
        return list(page), count

    candidates = (
        await session.exec(ordered.limit(settings.QUERY_SEARCH_MAX_DOCUMENTS))
    ).all()
    found = [document for document in candidates if matches(document, search)]
    return found[skip : skip + limit], len(found)


async def delete(session: AsyncSession, *, document: QueryDocument) -> None:
    await session.delete(document)
    await session.commit()

"""What a person copied in the application, kept for them to copy again (D460).

Written by the browser after a copy it made itself; a secret is never sent
here, which the frontend's `copyText` decides. Kept as plain text, deliberately
unencrypted: it is what the person already had on their screen.
"""

import uuid
from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict
from pydantic import Field as Constrained
from sqlalchemy import Column, DateTime, Index, String, Text, func
from sqlmodel import Field, SQLModel, col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.schemas import get_datetime_utc

# Where on the screen a text was copied from, as a closed set: the browser
# words it in the person's language, which a stored sentence could not follow.
CopySource = Literal[
    "grid", "agent", "catalog", "code", "connection", "document", "view",
    "link", "log", "record", "key", "other",
]
SOURCES: tuple[CopySource, ...] = get_args(CopySource)

# The characters of one copy that are kept; a longer one is kept cut. The
# browser sends one more than this and no more (`features/copies/record.ts`).
MAX_CHARS = 65_536
# The copies kept per person; the oldest go as new ones come.
KEEP = 500
# How much of a copy the list shows. The whole text is asked for when copied again.
PREVIEW_CHARS = 300


class CopiedText(SQLModel, table=True):
    __tablename__ = "copied_text"
    __table_args__ = (Index("ix_copied_text_owner_copied", "owner_id", "copied_at"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    text: str = Field(sa_column=Column(Text, nullable=False))
    source: str = Field(sa_column=Column(String(16), nullable=False))
    detail: str | None = Field(default=None, max_length=200)
    cut: bool = Field(default=False)
    copied_at: datetime = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))


class CopyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Constrained(min_length=1, max_length=MAX_CHARS + 1)
    source: CopySource
    # What was copied from, as the screen names it: a table, a connection.
    detail: str | None = Constrained(default=None, max_length=200)


class CopyBrief(BaseModel):
    """One copy as the list shows it: the start of its text."""

    id: uuid.UUID
    preview: str
    length: int
    cut: bool
    source: CopySource
    detail: str | None
    copied_at: datetime


class CopyPublic(CopyBrief):
    text: str


class CopiesPublic(BaseModel):
    items: list[CopyBrief]
    # Every copy kept, whatever the search left out.
    total: int


class CopiesDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Constrained(min_length=1, max_length=KEEP)


class CopiesDeleted(BaseModel):
    deleted: int


def source_of(stored: str) -> CopySource:
    for source in SOURCES:
        if source == stored:
            return source
    return "other"


def brief_of(row: CopiedText) -> CopyBrief:
    return CopyBrief(
        id=row.id,
        preview=row.text[:PREVIEW_CHARS],
        length=len(row.text),
        cut=row.cut,
        source=source_of(row.source),
        detail=row.detail,
        copied_at=row.copied_at,
    )


def public_of(row: CopiedText) -> CopyPublic:
    return CopyPublic(**brief_of(row).model_dump(), text=row.text)


async def list_own(
    session: AsyncSession, owner_id: uuid.UUID, query: str | None
) -> CopiesPublic:
    statement = select(CopiedText).where(CopiedText.owner_id == owner_id)
    if query:
        statement = statement.where(col(CopiedText.text).icontains(query, autoescape=True))
    rows = await session.exec(statement.order_by(col(CopiedText.copied_at).desc()).limit(KEEP))
    total = await session.exec(
        select(func.count()).select_from(CopiedText).where(CopiedText.owner_id == owner_id)
    )
    return CopiesPublic(items=[brief_of(row) for row in rows.all()], total=total.one())


async def read_own(
    session: AsyncSession, owner_id: uuid.UUID, copy_id: uuid.UUID
) -> CopiedText | None:
    row = await session.get(CopiedText, copy_id)
    return row if row is not None and row.owner_id == owner_id else None


async def record(session: AsyncSession, owner_id: uuid.UUID, body: CopyCreate) -> CopyBrief:
    """Keep a copy on top of the list.

    The same text copied again moves up rather than standing twice, so copying
    one value back and forth does not push everything else out.
    """
    cut = len(body.text) > MAX_CHARS
    text = body.text[:MAX_CHARS]
    row = (
        await session.exec(
            select(CopiedText).where(CopiedText.owner_id == owner_id, CopiedText.text == text)
        )
    ).first()
    if row is None:
        row = CopiedText(owner_id=owner_id, text=text, source=body.source, cut=cut)
    row.source = body.source
    row.detail = body.detail
    row.copied_at = get_datetime_utc()
    session.add(row)
    await session.flush()
    kept = (
        select(CopiedText.id)
        .where(CopiedText.owner_id == owner_id)
        .order_by(col(CopiedText.copied_at).desc())
        .offset(KEEP)
    )
    outgrown = list((await session.exec(kept)).all())
    if outgrown:
        await session.exec(delete(CopiedText).where(col(CopiedText.id).in_(outgrown)))
    await session.commit()
    await session.refresh(row)
    return brief_of(row)


async def delete_own(
    session: AsyncSession, owner_id: uuid.UUID, ids: list[uuid.UUID] | None
) -> int:
    """Delete these copies of this person, or every one of them for None.

    An id that is not theirs, or is gone already, is not counted: deleting is
    asked for what the list showed, and another tab may have been quicker.
    """
    statement = select(CopiedText.id).where(CopiedText.owner_id == owner_id)
    if ids is not None:
        statement = statement.where(col(CopiedText.id).in_(ids))
    found = list((await session.exec(statement)).all())
    if found:
        await session.exec(delete(CopiedText).where(col(CopiedText.id).in_(found)))
        await session.commit()
    return len(found)

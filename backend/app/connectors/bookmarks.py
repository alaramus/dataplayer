"""Where a reader stands in a source that keeps no reader's place (D319).

Kafka keeps a consumer group's positions itself (D312); Binance keeps
nothing for anybody, so the bookmark of a pipeline's link reading it on is a
row here, one per connection, node and reader, gone with the connection.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlmodel import Field, SQLModel, col, select

from app.adapters.reading_on import Bookmark
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc


class ReadingBookmark(SQLModel, table=True):
    __tablename__ = "reading_bookmark"

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    node_id: str = Field(sa_column=Column(String(1024), primary_key=True))
    reader: str = Field(sa_column=Column(String(255), primary_key=True))
    positions: dict[str, int] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    written_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ConnectionBookmarks:
    """One connection's bookmarks, handed to its source (`BookmarkAccess`).

    Opens a session of its own: it is asked in the middle of a transfer,
    long after the request that built the source began, as a key is (D146).
    """

    def __init__(self, connector_id: uuid.UUID) -> None:
        self._connector_id = connector_id

    async def read(self, node_id: str, reader: str) -> Bookmark | None:
        async with async_session_maker() as session:
            found = (
                await session.exec(
                    select(ReadingBookmark).where(
                        col(ReadingBookmark.connector_id) == self._connector_id,
                        col(ReadingBookmark.node_id) == node_id,
                        col(ReadingBookmark.reader) == reader,
                    )
                )
            ).first()
        return None if found is None else Bookmark(positions=dict(found.positions))

    async def write(self, node_id: str, reader: str, at: Bookmark) -> None:
        now = get_datetime_utc()
        statement = insert(ReadingBookmark).values(
            connector_id=self._connector_id,
            node_id=node_id,
            reader=reader,
            positions=at.positions,
            written_at=now,
        )
        async with async_session_maker() as session:
            await session.exec(
                statement.on_conflict_do_update(
                    index_elements=["connector_id", "node_id", "reader"],
                    set_={"positions": at.positions, "written_at": now},
                )
            )
            await session.commit()

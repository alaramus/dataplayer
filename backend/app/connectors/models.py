import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Index, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.core.access import Access, Grant
from app.core.schemas import get_datetime_utc


class Connector(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(min_length=1, max_length=255)
    # A key into the adapter type registry, not a foreign key: the registry
    # lives in code, so a new source type needs no migration.
    adapter_type: str = Field(max_length=64)
    config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    secrets: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    # Switched off rather than deleted: the row stays, and what it loses is the
    # right to become a live adapter. A server default as well as a Python one,
    # so rows written before the column existed answer the same.
    enabled: bool = Field(default=True, sa_column_kwargs={"server_default": "true"})
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ConnectorCreate(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    adapter_type: str = Field(max_length=64)
    options: dict[str, Any]


class ConnectorUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    options: dict[str, Any] | None = None
    enabled: bool | None = None


class ConnectorGrant(SQLModel, table=True):
    """One person's standing on one connection.

    A row, not a rule: the question every route asks is answered by a primary
    key lookup. `access` is a plain string column carrying a value of the
    `Grant` union, so a level the application does not know fails to validate
    on the way out of the database rather than being compared as an unranked
    string.
    """

    # Every list a user opens asks which connections are granted to them, and
    # the primary key leads with the connector. Declared here as well as in the
    # migration that made it, so the model is the whole description of the
    # table and `alembic check` has nothing to report.
    __table_args__ = (Index("ix_connectorgrant_user_id", "user_id"),)

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    access: Grant = Field(sa_column=Column(String(16), nullable=False))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ConnectorPublic(SQLModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    config: dict[str, Any]
    enabled: bool
    # What the caller may do with this connection. Sent rather than derived on
    # the client: a screen that hides a button by knowing the rules is a second
    # place the rules live, and the first it would hear of a refusal is a 403.
    access: Access
    # Whose it is, when it is not the caller's own. None for your own
    # connections, where naming the owner would only be your own address.
    owner_email: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectorsPublic(SQLModel):
    data: list[ConnectorPublic]
    count: int


class GrantPublic(SQLModel):
    """A grant as the owner of the connection sees it."""

    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    access: Grant


class GrantsPublic(SQLModel):
    data: list[GrantPublic]


class GrantWrite(SQLModel):
    """Give a level, or raise or lower one already given."""

    user_id: uuid.UUID
    access: Grant

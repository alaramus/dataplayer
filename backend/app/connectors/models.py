import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, LargeBinary, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models import get_datetime_utc


class Connector(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_connector_owner_name"),
    )

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


class ConnectorPublic(SQLModel):
    id: uuid.UUID
    name: str
    adapter_type: str
    config: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConnectorsPublic(SQLModel):
    data: list[ConnectorPublic]
    count: int

"""What the application database keeps about metrics, and what the API says.

Samples are not here: they live in the store (D126). Agents and the store
setting are here, beside the users who own them.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from sqlalchemy import JSON, CheckConstraint, Column, DateTime, LargeBinary
from sqlmodel import Field, SQLModel

from app.core.schemas import get_datetime_utc
from app.jobs.models import JobPublic

MAX_AGENT_NAME = 120
MAX_SERIES_PER_REQUEST = 200
DEFAULT_MAX_POINTS = 1000
MAX_POINTS = 5000
MIN_RANGE_SECONDS = 60
MAX_RANGE_SECONDS = 366 * 24 * 3600


class MetricsAgent(SQLModel, table=True):
    """An external agent a person registered, and the key it reports under."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    name: str = Field(max_length=MAX_AGENT_NAME)
    key_fingerprint: str = Field(max_length=64, unique=True, index=True)
    key_sealed: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    key_issued_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MetricsStoreSetting(SQLModel, table=True):
    """Where the installation's metrics store is. One row or none (D126).

    The options are the PostgreSQL adapter's, split the way a connector's are:
    configuration in the clear, secrets encrypted under the connector key (D4).
    """

    __table_args__ = (CheckConstraint("id = 1", name="metrics_store_is_one_row"),)

    id: int = Field(default=1, primary_key=True)
    config: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    secrets: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # The service it was started as, when it was started rather than connected.
    service_id: uuid.UUID | None = Field(
        default=None, foreign_key="managedservice.id", ondelete="SET NULL"
    )
    configured_by: uuid.UUID | None = Field(
        default=None, foreign_key="user.id", ondelete="SET NULL"
    )
    configured_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


ReportingInterval = Literal[15, 30, 60, 300]


class MetricsConnector(SQLModel, table=True):
    """Whether a connection reports its own metrics, and how often (D128).

    A row of its own rather than a column of the connector: reporting is about
    dashboards, and a connector knows nothing of them.
    """

    connector_id: uuid.UUID = Field(
        foreign_key="connector.id", primary_key=True, ondelete="CASCADE"
    )
    enabled: bool = Field(default=False)
    interval_seconds: int = Field(default=30)
    changed_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ConnectorReporting(BaseModel):
    connector_id: uuid.UUID
    name: str
    adapter_type: str
    enabled: bool
    interval_seconds: ReportingInterval
    # Only the owner decides whether their database is polled.
    may_change: bool
    last_heard_at: datetime | None = None


class ReportingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    interval_seconds: ReportingInterval = 30


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = PydanticField(min_length=1, max_length=MAX_AGENT_NAME)


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = PydanticField(min_length=1, max_length=MAX_AGENT_NAME)


class AgentPublic(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    key_issued_at: datetime
    # When the store last received a sample from it. Null when it never has,
    # or when the store cannot be asked.
    last_heard_at: datetime | None = None


class AgentKey(BaseModel):
    """The key, for the agent's owner to put into the agent's configuration."""

    agent: AgentPublic
    key: str
    # Where the agent sends to: the UDP port of the metrics process.
    udp_port: int


StoreState = Literal["not_configured", "starting", "failed", "ready", "unreachable"]


class StartOffer(BaseModel):
    available: bool
    reason: str | None = None


class StoreStatus(BaseModel):
    state: StoreState
    # Whether the caller is somebody who sets the store up.
    may_set_up: bool
    # Whether starting TimescaleDB on this server is possible now. Only told to
    # somebody who may set the store up.
    start: StartOffer | None = None
    # The job starting the store, while it runs or after it failed.
    job: JobPublic | None = None
    message: str | None = None


class StoreConnect(BaseModel):
    """An existing TimescaleDB, in the PostgreSQL adapter's options."""

    model_config = ConfigDict(extra="forbid")

    options: dict[str, Any]


class SeriesInfo(BaseModel):
    id: int
    field: str
    label: str
    unit: str
    first_seen: datetime
    last_seen: datetime


class MetricInfo(BaseModel):
    metric: str
    series: list[SeriesInfo]


class HostInfo(BaseModel):
    host: str
    last_seen: datetime
    metrics: list[MetricInfo]
    # Whether it sent a process table in the last day.
    processes: bool = False


class AgentSources(BaseModel):
    agent_id: uuid.UUID
    name: str
    hosts: list[HostInfo]


class ConnectorSources(BaseModel):
    connector_id: uuid.UUID
    name: str
    adapter_type: str
    last_seen: datetime
    metrics: list[MetricInfo]


class MetricsCatalog(BaseModel):
    agents: list[AgentSources]
    connectors: list[ConnectorSources] = PydanticField(default_factory=list)


ProcessLimit = Literal[10, 20, 50, 100, 200]


class ProcessInfo(BaseModel):
    pid: int
    ppid: int
    user: str
    command: str
    pcpu: float
    pmem: float
    elapsed: str


class ProcessTable(BaseModel):
    # Seconds; null when the host sent no table in the last hour.
    ts: int | None
    rows: list[ProcessInfo]


class HistoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series_ids: list[int] = PydanticField(min_length=1, max_length=MAX_SERIES_PER_REQUEST)
    # Seconds since the epoch, both ends included.
    start: int = PydanticField(ge=0)
    end: int = PydanticField(ge=0)
    max_points: int = PydanticField(default=DEFAULT_MAX_POINTS, ge=10, le=MAX_POINTS)


class SeriesHistory(BaseModel):
    series_id: int
    # Raw: [ts, value]. Bucketed: [ts, avg, min, max]. The value is at index 1
    # either way, so a chart need not know which it got.
    points: list[list[float]]


class HistoryAnswer(BaseModel):
    start: int
    end: int
    # Null for raw samples; the width of a bucket otherwise.
    bucket_seconds: int | None
    series: list[SeriesHistory]

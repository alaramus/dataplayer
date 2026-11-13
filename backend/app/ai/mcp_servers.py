"""Outside MCP servers a person lets the agent call (D360).

A server is its owner's alone: its token stands for an account of whoever
entered it. The token and the other headers are sealed as a provider key is,
and only their presence and the headers' names ever leave the server.
"""

import ipaddress
import re
import socket
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from anyio import to_thread
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator
from pydantic import Field as Constrained
from sqlalchemy import JSON, Column, DateTime, Index, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import crypto
from app.core.config import settings
from app.core.problems import MESSAGES, ProblemCode
from app.core.schemas import get_datetime_utc

MAX_SERVERS = 20
MAX_HEADERS = 10
# A header the HTTP client or MCP itself sets; one typed in would break the
# request or pretend to be another session.
RESERVED_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "content-type",
        "accept",
        "connection",
        "transfer-encoding",
        "mcp-session-id",
        "mcp-protocol-version",
        "authorization",
    }
)
HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")


class McpServer(SQLModel, table=True):
    __tablename__ = "mcp_server"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_mcp_server_owner_name"),
        Index("ix_mcp_server_owner", "owner_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(max_length=2048)
    # {"token": ..., "headers": {...}}, sealed; nothing when neither is set.
    secret: bytes | None = Field(default=None, sa_column=Column(LargeBinary, nullable=True))
    header_names: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]")
    )
    has_token: bool = Field(default=False)
    enabled: bool = Field(default=True)
    tools_off: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False, server_default="[]")
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )


def _check_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("The address must start with http:// or https:// and name a host")
    if parts.username or parts.password:
        raise ValueError("Put credentials in the token or a header, not in the address")
    return value.strip()


def _check_headers(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if len(value) > MAX_HEADERS:
        raise ValueError(f"At most {MAX_HEADERS} headers")
    for name in value:
        if not HEADER_NAME.match(name):
            raise ValueError(f"{name!r} is not a header name")
        if name.lower() in RESERVED_HEADERS:
            raise ValueError(f"{name} is set by DataPlayer itself; use the token for Authorization")
    return value


class McpServerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Constrained(min_length=1, max_length=60)
    url: str = Constrained(min_length=1, max_length=2048)
    token: SecretStr | None = Constrained(default=None, max_length=4096)
    headers: dict[str, SecretStr] = Constrained(default_factory=dict)
    enabled: bool = True

    _url = field_validator("url")(_check_url)
    _headers = field_validator("headers")(_check_headers)


class McpServerUpdate(BaseModel):
    """What changes; a field left out stays. A header sent with `null` keeps
    the value it had, so the list can be edited without typing them again."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Constrained(default=None, min_length=1, max_length=60)
    url: str | None = Constrained(default=None, min_length=1, max_length=2048)
    token: SecretStr | None = Constrained(default=None, max_length=4096)
    clear_token: bool = False
    headers: dict[str, SecretStr | None] | None = None
    enabled: bool | None = None
    tools_off: list[str] | None = Constrained(default=None, max_length=500)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value)

    _headers = field_validator("headers")(_check_headers)


class McpServerPublic(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    has_token: bool
    header_names: list[str]
    enabled: bool
    tools_off: list[str]
    created_at: datetime
    updated_at: datetime


class McpToolPublic(BaseModel):
    name: str
    title: str | None
    description: str | None
    read_only: bool
    enabled: bool


class McpToolsPublic(BaseModel):
    server_id: uuid.UUID
    tools: list[McpToolPublic]


def public_of(server: McpServer) -> McpServerPublic:
    return McpServerPublic.model_validate(server, from_attributes=True)


class Credentials(BaseModel):
    token: str | None = None
    headers: dict[str, str] = Constrained(default_factory=dict)


def credentials_of(server: McpServer) -> Credentials:
    if server.secret is None:
        return Credentials()
    return Credentials.model_validate_json(crypto.decrypt(server.secret, purpose="connector"))


def _seal(server: McpServer, credentials: Credentials) -> None:
    server.has_token = credentials.token is not None
    server.header_names = sorted(credentials.headers)
    server.secret = (
        crypto.encrypt(credentials.model_dump_json().encode(), purpose="connector")
        if credentials.token is not None or credentials.headers
        else None
    )


def request_headers(server: McpServer) -> dict[str, str]:
    credentials = credentials_of(server)
    headers = dict(credentials.headers)
    if credentials.token is not None:
        headers["Authorization"] = f"Bearer {credentials.token}"
    return headers


class AddressRefused(ValueError):
    """The address leads somewhere this installation does not let it go (D360)."""

    def __init__(self, code: ProblemCode, message: str) -> None:
        super().__init__(message)
        self.code: ProblemCode = code


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def check_address(url: str) -> None:
    """Refuse an address that resolves inside, unless the installation allows it.

    Asked before every connection rather than once when saved: a name may lead
    elsewhere tomorrow.
    """
    _check_url(url)
    if settings.MCP_CLIENT_ALLOW_PRIVATE:
        return
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        found = await to_thread.run_sync(
            lambda: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    except OSError as failure:
        raise AddressRefused(
            "ai.mcp_address_unresolved", MESSAGES["ai.mcp_address_unresolved"]
        ) from failure
    if not found or not all(_public(str(entry[4][0])) for entry in found):
        raise AddressRefused("ai.mcp_address_private", MESSAGES["ai.mcp_address_private"])


async def list_own(session: AsyncSession, owner_id: uuid.UUID) -> list[McpServer]:
    rows = await session.exec(
        select(McpServer)
        .where(col(McpServer.owner_id) == owner_id)
        .order_by(col(McpServer.name))
    )
    return list(rows.all())


async def get_own(
    session: AsyncSession, owner_id: uuid.UUID, server_id: uuid.UUID
) -> McpServer | None:
    server = await session.get(McpServer, server_id)
    return server if server is not None and server.owner_id == owner_id else None


class ServerRefused(ValueError):
    """A save that would break a rule of the list."""

    def __init__(self, code: ProblemCode, **params: object) -> None:
        super().__init__(MESSAGES[code].format(**params))
        self.code: ProblemCode = code
        self.params = params


async def _name_taken(
    session: AsyncSession, owner_id: uuid.UUID, name: str, other_than: uuid.UUID | None
) -> bool:
    rows = await session.exec(
        select(McpServer.id).where(
            col(McpServer.owner_id) == owner_id, col(McpServer.name) == name
        )
    )
    return any(found != other_than for found in rows.all())


async def create(
    session: AsyncSession, owner_id: uuid.UUID, body: McpServerCreate
) -> McpServer:
    if len(await list_own(session, owner_id)) >= MAX_SERVERS:
        raise ServerRefused("ai.mcp_server_limit", limit=MAX_SERVERS)
    name = body.name.strip()
    if await _name_taken(session, owner_id, name, None):
        raise ServerRefused("ai.mcp_server_name_taken")
    server = McpServer(owner_id=owner_id, name=name, url=body.url, enabled=body.enabled)
    _seal(
        server,
        Credentials(
            token=body.token.get_secret_value() if body.token is not None else None,
            headers={key: value.get_secret_value() for key, value in body.headers.items()},
        ),
    )
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


async def update(
    session: AsyncSession, server: McpServer, body: McpServerUpdate
) -> McpServer:
    if body.name is not None:
        name = body.name.strip()
        if await _name_taken(session, server.owner_id, name, server.id):
            raise ServerRefused("ai.mcp_server_name_taken")
        server.name = name
    if body.url is not None:
        server.url = body.url
    if body.enabled is not None:
        server.enabled = body.enabled
    if body.tools_off is not None:
        server.tools_off = sorted(set(body.tools_off))
    if body.token is not None or body.clear_token or body.headers is not None:
        kept = credentials_of(server)
        token = kept.token
        if body.clear_token:
            token = None
        if body.token is not None:
            token = body.token.get_secret_value()
        headers = kept.headers
        if body.headers is not None:
            headers = {}
            for key, value in body.headers.items():
                if value is not None:
                    headers[key] = value.get_secret_value()
                elif key in kept.headers:
                    headers[key] = kept.headers[key]
                else:
                    raise ServerRefused("ai.mcp_header_value_required", name=key)
        _seal(server, Credentials(token=token, headers=headers))
    server.updated_at = get_datetime_utc()
    session.add(server)
    await session.commit()
    await session.refresh(server)
    return server


async def delete_own(
    session: AsyncSession, owner_id: uuid.UUID, server_id: uuid.UUID
) -> bool:
    server = await get_own(session, owner_id, server_id)
    if server is None:
        return False
    await session.delete(server)
    await session.commit()
    return True

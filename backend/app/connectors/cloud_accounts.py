"""Cloud accounts: a person's, kept apart from the connections that use them (D451).

The shape of SSH keys (D146): a connection names an account by id, the account
is a row of its owner's, its secrets are encrypted under the connector key and
never sent back, and a grantee's reads use the owner's account without seeing
it (D33). What an account is asked for is issued at every new connection and
kept only in this process (D449).
"""

import json
import logging
import time
import uuid
from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from anyio import to_thread
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic import Field as Constrained
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as options_schema
from app.adapters import registry
from app.adapters.cloud import AccountKind, IssuedSecret, SecretRequest, issuer_for
from app.adapters.cloud.accounts import (
    KIND_TITLES,
    KINDS,
    CloudAccountSettings,
    method_of,
    schema_of,
)
from app.adapters.cloud.cache import IssueCache
from app.adapters.protocol import AdapterError
from app.connectors.models import Connector
from app.connectors.ssh_keys import SshKeyUse
from app.core import crypto
from app.core.config import settings as installation
from app.core.db import async_session_maker
from app.core.problems import Problem
from app.core.schemas import get_datetime_utc, refusal_sentence
from app.core.translation import say, say_schema
from app.users.models import User

logger = logging.getLogger(__name__)


class CloudAccount(SQLModel, table=True):
    """One account; its secrets are never shown again."""

    __table_args__ = (
        Index("ix_cloudaccount_owner", "owner_id"),
        UniqueConstraint("owner_id", "name", name="uq_cloudaccount_owner_name"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(sa_column=Column(String(8), nullable=False))
    method: str = Field(sa_column=Column(String(32), nullable=False))
    # What may be said out loud: a region, a role, an address.
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # JSON of the secret fields, encrypted under the connector key (D4).
    secrets: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    # Bumped on every change, so what was issued under the old settings is
    # never handed out again (D449).
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False, server_default="1"))
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))
    updated_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"CloudAccount({self.id}, {self.name!r}, {self.method})"


class CloudAccountPublic(BaseModel):
    """Everything about an account that may be said out loud."""

    id: uuid.UUID
    name: str
    kind: AccountKind
    kind_title: str
    method: str
    method_title: str
    settings: dict[str, Any]
    # Which secret fields hold a value, so an edit can say "stored" in them.
    stored_secrets: list[str]
    # Signs in as this server rather than as credentials of its own (D452).
    ambient: bool
    # Whether this installation can make the account's test call.
    testable: bool
    created_at: datetime | None
    updated_at: datetime | None
    used_by: list[SshKeyUse]


class CloudAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Constrained(min_length=1, max_length=255)
    # Validated against the schema of the kind its `method` belongs to; a
    # runtime schema, as a connection's options are.
    settings: dict[str, Any]


class CloudAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Constrained(default=None, min_length=1, max_length=255)
    # A secret left empty keeps the stored one, as a connection's do.
    settings: dict[str, Any] | None = None


class CloudAccountKindSchema(BaseModel):
    kind: AccountKind
    title: str
    json_schema: dict[str, Any]


class CloudAccountSchemas(BaseModel):
    """The kinds of account, each with the methods this person may choose."""

    kinds: list[CloudAccountKindSchema]
    # Whether methods signing in as this server are offered to this person.
    ambient: bool


class CloudAccountTest(BaseModel):
    ok: bool
    message: str


class CloudRegion(BaseModel):
    """A region the field offers: its name, and what the provider calls it."""

    name: str
    title: str


def ambient_offered(user: User) -> bool:
    return installation.CLOUD_AMBIENT_CREDENTIALS and user.is_superuser


def schemas_for(user: User) -> CloudAccountSchemas:
    ambient = ambient_offered(user)
    return CloudAccountSchemas(
        kinds=[
            CloudAccountKindSchema(
                kind=kind,
                title=KIND_TITLES[kind],
                json_schema=say_schema(options_schema.json_schema(schema_of(kind, ambient=ambient))),
            )
            for kind in KINDS
        ],
        ambient=ambient,
    )


def _refusal(exc: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[
            {
                "loc": ["body", "settings", *error["loc"]],
                "msg": refusal_sentence(error),
                "type": error["type"],
            }
            for error in exc.errors()
        ],
    )


def _method_or_422(data: Mapping[str, Any]) -> type[CloudAccountSettings]:
    found = method_of(str(data.get("method", "")))
    if found is None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "settings", "method"],
                    "msg": say("Choose how the account signs in"),
                    "type": "value_error",
                }
            ],
        )
    return found


def validated(data: Mapping[str, Any], user: User) -> CloudAccountSettings:
    """An account's settings as their model, once the ambient gate let them by (D452)."""
    method = _method_or_422(data)
    if method.ambient:
        if not installation.CLOUD_AMBIENT_CREDENTIALS:
            raise Problem(403, "cloud_accounts.ambient_off")
        if not user.is_superuser:
            raise Problem(403, "cloud_accounts.ambient_superuser")
    try:
        model = options_schema.validate(schema_of(method.kind, ambient=True), data)
    except ValidationError as exc:
        raise _refusal(exc) from None
    return cast(CloudAccountSettings, model)


def _secret_names(model: CloudAccountSettings) -> set[str]:
    return options_schema.secret_field_names(type(model))


def split(model: CloudAccountSettings) -> tuple[dict[str, Any], bytes]:
    """What may be shown, and the secrets encrypted. An empty secret is not kept."""
    names = _secret_names(model)
    dumped = model.model_dump(mode="json")
    shown = {name: value for name, value in dumped.items() if name not in names}
    hidden = {
        name: getattr(model, name).get_secret_value()
        for name in names
        if getattr(model, name).get_secret_value() != ""
    }
    return shown, crypto.encrypt(json.dumps(hidden).encode(), purpose="connector")


def secrets_of(row: CloudAccount) -> dict[str, str]:
    found: dict[str, str] = json.loads(crypto.decrypt(row.secrets, purpose="connector"))
    return found


def with_stored_secrets(row: CloudAccount, data: Mapping[str, Any]) -> dict[str, Any]:
    """The settings sent, with each secret left empty taken from the row.

    Only for the same method: another method's secrets are another thing.
    """
    filled = dict(data)
    method = method_of(str(filled.get("method", "")))
    if method is None or method.model_fields["method"].default != row.method:
        return filled
    stored = secrets_of(row)
    for name in options_schema.secret_field_names(method):
        if not filled.get(name) and name in stored:
            filled[name] = stored[name]
    return filled


def settings_of(row: CloudAccount) -> CloudAccountSettings:
    """The row's settings as their model, secrets included."""
    method = method_of(row.method)
    if method is None:
        raise AdapterError("config", say("This cloud account signs in a way this server no longer knows"))
    return method.model_validate({**row.settings, **secrets_of(row)})


async def list_own(session: AsyncSession, owner_id: uuid.UUID) -> list[CloudAccount]:
    rows = await session.exec(
        select(CloudAccount).where(CloudAccount.owner_id == owner_id).order_by(col(CloudAccount.name))
    )
    return list(rows.all())


async def get_own(
    session: AsyncSession, account_id: uuid.UUID, owner_id: uuid.UUID
) -> CloudAccount | None:
    """One account of this owner. Somebody else's answers exactly as a missing one."""
    row = await session.get(CloudAccount, account_id)
    if row is None or row.owner_id != owner_id:
        return None
    return row


async def name_taken(
    session: AsyncSession, owner_id: uuid.UUID, name: str, *, besides: uuid.UUID | None = None
) -> bool:
    rows = await session.exec(
        select(CloudAccount.id).where(CloudAccount.owner_id == owner_id, CloudAccount.name == name)
    )
    return any(found != besides for found in rows.all())


async def uses(session: AsyncSession, owner_id: uuid.UUID) -> dict[uuid.UUID, list[SshKeyUse]]:
    """Which of the owner's connections name which account, read off the
    schemas and the stored options as the uses of a key are."""
    names_of = {
        adapter_type.name: options_schema.cloud_account_names(adapter_type.options_schema)
        for adapter_type in registry.all_types()
    }
    rows = await session.exec(select(Connector).where(Connector.owner_id == owner_id))
    found: dict[uuid.UUID, list[SshKeyUse]] = {}
    for connector in rows.all():
        for name in names_of.get(connector.adapter_type, {}):
            try:
                account_id = uuid.UUID(str(connector.config.get(name)))
            except ValueError:
                continue
            found.setdefault(account_id, []).append(SshKeyUse(id=connector.id, name=connector.name))
    return found


async def check_references(
    session: AsyncSession,
    owner_id: uuid.UUID,
    adapter_type: registry.AdapterType,
    config: Mapping[str, Any],
) -> None:
    """Refuse a connection naming an account that is not its owner's or not of
    a kind its field takes (D451). Asked again when it opens."""
    problems = []
    for name, kinds in options_schema.cloud_account_names(adapter_type.options_schema).items():
        if name not in config:
            continue
        try:
            account_id = uuid.UUID(str(config[name]))
        except ValueError:
            continue
        row = await get_own(session, account_id, owner_id)
        if row is None:
            message = say("Choose one of your cloud accounts")
        elif row.kind not in kinds:
            message = say(
                "{name} is not an account of {kind}", name=row.name, kind=kinds_title(kinds)
            )
        else:
            continue
        problems.append({"loc": ["body", "options", name], "msg": message, "type": "value_error"})
    if problems:
        raise HTTPException(status_code=422, detail=problems)


def kinds_title(kinds: tuple[str, ...]) -> str:
    """The products a field takes, as one name or a list of them."""
    return ", ".join(KIND_TITLES[cast(AccountKind, kind)] for kind in kinds)


def public_of(row: CloudAccount, used_by: list[SshKeyUse]) -> CloudAccountPublic:
    kind = cast(AccountKind, row.kind)
    method = method_of(row.method)
    title = method.model_config.get("title") if method is not None else None
    return CloudAccountPublic(
        id=row.id,
        name=row.name,
        kind=kind,
        kind_title=KIND_TITLES[kind],
        method=row.method,
        method_title=say(title) if title else row.method,
        settings=row.settings,
        stored_secrets=sorted(secrets_of(row)),
        ambient=method is not None and method.ambient,
        testable=issuer_for(kind) is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        used_by=used_by,
    )


# Issued secrets, for the whole process (D449).
ISSUED = IssueCache()

# How long one holder keeps an account it read: a pool opening several
# connections at once asks for each, and the database once is enough.
KEPT_SECONDS = 30.0


@dataclass(frozen=True)
class _Read:
    read_at: float
    name: str
    kind: str
    version: int
    ambient: bool
    owner_is_superuser: bool
    settings: CloudAccountSettings

    def __repr__(self) -> str:
        return f"_Read({self.name!r}, <hidden>)"


def _gate(read: _Read) -> None:
    """An account signing in as this server is refused once the installation,
    or the owner's standing, no longer allows it (D452)."""
    if read.ambient and not (installation.CLOUD_AMBIENT_CREDENTIALS and read.owner_is_superuser):
        raise AdapterError(
            "config",
            say("The cloud account {name} signs in as this server, which is no longer allowed", name=read.name),
        )


async def run_issuer[T](kind: AccountKind, name: str, call: Any, *args: Any) -> T:
    """An issuer's call in a thread, any failure it did not word reduced to a
    sentence that names no SDK text (D184)."""
    try:
        result: T = await to_thread.run_sync(call, *args)
        return result
    except AdapterError:
        raise
    except Exception as failure:
        logger.warning("A %s issuer failed with %s", kind, type(failure).__name__)
        raise AdapterError(
            "unknown",
            say(
                "{kind} did not answer for the account {name}; test it in Preferences",
                kind=KIND_TITLES[kind],
                name=name,
            ),
        ) from None


class OwnerCloud:
    """One person's cloud accounts, asked for a secret at every new connection.

    Built for every source and asked only by one whose options name an
    account, so it reads nothing until asked; it opens a session of its own,
    as `OwnerKeys` does, because it is asked from places that hold none.
    """

    def __init__(self, owner_id: uuid.UUID) -> None:
        self._owner_id = owner_id
        self._read: dict[uuid.UUID, _Read] = {}

    async def issue(
        self, account_id: uuid.UUID, kinds: tuple[AccountKind, ...], request: SecretRequest
    ) -> IssuedSecret:
        read = self._read.get(account_id)
        if read is None or time.monotonic() - read.read_at > KEPT_SECONDS:
            read = await self._from_database(account_id)
            self._read[account_id] = read
        if read.kind not in kinds:
            raise AdapterError(
                "config",
                say("{name} is not an account of {kind}", name=read.name, kind=kinds_title(kinds)),
            )
        kind: AccountKind = read.kind
        _gate(read)
        issuer = issuer_for(kind)
        if issuer is None:
            raise AdapterError(
                "config",
                say("This installation cannot sign in with accounts of {kind}", kind=KIND_TITLES[kind]),
            )
        settings = read.settings
        key: Hashable = (account_id, read.version, request)

        async def run() -> IssuedSecret:
            secret: IssuedSecret = await run_issuer(kind, read.name, issuer.issue, settings, request)
            return secret

        return await ISSUED.get(key, run)

    async def _from_database(self, account_id: uuid.UUID) -> _Read:
        async with async_session_maker() as session:
            row = await get_own(session, account_id, self._owner_id)
            owner = await session.get(User, self._owner_id)
        if row is None:
            raise AdapterError(
                "config",
                say("The cloud account this connection signs in with is gone; choose another"),
            )
        method = method_of(row.method)
        return _Read(
            read_at=time.monotonic(),
            name=row.name,
            kind=row.kind,
            version=row.version,
            ambient=method is not None and method.ambient,
            owner_is_superuser=owner is not None and owner.is_superuser,
            settings=settings_of(row),
        )

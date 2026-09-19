"""SSH keys: a person's, kept apart from the connections that sign in with them.

A connection names a key by id; the key itself is a row of its owner's (D146).
One key serves as many connections as its owner points at it, and replacing
it is one change rather than one per connection — which is why keys were given
a store of their own before anybody had pasted one into a connection.

The private half is write-only. It is encrypted under the connector key, like
every other credential of a connection (D4), and nothing reads it but
`OwnerKeys`, at the moment a source signs in. What a person sees of a key is
its public half and its fingerprint, which open nothing.
"""

import uuid
from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, SecretStr
from pydantic import Field as Constrained
from sqlalchemy import Column, DateTime, Index, LargeBinary, String, Text
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as options_schema
from app.adapters import registry
from app.adapters.credentials import SigningKey
from app.adapters.protocol import AdapterError
from app.adapters.ssh.keys import KeyFacts, KeyType
from app.connectors.keyring import KEYRING
from app.connectors.models import Connector
from app.core import crypto
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc

# Whether a key has a passphrase, and where it comes from when it does: kept
# encrypted beside the key, or asked for and held in memory for a while (D147).
PassphraseMode = Literal["none", "stored", "ask"]

# How long an asked-for passphrase is held. A closed set — a free number is a
# field somebody types a week into — and the three the owner chose from.
UnlockMinutes = Literal[15, 60, 480]

# A private key is a few kilobytes; RSA 4096 in OpenSSH form is under four.
# Anything much larger pasted into the box is not a key.
MAX_PRIVATE_KEY_CHARS = 16_384


class SshKey(SQLModel, table=True):
    """One key pair, of which only the public half is ever shown again."""

    __table_args__ = (Index("ix_sshkey_owner", "owner_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    name: str = Field(min_length=1, max_length=255)
    algorithm: str = Field(max_length=64)
    public_key: str = Field(sa_column=Column(Text, nullable=False))
    fingerprint: str = Field(max_length=128)
    # OpenSSH text, itself encrypted under the passphrase when there is one,
    # then under the connector key.
    private_key: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    passphrase_mode: str = Field(
        sa_column=Column(String(8), nullable=False, server_default="none")
    )
    # Only in `stored` mode. An asked-for passphrase is never written down.
    passphrase: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
    )

    def __repr__(self) -> str:
        return f"SshKey({self.id}, {self.name!r}, {self.fingerprint})"


class SshKeyUse(BaseModel):
    """A connection that signs in with the key."""

    id: uuid.UUID
    name: str


class SshKeyPublic(BaseModel):
    """Everything about a key that may be said out loud."""

    id: uuid.UUID
    name: str
    algorithm: str
    public_key: str
    fingerprint: str
    passphrase_mode: PassphraseMode
    # When an asked-for passphrase stops being held, while it is. Absent for a
    # key that is locked, and for one that is never asked about.
    unlocked_until: datetime | None
    created_at: datetime | None
    used_by: list[SshKeyUse]


class _Protection(BaseModel):
    """The passphrase a key will be locked with, and whether it is kept."""

    model_config = ConfigDict(extra="forbid")

    passphrase: SecretStr | None = Constrained(default=None, max_length=1024)
    # Ignored without a passphrase: a key that has none has nothing to keep.
    passphrase_mode: Literal["stored", "ask"] = "ask"


class SshKeyGenerate(_Protection):
    name: str = Constrained(min_length=1, max_length=255)
    key_type: KeyType = "ed25519"


class SshKeyImport(_Protection):
    name: str = Constrained(min_length=1, max_length=255)
    private_key: SecretStr = Constrained(max_length=MAX_PRIVATE_KEY_CHARS)


class SshKeyRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Constrained(min_length=1, max_length=255)


class SshKeyUnlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passphrase: SecretStr = Constrained(max_length=1024)
    minutes: UnlockMinutes = 15


def mode_of(protection: _Protection) -> PassphraseMode:
    if protection.passphrase is None or protection.passphrase.get_secret_value() == "":
        return "none"
    return protection.passphrase_mode


def passphrase_of(protection: _Protection) -> str | None:
    if mode_of(protection) == "none" or protection.passphrase is None:
        return None
    return protection.passphrase.get_secret_value()


async def create(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    name: str,
    private_key: str,
    facts: KeyFacts,
    mode: PassphraseMode,
    passphrase: str | None,
) -> SshKey:
    """Write a prepared key down. An asked-for passphrase is not written."""
    row = SshKey(
        owner_id=owner_id,
        name=name.strip(),
        algorithm=facts.algorithm,
        public_key=facts.public_key,
        fingerprint=facts.fingerprint,
        private_key=crypto.encrypt(private_key.encode(), purpose="connector"),
        passphrase_mode=mode,
        passphrase=(
            crypto.encrypt(passphrase.encode(), purpose="connector")
            if mode == "stored" and passphrase is not None
            else None
        ),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_own(session: AsyncSession, owner_id: uuid.UUID) -> list[SshKey]:
    rows = await session.exec(
        select(SshKey)
        .where(SshKey.owner_id == owner_id)
        .order_by(col(SshKey.created_at))
    )
    return list(rows.all())


async def get_own(
    session: AsyncSession, key_id: uuid.UUID, owner_id: uuid.UUID
) -> SshKey | None:
    """One key of this owner. Somebody else's answers exactly as a missing one."""
    row = await session.get(SshKey, key_id)
    if row is None or row.owner_id != owner_id:
        return None
    return row


def private_key_of(row: SshKey) -> str:
    return crypto.decrypt(row.private_key, purpose="connector").decode()


async def uses(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[uuid.UUID, list[SshKeyUse]]:
    """Which of the owner's connections sign in with which key.

    Read from the owner's connections rather than kept beside the key: the
    connection's options are the one place that says which key it uses, and
    a second record of that would be a second thing to keep in step. Which
    option of which source holds a key id is read off the schemas.
    """
    names_of = {
        adapter_type.name: options_schema.key_reference_names(adapter_type.options_schema)
        for adapter_type in registry.all_types()
    }
    rows = await session.exec(select(Connector).where(Connector.owner_id == owner_id))
    found: dict[uuid.UUID, list[SshKeyUse]] = {}
    for connector in rows.all():
        for name in names_of.get(connector.adapter_type, set()):
            value = connector.config.get(name)
            try:
                key_id = uuid.UUID(str(value))
            except ValueError:
                continue
            found.setdefault(key_id, []).append(
                SshKeyUse(id=connector.id, name=connector.name)
            )
    return found


def public_of(row: SshKey, used_by: list[SshKeyUse]) -> SshKeyPublic:
    mode = cast(PassphraseMode, row.passphrase_mode)
    return SshKeyPublic(
        id=row.id,
        name=row.name,
        algorithm=row.algorithm,
        public_key=row.public_key,
        fingerprint=row.fingerprint,
        passphrase_mode=mode,
        unlocked_until=KEYRING.until(row.id) if mode == "ask" else None,
        created_at=row.created_at,
        used_by=used_by,
    )


class OwnerKeys:
    """The keys of one person, handed to a source that signs in with one.

    Built for every source and asked only by one that signs in with a key, so
    it reads nothing until asked. It opens a session of its own because it is
    asked from places that hold none — the health monitor among them — and
    because a key is read at the moment of signing in, which may be long
    after the request that built the source began.

    Asked on every sign-in and every use of a kept connection, so a key whose
    passphrase has stopped being held stops the source even while a
    connection made with it is still open (D147).
    """

    def __init__(self, owner_id: uuid.UUID) -> None:
        self._owner_id = owner_id

    async def signing_key(self, key_id: uuid.UUID) -> SigningKey:
        async with async_session_maker() as session:
            row = await get_own(session, key_id, self._owner_id)
        if row is None:
            raise AdapterError(
                "config",
                "The SSH key this connection signs in with is gone; choose another",
            )
        if row.passphrase_mode == "ask":
            held = KEYRING.passphrase(row.id)
            if held is None:
                raise AdapterError(
                    "locked",
                    f"The SSH key {row.name} is locked; enter its passphrase to use it",
                )
            return SigningKey(private_key=private_key_of(row), passphrase=held)
        stored = (
            crypto.decrypt(row.passphrase, purpose="connector").decode()
            if row.passphrase_mode == "stored" and row.passphrase is not None
            else None
        )
        return SigningKey(private_key=private_key_of(row), passphrase=stored)

"""What a Redis connection can be asked to do to its keys.

Four things, which is the whole of what people do to a key space by hand:
write one, take one away, give one a deadline, and take the deadline off
again. Everything else — reading, browsing — is the catalog and the reader,
because it is not an action.

Every one of them is declared here with its own parameter model, so a name
that is not on this list does not resolve. The old application dispatched by
`getattr` on the driver, which made every public method an action.
"""

import re
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActsOn,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.redis.keyspace import (
    SEPARATOR,
    NotAKey,
    RedisKeyspace,
    folder_id,
    key_id,
    key_name,
)
from app.adapters.redis.session import RedisSession, resolved
from app.core.access import Access

# What a key may be called. Anything but a newline is legal in Redis itself,
# and almost anything is a bad idea: a name with a space or a control
# character in it is a name nobody can type back, and one written by mistake
# in a form is a key nobody will find again. Letters, digits, the separator
# and the three punctuation marks conventions use.
KEY_PATTERN = re.compile(r"^[A-Za-z0-9:_.\-]{1,512}$")

# How long an expiry may be set for. A day short of sixty-eight years, which
# is where Redis itself stops; the ceiling is here so that a typo produces a
# refusal rather than a key that never expires by accident.
MAX_TTL_SECONDS = 60 * 60 * 24 * 365 * 10


def _key_check(written: str) -> str:
    if not KEY_PATTERN.match(written):
        raise ValueError(
            "A key name may hold letters, digits, colons, dots, dashes and "
            "underscores"
        )
    return written


class NewKeyParams(BaseModel):
    name: str = Field(title="Key")
    value: str = Field(default="", title="Value", max_length=1_000_000)
    # Optional, and empty means "no deadline" rather than "zero seconds".
    ttl_seconds: int | None = Field(
        default=None,
        ge=1,
        le=MAX_TTL_SECONDS,
        title="Expires in (seconds)",
        description="Leave empty to keep it until something removes it",
    )
    overwrite: bool = Field(
        default=False,
        title="Replace it if it already exists",
        description="Otherwise a name already in use is refused",
    )

    _check = field_validator("name")(_key_check)


class DeleteKeyParams(BaseModel):
    """Deleting says nothing but which keys, and those are the selection."""


class ExpiryParams(BaseModel):
    seconds: int = Field(
        ge=1,
        le=MAX_TTL_SECONDS,
        title="Expires in (seconds)",
    )


class PersistParams(BaseModel):
    """Removing a deadline says nothing but which key."""


class _KeyAction:
    """What all four of them need: a way to reach the server."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    def _target(self, node_id: str | None) -> str:
        try:
            return key_name(node_id or "")
        except NotAKey:
            raise ActionRefused(
                "not_applicable", "That is not a key"
            ) from None

    def _folder_of(self, name: str) -> str | None:
        """Which branch of the catalog changed when this key did.

        The folder the key hangs under, or the root when it hangs under none.
        Worked out here rather than on the client, which never takes an id
        apart (D21).
        """
        head, found, _ = name.rpartition(SEPARATOR)
        return folder_id(f"{head}{SEPARATOR}") if found else None


class NewKey(_KeyAction, JsonAction[NewKeyParams]):
    """Write a string key, with an expiry if one is wanted.

    Strings only. A hash, a list or a sorted set built from a form would be a
    form with a repeating group in it, and what people write by hand into a
    key space is overwhelmingly one value under one name. The rest arrive from
    whatever writes them.

    It is also how a value is changed: a name already in use is refused unless
    the form says to replace it, which makes "write this" one action instead
    of a create and an update that would differ only in their refusals.
    """

    name: ClassVar[str] = "new_key"
    title: ClassVar[str] = "New key"
    # On a folder or at the root: a key is made in a place, and a key is not a
    # place. `directory` is what a namespace is listed as.
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"directory"})
    acts_on: ClassVar[ActsOn] = "level"
    params_model = NewKeyParams

    async def run(self, node_id: str | None, params: NewKeyParams) -> ActionResult:
        async with self._session.connection() as client:
            written = await resolved(
                client.set(
                    params.name,
                    params.value,
                    ex=params.ttl_seconds,
                    nx=not params.overwrite,
                )
            )
        if not written:
            # A taken name is a conflict rather than a fault: the same shape a
            # taken folder name answers with.
            raise ActionRefused(
                "conflict", f'A key called "{params.name}" already exists'
            )
        return ActionResult(
            message=f"{params.name} written",
            reload_node_ids=[self._folder_of(params.name)],
        )


class DeleteKey(_KeyAction, JsonAction[DeleteKeyParams]):
    name: ClassVar[str] = "delete_key"
    title: ClassVar[str] = "Delete"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"key"})
    acts_on: ClassVar[ActsOn] = "node"
    destructive: ClassVar[bool] = True
    # One form, many keys: the parameters of a delete say nothing about which
    # key they are for, and five keys deleted are five deletions.
    bulk: ClassVar[bool] = True
    params_model = DeleteKeyParams

    async def run(self, node_id: str | None, params: DeleteKeyParams) -> ActionResult:
        del params
        name = self._target(node_id)
        async with self._session.connection() as client:
            removed = int(await resolved(client.delete(name)))
        if removed == 0:
            # Gone already, which for a key space is ordinary rather than
            # exceptional: something with an expiry may go between the listing
            # and the click.
            return ActionResult(
                message=f"{name} was already gone",
                reload_node_ids=[self._folder_of(name)],
            )
        return ActionResult(
            message=f"{name} deleted", reload_node_ids=[self._folder_of(name)]
        )


class SetExpiry(_KeyAction, JsonAction[ExpiryParams]):
    """Give a key a deadline, or move the one it has."""

    name: ClassVar[str] = "set_expiry"
    title: ClassVar[str] = "Set expiry"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"key"})
    acts_on: ClassVar[ActsOn] = "node"
    # Destructive: what it schedules is the key ceasing to exist, and a person
    # setting one second on the wrong key should be asked first. What it is
    # not is a deletion, so it says what it does rather than letting the
    # client call it one.
    destructive: ClassVar[bool] = True
    question: ClassVar[str | None] = (
        "This key will be removed when the time is up. Set the expiry?"
    )
    bulk: ClassVar[bool] = True
    params_model = ExpiryParams

    async def run(self, node_id: str | None, params: ExpiryParams) -> ActionResult:
        name = self._target(node_id)
        async with self._session.connection() as client:
            done = await resolved(client.expire(name, params.seconds))
        if not done:
            raise ActionRefused("conflict", f"{name} is no longer there")
        return ActionResult(
            message=f"{name} expires in {params.seconds} seconds",
            reload_node_ids=[self._folder_of(name)],
        )


class RemoveExpiry(_KeyAction, JsonAction[PersistParams]):
    """Take the deadline off a key, so it stays until something removes it."""

    name: ClassVar[str] = "remove_expiry"
    title: ClassVar[str] = "Remove expiry"
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"key"})
    acts_on: ClassVar[ActsOn] = "node"
    bulk: ClassVar[bool] = True
    requires: ClassVar[Access] = "write"
    params_model = PersistParams

    async def run(self, node_id: str | None, params: PersistParams) -> ActionResult:
        del params
        name = self._target(node_id)
        async with self._session.connection() as client:
            done = await resolved(client.persist(name))
        if not done:
            # Either it has no expiry or it is gone; neither is a failure, and
            # the state asked for is the state it is in.
            return ActionResult(
                message=f"{name} has no expiry",
                reload_node_ids=[self._folder_of(name)],
            )
        return ActionResult(
            message=f"{name} will be kept",
            reload_node_ids=[self._folder_of(name)],
        )


REDIS_ACTION_TYPES: tuple[type[NewKey | DeleteKey | SetExpiry | RemoveExpiry], ...] = (
    NewKey,
    DeleteKey,
    SetExpiry,
    RemoveExpiry,
)


class RedisActions:
    """The four of them, built once per adapter."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._made = [
            action(session, keyspace) for action in REDIS_ACTION_TYPES
        ]

    def actions(self) -> Sequence[NewKey | DeleteKey | SetExpiry | RemoveExpiry]:
        return self._made


__all__ = [
    "KEY_PATTERN",
    "MAX_TTL_SECONDS",
    "REDIS_ACTION_TYPES",
    "DeleteKey",
    "NewKey",
    "RedisActions",
    "RemoveExpiry",
    "SetExpiry",
    "key_id",
]

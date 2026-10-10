"""What a Redis connection can be asked to do to its keys.

Writing one, taking one away, giving one a deadline, and taking the deadline
off again — the whole of what people do to a key space by hand. Everything
else, reading and browsing, is the catalog and the reader, because it is not
an action.

Writing is six actions rather than one because Redis has six kinds of key and
each is written with a different command and asks for a different thing: a
string is a value, a hash is fields and values, a sorted set is members and
scores. One action with a type to pick would be one form whose only text box
means six things depending on a select above it, and the description under it
could describe at most one of them. Six named actions each say what they take,
which is also what the menu ends up showing.

Every one of them is declared here with its own parameter model, so a name
that is not on this list does not resolve. Dispatching by `getattr` on the
driver would make every public method an action.
"""

import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from app.adapters.actions import (
    ActionRefused,
    ActionResult,
    ActsOn,
    JsonAction,
)
from app.adapters.catalog import NodeKind
from app.adapters.layout import layout
from app.adapters.redis.keyspace import (
    SEPARATOR,
    KeyRef,
    NotAKey,
    PlaceRef,
    RedisKeyspace,
    database_id,
    folder_id,
    key_ref,
    place_ref,
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

# How much one written value may be. A form is not an import: a key that needs
# more than this arrives from whatever writes it.
MAX_VALUE_LENGTH = 1_000_000


def _key_check(written: str) -> str:
    if not KEY_PATTERN.match(written):
        raise ValueError(
            "A key name may hold letters, digits, colons, dots, dashes and "
            "underscores"
        )
    return written


def lines(written: str) -> list[str]:
    """What was typed, one entry per line, blank lines left out.

    The line ending is taken off and nothing else is: a value may legitimately
    start with a space, and a form that quietly trimmed one would write a
    different key from the one that was read back.
    """
    return [line.rstrip("\r") for line in written.split("\n") if line.strip() != ""]


def pairs(written: str) -> list[tuple[str, str]]:
    """`name=value` per line, split at the first `=` only.

    The value may hold anything, `=` included — a URL, a base64 blob — so only
    the first one separates.
    """
    found: list[tuple[str, str]] = []
    for line in lines(written):
        name, sign, value = line.partition("=")
        if sign == "" or name.strip() == "":
            raise ValueError(f'Write each line as name=value, not "{line}"')
        found.append((name.strip(), value))
    return found


def scored(written: str) -> dict[str, float]:
    """`member=score` per line, with the score read as a number."""
    members: dict[str, float] = {}
    for member, score in pairs(written):
        try:
            members[member] = float(score)
        except ValueError:
            raise ValueError(f'"{score}" is not a score') from None
    return members


def _not_empty(parsed: Sequence[Any] | dict[str, Any], noun: str) -> None:
    if len(parsed) == 0:
        raise ValueError(f"A {noun} needs at least one line")


# The shared fields, written once and used by each of the six models. Field
# objects rather than a base class, because the order the fields are declared
# in is the order the form draws them, and inheritance would put every shared
# field above the one thing each action is actually about.


def _name_field() -> Any:
    return Field(
        title="Key",
        description=(
            "Made where the catalog is standing. A name with colons in it "
            "makes the folders it needs."
        ),
        examples=["cache:profile:ada"],
        json_schema_extra=layout(),
    )


def _value_field(title: str, description: str, example: str) -> Any:
    """One value box, and what a filled one looks like.

    The example is shown inside the empty box and goes the moment anything is
    typed. A sentence says how to write a hash; the example shows it, which is
    the difference between reading an instruction and recognising a shape.
    """
    return Field(
        default="",
        title=title,
        description=description,
        examples=[example],
        max_length=MAX_VALUE_LENGTH,
        json_schema_extra=layout(multiline=True),
    )


def _ttl_field() -> Any:
    return Field(
        default=None,
        ge=1,
        le=MAX_TTL_SECONDS,
        title="Expires in (seconds)",
        description="Leave empty to keep it until something removes it",
        json_schema_extra=layout(row="keeping"),
    )


def _overwrite_field() -> Any:
    return Field(
        default=False,
        # No description: a toggle's label is the whole statement, and the
        # form has nowhere to put a second line under one.
        title="Replace it if it already exists",
        json_schema_extra=layout(row="keeping"),
    )


class KeyForm(BaseModel):
    """What every one of the six asks for, whatever it writes.

    `value` is declared here so that it keeps its place in the form — second,
    right under the name — while each action gives it its own title and its
    own description, because "Value" and "One member per line" are not the
    same instruction.
    """

    name: str = _name_field()
    value: str = _value_field("Value", "What to store", "Ada Lovelace")
    # Optional, and empty means "no deadline" rather than "zero seconds".
    ttl_seconds: int | None = _ttl_field()
    overwrite: bool = _overwrite_field()

    _check_name = field_validator("name")(_key_check)


class NewStringParams(KeyForm):
    value: str = _value_field(
        "Value",
        "The text to store, however long",
        '{"handle": "ada", "role": "analyst"}',
    )


class NewHashParams(KeyForm):
    value: str = _value_field(
        "Fields",
        "One per line, written as field=value",
        "name=Ada Lovelace\nborn=1815\nrole=analyst",
    )

    @field_validator("value")
    @classmethod
    def _check(cls, written: str) -> str:
        _not_empty(pairs(written), "hash")
        return written


class NewListParams(KeyForm):
    value: str = _value_field(
        "Items",
        "One per line, in the order they go in",
        "first\nsecond\nthird",
    )

    @field_validator("value")
    @classmethod
    def _check(cls, written: str) -> str:
        _not_empty(lines(written), "list")
        return written


class NewSetParams(KeyForm):
    value: str = _value_field(
        "Members",
        "One per line; repeats count once",
        "ada\nalan\ngrace",
    )

    @field_validator("value")
    @classmethod
    def _check(cls, written: str) -> str:
        _not_empty(lines(written), "set")
        return written


class NewSortedSetParams(KeyForm):
    value: str = _value_field(
        "Members",
        "One per line, written as member=score",
        "ada=3\nalan=1\ngrace=2",
    )

    @field_validator("value")
    @classmethod
    def _check(cls, written: str) -> str:
        _not_empty(scored(written), "sorted set")
        return written


class NewStreamParams(KeyForm):
    value: str = _value_field(
        "First entry",
        "The fields of one entry, written as field=value",
        "who=ada\nwhat=signed in",
    )

    @field_validator("value")
    @classmethod
    def _check(cls, written: str) -> str:
        _not_empty(pairs(written), "stream")
        return written


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
    """What all of them need: a way to reach the right database."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    def _target(self, node_id: str | None) -> KeyRef:
        try:
            return key_ref(node_id)
        except NotAKey:
            raise ActionRefused(
                "not_applicable", "That is not a key"
            ) from None

    def _place(self, node_id: str | None) -> PlaceRef:
        try:
            return place_ref(node_id)
        except NotAKey:
            raise ActionRefused(
                "not_applicable", "A key is made in a database, not on a server"
            ) from None

    def _branch_of(self, ref: KeyRef) -> str:
        """Which branch of the catalog changed when this key did.

        The folder the key hangs under, or the database itself when it hangs
        under none. Worked out here rather than on the client, which never
        takes an id apart (D21).
        """
        head, found, _ = ref.name.rpartition(SEPARATOR)
        if not found:
            return database_id(ref.database)
        return folder_id(ref.database, f"{head}{SEPARATOR}")


class _NewKey[P: KeyForm](_KeyAction, JsonAction[P]):
    """Writing one key of one type, with an expiry if one is wanted.

    The six differ in one method. Everything else — where the key goes, what a
    name already in use means, what happens to the deadline — is the same for
    all of them and is here, so a seventh type is a class with a `_write` in
    it.

    It is also how a value is replaced: a name already in use is refused unless
    the form says to replace it, which makes "write this" one action instead of
    a create and an update that would differ only in their refusals. Replacing
    removes what is there first, so a string may become a hash.
    """

    # On a database or a folder: a key is made in a place, and a key is not a
    # place. `directory` is what a namespace is listed as.
    applies_to: ClassVar[frozenset[NodeKind]] = frozenset({"database", "directory"})
    acts_on: ClassVar[ActsOn] = "level"

    @abstractmethod
    async def _write(self, client: Any, name: str, params: P) -> None:
        """Put the value into a key that is known not to be there."""

    async def run(self, node_id: str | None, params: P) -> ActionResult:
        place = self._place(node_id)
        name = f"{place.prefix}{params.name}"
        async with self._session.connection(place.database) as client:
            # Checked and then written, rather than written conditionally: only
            # `SET` has a "if it is not there" of its own, and the five other
            # commands would each need a transaction to say the same thing. The
            # gap between the two is a race nobody writing keys by hand loses.
            if await resolved(client.exists(name)):
                if not params.overwrite:
                    # A taken name is a conflict rather than a fault: the same
                    # shape a taken folder name answers with.
                    raise ActionRefused(
                        "conflict", f'A key called "{name}" already exists'
                    )
                await resolved(client.delete(name))
            await self._write(client, name, params)
            if params.ttl_seconds is not None:
                await resolved(client.expire(name, params.ttl_seconds))
        return ActionResult(
            message=f"{name} written",
            reload_node_ids=[self._branch_of(KeyRef(place.database, name))],
        )


class NewString(_NewKey[NewStringParams]):
    name: ClassVar[str] = "new_string"
    title: ClassVar[str] = "New string"
    params_model = NewStringParams

    async def _write(self, client: Any, name: str, params: NewStringParams) -> None:
        await resolved(client.set(name, params.value))


class NewHash(_NewKey[NewHashParams]):
    name: ClassVar[str] = "new_hash"
    title: ClassVar[str] = "New hash"
    params_model = NewHashParams

    async def _write(self, client: Any, name: str, params: NewHashParams) -> None:
        # One field per call: redis-py takes several only as `mapping=`, and a
        # dict passed positionally reaches the server as the word "dict".
        for field, value in pairs(params.value):
            await resolved(client.hset(name, field, value))


class NewList(_NewKey[NewListParams]):
    name: ClassVar[str] = "new_list"
    title: ClassVar[str] = "New list"
    params_model = NewListParams

    async def _write(self, client: Any, name: str, params: NewListParams) -> None:
        await resolved(client.rpush(name, *lines(params.value)))


class NewSet(_NewKey[NewSetParams]):
    name: ClassVar[str] = "new_set"
    title: ClassVar[str] = "New set"
    params_model = NewSetParams

    async def _write(self, client: Any, name: str, params: NewSetParams) -> None:
        await resolved(client.sadd(name, *lines(params.value)))


class NewSortedSet(_NewKey[NewSortedSetParams]):
    name: ClassVar[str] = "new_zset"
    title: ClassVar[str] = "New sorted set"
    params_model = NewSortedSetParams

    async def _write(
        self, client: Any, name: str, params: NewSortedSetParams
    ) -> None:
        await resolved(client.zadd(name, scored(params.value)))


class NewStream(_NewKey[NewStreamParams]):
    name: ClassVar[str] = "new_stream"
    title: ClassVar[str] = "New stream"
    params_model = NewStreamParams

    async def _write(self, client: Any, name: str, params: NewStreamParams) -> None:
        # A stream exists only once it holds an entry, so writing one is
        # writing its first entry. The id is the server's: an entry is stamped
        # with when it arrived, and a form asking for that would be asking
        # somebody to invent a timestamp.
        await resolved(client.xadd(name, dict(pairs(params.value))))


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
        ref = self._target(node_id)
        async with self._session.connection(ref.database) as client:
            removed = int(await resolved(client.delete(ref.name)))
        if removed == 0:
            # Gone already, which for a key space is ordinary rather than
            # exceptional: something with an expiry may go between the listing
            # and the click.
            return ActionResult(
                message=f"{ref.name} was already gone",
                reload_node_ids=[self._branch_of(ref)],
            )
        return ActionResult(
            message=f"{ref.name} deleted", reload_node_ids=[self._branch_of(ref)]
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
        ref = self._target(node_id)
        async with self._session.connection(ref.database) as client:
            done = await resolved(client.expire(ref.name, params.seconds))
        if not done:
            raise ActionRefused("conflict", f"{ref.name} is no longer there")
        return ActionResult(
            message=f"{ref.name} expires in {params.seconds} seconds",
            reload_node_ids=[self._branch_of(ref)],
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
        ref = self._target(node_id)
        async with self._session.connection(ref.database) as client:
            done = await resolved(client.persist(ref.name))
        if not done:
            # Either it has no expiry or it is gone; neither is a failure, and
            # the state asked for is the state it is in.
            return ActionResult(
                message=f"{ref.name} has no expiry",
                reload_node_ids=[self._branch_of(ref)],
            )
        return ActionResult(
            message=f"{ref.name} will be kept",
            reload_node_ids=[self._branch_of(ref)],
        )


# The order the menu shows them in: the six ways of writing one, then what can
# be done to one that is there.
REDIS_ACTION_TYPES: tuple[
    type[
        NewString
        | NewHash
        | NewList
        | NewSet
        | NewSortedSet
        | NewStream
        | DeleteKey
        | SetExpiry
        | RemoveExpiry
    ],
    ...,
] = (
    NewString,
    NewHash,
    NewList,
    NewSet,
    NewSortedSet,
    NewStream,
    DeleteKey,
    SetExpiry,
    RemoveExpiry,
)


class RedisActions:
    """All of them, built once per adapter."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._made = [action(session, keyspace) for action in REDIS_ACTION_TYPES]

    def actions(self) -> Sequence[Any]:
        return self._made


__all__ = [
    "KEY_PATTERN",
    "MAX_TTL_SECONDS",
    "REDIS_ACTION_TYPES",
    "DeleteKey",
    "KeyForm",
    "NewHash",
    "NewList",
    "NewSet",
    "NewSortedSet",
    "NewStream",
    "NewString",
    "RedisActions",
    "RemoveExpiry",
    "SetExpiry",
    "lines",
    "pairs",
    "scored",
]

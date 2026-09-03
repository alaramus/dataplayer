"""The key space of a Redis server, walked as a catalog.

Redis has no schemas and no tables. What it has is a flat set of names, which
by universal convention are written with colons — `session:42:token`,
`cache:user:7` — and every tool that shows a key space shows that convention
as a tree. So the catalog groups by the separator: the root lists the first
segment of every key as a folder, and walking into one lists the next.

Two things are deliberate and both are about size. Nothing here ever runs
`KEYS`, which blocks the server for as long as the scan takes; everything is
`SCAN`, which is the command that exists so a client cannot do that. And a
listing stops at a ceiling: a key space of ten million names has no useful
tree, and a page that tried to draw one would fail slowly instead of quickly.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

from app.adapters.catalog import CatalogNode, DirectoryNode, KeyNode
from app.adapters.content import NodeRepresentation
from app.adapters.redis.session import RedisSession, text

# How keys are conventionally named, and therefore how they are grouped. Not
# configurable: a source type whose tree shape is an option is a source type
# with two behaviours to explain, and every Redis convention there is uses
# this one.
SEPARATOR = ":"

# How many keys one listing will walk before it stops. Enough that an ordinary
# key space arrives whole, small enough that a huge one answers quickly with
# what it found rather than slowly with everything.
SCAN_CEILING = 5_000

# How many keys the server is asked for per round trip. A hint rather than a
# limit, which is what Redis documents it as.
SCAN_BATCH = 500

# The ids a client sends back. Prefixed so the two cannot be confused: a key
# may itself be called "user:", and without a mark a listing of it and a
# listing of the folder above it would be the same request.
KEY_PREFIX = "k:"
FOLDER_PREFIX = "f:"

DataType = Literal["string", "list", "set", "zset", "hash", "stream"]

# What opening a key shows: what it holds, as rows. One representation, and
# the same one for every type — a hash is fields and values, a list is
# positions and values, and both are a grid.
AS_ROWS = NodeRepresentation(kind="table", title="View what it holds")

_TYPES: frozenset[str] = frozenset(
    {"string", "list", "set", "zset", "hash", "stream"}
)


class NotAKey(Exception):
    """The id names a folder, or nothing this source issued."""


@dataclass(frozen=True)
class KeyFacts:
    """What one key says about itself before it is opened."""

    name: str
    data_type: DataType
    ttl_seconds: int | None
    length: int | None


def key_id(name: str) -> str:
    return f"{KEY_PREFIX}{name}"


def folder_id(prefix: str) -> str:
    return f"{FOLDER_PREFIX}{prefix}"


def key_name(node_id: str) -> str:
    """The key an id names, or a refusal.

    The one place an id from a client becomes a key name. Nothing else takes
    an id apart, so there is no second door where the same string could mean
    something different (D21).
    """
    if not node_id.startswith(KEY_PREFIX):
        raise NotAKey(node_id)
    return node_id[len(KEY_PREFIX) :]


def folder_prefix(node_id: str | None) -> str:
    """The prefix a folder id names; the empty string for the root."""
    if node_id is None:
        return ""
    if node_id.startswith(FOLDER_PREFIX):
        return node_id[len(FOLDER_PREFIX) :]
    raise NotAKey(node_id)


def is_key(node_id: str | None) -> bool:
    return node_id is not None and node_id.startswith(KEY_PREFIX)


class RedisKeyspace:
    """Listing what is under one prefix, and asking about one key."""

    def __init__(self, session: RedisSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        """Everything one level under this prefix.

        A key whose remainder holds no separator is a key here; one whose
        remainder does is counted into the folder its first segment names.
        Folders come first and both are in the server's own order made
        stable — a scan returns what it happens to meet, and a list that
        reorders itself between two readings is a list nobody can use.
        """
        if is_key(node_id):
            # A key has no children. Said rather than scanned for, because
            # `k:user` and the folder `user:` are different things and a scan
            # would quietly answer for the wrong one.
            return []
        prefix = folder_prefix(node_id)
        names = await self._scan(f"{prefix}*")
        folders: set[str] = set()
        keys: list[str] = []
        for name in names:
            remainder = name[len(prefix) :]
            head, found, _ = remainder.partition(SEPARATOR)
            if found and head:
                folders.add(head)
            else:
                keys.append(name)
        described = await self.describe(sorted(keys))
        return [
            *(
                DirectoryNode(
                    id=folder_id(f"{prefix}{head}{SEPARATOR}"),
                    name=f"{head}{SEPARATOR}",
                    has_children=True,
                    representations=[],
                )
                for head in sorted(folders)
            ),
            *(_node(facts) for facts in described),
        ]

    async def facts_of(self, name: str) -> KeyFacts | None:
        """One key, or nothing when the server no longer holds it."""
        found = await self.describe([name])
        return found[0] if found else None

    async def describe(self, names: Iterable[str]) -> list[KeyFacts]:
        """What each of these keys is, in one round trip rather than three each.

        A key that has gone between the scan and this — which is the ordinary
        state of a cache — is left out rather than reported as missing: it was
        never asked for by name.
        """
        wanted = list(names)
        if not wanted:
            return []
        async with self._session.connection() as client:
            pipe = client.pipeline(transaction=False)
            for name in wanted:
                pipe.type(name)
                pipe.ttl(name)
            answers = await pipe.execute()
            kinds = [text(answers[index * 2]) for index in range(len(wanted))]
            expiries = [answers[index * 2 + 1] for index in range(len(wanted))]
            lengths = await self._lengths(client, wanted, kinds)
        facts: list[KeyFacts] = []
        for name, kind, expiry, length in zip(
            wanted, kinds, expiries, lengths, strict=True
        ):
            if kind not in _TYPES:
                continue
            facts.append(
                KeyFacts(
                    name=name,
                    data_type=cast(DataType, kind),
                    # -1 is "no expiry" and -2 is "no such key"; neither is a
                    # number of seconds, and passing them on as one is how a
                    # screen ends up showing "-1 seconds".
                    ttl_seconds=int(expiry) if int(expiry) >= 0 else None,
                    length=length,
                )
            )
        return facts

    async def _lengths(
        self, client: Any, names: list[str], kinds: list[str]
    ) -> list[int | None]:
        """How big each key is, asked with the command its own type takes.

        One pipeline for all of them. A type this application does not count —
        a stream — answers with nothing rather than with a guess.
        """
        pipe = client.pipeline(transaction=False)
        asked: list[bool] = []
        for name, kind in zip(names, kinds, strict=True):
            command = _LENGTH_COMMANDS.get(kind)
            if command is None:
                asked.append(False)
                continue
            getattr(pipe, command)(name)
            asked.append(True)
        counted = await pipe.execute()
        answers: list[int | None] = []
        found = iter(counted)
        for was_asked in asked:
            answers.append(int(next(found)) if was_asked else None)
        return answers

    async def _scan(self, match: str) -> list[str]:
        """Every key matching this pattern, up to the ceiling.

        `SCAN` rather than `KEYS`, which blocks the server for the whole of
        its own run. The cursor is followed until it comes back to zero or
        enough has been found; a scan may return the same key twice, so the
        answer is deduplicated here rather than trusted.
        """
        seen: set[str] = set()
        cursor = 0
        async with self._session.connection() as client:
            while True:
                cursor, batch = await client.scan(
                    cursor=cursor, match=match, count=SCAN_BATCH
                )
                for raw in batch:
                    seen.add(text(raw))
                if cursor == 0 or len(seen) >= SCAN_CEILING:
                    break
        return list(seen)


# Which command counts a key of each type. A table rather than a chain of
# `elif`, so a type that gains a counter is a line here.
_LENGTH_COMMANDS: dict[str, str] = {
    "string": "strlen",
    "list": "llen",
    "set": "scard",
    "zset": "zcard",
    "hash": "hlen",
}


def _node(facts: KeyFacts) -> KeyNode:
    return KeyNode(
        id=key_id(facts.name),
        name=facts.name.rsplit(SEPARATOR, 1)[-1] or facts.name,
        has_children=False,
        representations=[AS_ROWS],
        data_type=facts.data_type,
        ttl_seconds=facts.ttl_seconds,
        length=facts.length,
    )

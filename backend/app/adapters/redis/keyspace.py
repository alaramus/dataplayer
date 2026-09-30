"""The key space of a Redis server, walked as a catalog.

Redis has no schemas and no tables. What it has is a numbered set of key
spaces, each a flat set of names which by universal convention are written
with colons — `session:42:token`, `cache:user:7` — and every tool that shows
one shows that convention as a tree. So the root of the catalog lists the
server's databases, and inside one the names group by the separator: the first
segment of every key is a folder, and walking into one lists the next.

The database is a grouping and not a wall. The number written into the
connection says which one the catalog opens on; every other one on the server
is beside it, exactly as the schemas of a database are (D91). That is why
every id issued here carries its database: an id is the only thing a client
sends back, so a key in database 3 and a key of the same name in database 0
have to be two different strings.

Two things are deliberate and both are about size. Nothing here ever runs
`KEYS`, which blocks the server for as long as the scan takes; everything is
`SCAN`, which is the command that exists so a client cannot do that. And a
listing stops at a ceiling: a key space of ten million names has no useful
tree, and a page that tried to draw one would fail slowly instead of quickly.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

from redis.exceptions import ResponseError

from app.adapters.catalog import (
    CatalogNode,
    DatabaseNode,
    DirectoryNode,
    KeyNode,
)
from app.adapters.content import NodeRepresentation
from app.adapters.protocol import NodeNotFound
from app.adapters.redis.session import RedisSession, resolved, text

# How keys are conventionally named, and therefore how they are grouped. Not
# configurable: a source type whose tree shape is an option is a source type
# with two behaviours to explain, and every Redis convention there is uses
# this one.
SEPARATOR = ":"

# How many keys one listing will walk before it stops. Enough that an ordinary
# key space arrives whole, small enough that a huge one answers quickly with
# what it found rather than slowly with everything.
SCAN_CEILING = 5_000

# How much of one value this source ever holds at a time. A viewer is a
# preview and a cell is not where a megabyte is typed, so the reader shows a
# string up to here and the writer refuses one longer: the two are the same
# number because a save that silently truncated what was shown is worse than
# a refusal.
MAX_STRING_BYTES = 64 * 1024

# How many keys the server is asked for per round trip. A hint rather than a
# limit, which is what Redis documents it as.
SCAN_BATCH = 500

# How many key spaces a server has when it will not say. Redis is started with
# sixteen unless somebody chose otherwise, and a managed server may refuse
# `CONFIG GET` outright — in which case sixteen is the number every client
# assumes, this one included.
DEFAULT_DATABASES = 16

# The ids a client sends back, each carrying the database it belongs to.
# Prefixed so the three cannot be confused: a key may itself be called
# "user:", and without a mark a listing of it and a listing of the folder
# above it would be the same request.
DATABASE_PREFIX = "d"
KEY_PREFIX = "k"
FOLDER_PREFIX = "f"

# Read strictly. An id reaching this module came from a client, and a string
# that is nearly one of ours must be refused rather than nearly understood.
_DATABASE_ID = re.compile(r"^d(\d{1,3})$")
_KEY_ID = re.compile(r"^k(\d{1,3}):(.+)$", re.DOTALL)
_FOLDER_ID = re.compile(r"^f(\d{1,3}):(.*)$", re.DOTALL)

DataType = Literal["string", "list", "set", "zset", "hash", "stream"]

# What opening a key shows: what it holds, as rows. One representation, and
# the same one for every type — a hash is fields and values, a list is
# positions and values, and both are a grid.
AS_ROWS = NodeRepresentation(kind="table", title="View what it holds")

_TYPES: frozenset[str] = frozenset(
    {"string", "list", "set", "zset", "hash", "stream"}
)


class NotAKey(Exception):
    """The id names a folder, a database, or nothing this source issued."""


@dataclass(frozen=True)
class KeyFacts:
    """What one key says about itself before it is opened."""

    name: str
    data_type: DataType
    ttl_seconds: int | None
    length: int | None


@dataclass(frozen=True)
class KeyRef:
    """One key, and the database holding it."""

    database: int
    name: str


@dataclass(frozen=True)
class PlaceRef:
    """Somewhere a key can be listed or written: a database, or a folder in one.

    The two are one thing here because they differ only in the prefix — the
    root of a database is the empty prefix — and every caller that lists or
    writes wants exactly this pair.
    """

    database: int
    prefix: str


def database_id(database: int) -> str:
    return f"{DATABASE_PREFIX}{database}"


def key_id(database: int, name: str) -> str:
    return f"{KEY_PREFIX}{database}{SEPARATOR}{name}"


def folder_id(database: int, prefix: str) -> str:
    return f"{FOLDER_PREFIX}{database}{SEPARATOR}{prefix}"


def folders_above(name: str) -> list[str]:
    """The folder prefixes a name lies in, outermost first, by the listing's rule.

    A segment is a folder when a separator follows it and it is not empty, so
    `a::b` lies in `a:` and is a key there. For a folder's own prefix the
    last one is the folder itself.
    """
    found: list[str] = []
    prefix = ""
    while True:
        head, separated, _ = name[len(prefix) :].partition(SEPARATOR)
        if not (separated and head):
            return found
        prefix = f"{prefix}{head}{SEPARATOR}"
        found.append(prefix)


def pattern_under(prefix: str) -> str:
    """The `SCAN` pattern for every key under a prefix, the prefix taken literally.

    A glob character in a key's name — `[`, `*`, `?` — would otherwise make
    the pattern mean something else than the folder.
    """
    escaped = "".join(f"\\{char}" if char in "\\*?[]" else char for char in prefix)
    return f"{escaped}*"


def is_direct(name: str, prefix: str) -> bool:
    """Whether a name under a prefix is a key of that folder, not of one below."""
    head, separated, _ = name[len(prefix) :].partition(SEPARATOR)
    return not (separated and head)


def is_folder_prefix(prefix: str) -> bool:
    """Whether the listing could have issued this prefix as a folder."""
    above = folders_above(prefix)
    return bool(above) and above[-1] == prefix


def key_ref(node_id: str | None) -> KeyRef:
    """The key an id names, or a refusal.

    The one place an id from a client becomes a database number and a key
    name. Nothing else takes an id apart, so there is no second door where the
    same string could mean something different (D21).
    """
    found = _KEY_ID.match(node_id or "")
    if found is None:
        raise NotAKey(node_id)
    return KeyRef(database=int(found.group(1)), name=found.group(2))


def place_ref(node_id: str | None) -> PlaceRef:
    """The database, or the folder in one, that an id names.

    The root of the connection is not one: what is there is the list of
    databases, and a key belongs in a database rather than on a server.
    """
    database = _DATABASE_ID.match(node_id or "")
    if database is not None:
        return PlaceRef(database=int(database.group(1)), prefix="")
    folder = _FOLDER_ID.match(node_id or "")
    if folder is None:
        raise NotAKey(node_id)
    return PlaceRef(database=int(folder.group(1)), prefix=folder.group(2))


def place_of(node_id: str | None) -> PlaceRef:
    """The same, as an answer about a node rather than about a string.

    `place_ref` refuses a string this source did not issue; a caller holding
    an id from a client wants that refusal to reach the client as "there is no
    such node", which is what it is.
    """
    try:
        return place_ref(node_id)
    except NotAKey:
        raise NodeNotFound(node_id or "") from None


def key_of(node_id: str | None) -> KeyRef:
    """And the same for a key."""
    try:
        return key_ref(node_id)
    except NotAKey:
        raise NodeNotFound(node_id or "") from None


def is_key(node_id: str | None) -> bool:
    return _KEY_ID.match(node_id or "") is not None


def is_database(node_id: str | None) -> bool:
    return _DATABASE_ID.match(node_id or "") is not None


class RedisKeyspace:
    """Listing what is under one prefix, and asking about one key."""

    def __init__(self, session: RedisSession) -> None:
        self._session = session

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        """The databases at the root, and one level of names inside one.

        A key whose remainder holds no separator is a key here; one whose
        remainder does is counted into the folder its first segment names.
        Folders come first and both are in the server's own order made
        stable — a scan returns what it happens to meet, and a list that
        reorders itself between two readings is a list nobody can use.
        """
        if node_id is None:
            return await self.databases()
        if is_key(node_id):
            # A key has no children. Said rather than scanned for, because
            # `k0:user` and the folder `user:` are different things and a scan
            # would quietly answer for the wrong one.
            return []
        place = place_of(node_id)
        names = await self._scan(place.database, pattern_under(place.prefix))
        folders: set[str] = set()
        keys: list[str] = []
        for name in names:
            remainder = name[len(place.prefix) :]
            head, found, _ = remainder.partition(SEPARATOR)
            if found and head:
                folders.add(head)
            else:
                keys.append(name)
        described = await self.describe(place.database, sorted(keys))
        return [
            *(
                DirectoryNode(
                    id=folder_id(place.database, f"{place.prefix}{head}{SEPARATOR}"),
                    name=f"{head}{SEPARATOR}",
                    has_children=True,
                    representations=[],
                )
                for head in sorted(folders)
            ),
            *(key_node(place.database, facts) for facts in described),
        ]

    async def databases(self) -> list[CatalogNode]:
        """Every key space this server has, with the one to open on marked.

        How many there are is asked of the server rather than assumed, because
        it is a setting; a server that refuses to say — which managed ones do —
        gets the number everything else assumes. How full each one is comes
        from a single `INFO`, so listing sixteen databases costs one round trip
        rather than sixteen.
        """
        async with self._session.connection() as client:
            count = await self._database_count(client)
            filled = await self._key_counts(client)
        opens_on = self._session.database
        return [
            DatabaseNode(
                id=database_id(index),
                name=f"db{index}",
                has_children=True,
                representations=[],
                preferred=index == opens_on,
                keys=filled.get(index, 0),
            )
            for index in range(max(count, opens_on + 1))
        ]

    async def _database_count(self, client: Any) -> int:
        try:
            answered = await resolved(client.config_get("databases"))
        except ResponseError:
            # `CONFIG` is disabled on plenty of managed servers. Not a failure
            # of the connection, so nothing is raised: the catalog offers the
            # usual sixteen instead of nothing at all.
            return DEFAULT_DATABASES
        written = {text(name): text(value) for name, value in dict(answered).items()}
        number = written.get("databases", "")
        return int(number) if number.isdigit() else DEFAULT_DATABASES

    async def _key_counts(self, client: Any) -> dict[int, int]:
        """How many keys each database holds, as the server's own summary.

        `INFO keyspace` names only the databases that hold anything, so a
        database missing from the answer is an empty one rather than an
        unknown one.
        """
        answered = await resolved(client.info("keyspace"))
        counts: dict[int, int] = {}
        for raw_name, raw_facts in dict(answered).items():
            name = text(raw_name)
            if not name.startswith("db") or not name[2:].isdigit():
                continue
            found = _keys_in(raw_facts)
            if found is not None:
                counts[int(name[2:])] = found
        return counts

    async def facts_of(self, database: int, name: str) -> KeyFacts | None:
        """One key, or nothing when the server no longer holds it."""
        found = await self.describe(database, [name])
        return found[0] if found else None

    async def describe(
        self, database: int, names: Iterable[str]
    ) -> list[KeyFacts]:
        """What each of these keys is, in one round trip rather than three each.

        A key that has gone between the scan and this — which is the ordinary
        state of a cache — is left out rather than reported as missing: it was
        never asked for by name.
        """
        wanted = list(names)
        if not wanted:
            return []
        async with self._session.connection(database) as client:
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

    async def _scan(self, database: int, match: str) -> list[str]:
        names, _ = await self.scan_names(database, match, SCAN_CEILING)
        return names

    async def scan_names(
        self, database: int, match: str, ceiling: int
    ) -> tuple[list[str], bool]:
        """Every key matching this pattern up to a ceiling, and whether that was all.

        `SCAN` rather than `KEYS`, which blocks the server for the whole of
        its own run. The cursor is followed until it comes back to zero or
        enough has been found; a scan may return the same key twice, so the
        answer is deduplicated here rather than trusted.
        """
        seen: set[str] = set()
        cursor = 0
        async with self._session.connection(database) as client:
            while True:
                cursor, batch = await client.scan(
                    cursor=cursor, match=match, count=SCAN_BATCH
                )
                for raw in batch:
                    seen.add(text(raw))
                if cursor == 0 or len(seen) >= ceiling:
                    break
        return list(seen), cursor == 0


def _keys_in(facts: Any) -> int | None:
    """The key count out of one line of `INFO keyspace`, however it arrives.

    redis-py parses the line into a mapping; a server or a version that hands
    back `keys=3,expires=0` unparsed is read here rather than trusted to have
    been read already.
    """
    if isinstance(facts, dict):
        found = facts.get("keys", facts.get(b"keys"))
        return int(found) if found is not None else None
    written = text(facts)
    for part in written.split(","):
        name, _, value = part.partition("=")
        if name.strip() == "keys" and value.strip().isdigit():
            return int(value.strip())
    return None


# Which command counts a key of each type. A table rather than a chain of
# `elif`, so a type that gains a counter is a line here.
_LENGTH_COMMANDS: dict[str, str] = {
    "string": "strlen",
    "list": "llen",
    "set": "scard",
    "zset": "zcard",
    "hash": "hlen",
}


def key_node(database: int, facts: KeyFacts) -> KeyNode:
    return KeyNode(
        id=key_id(database, facts.name),
        name=facts.name.rsplit(SEPARATOR, 1)[-1] or facts.name,
        has_children=False,
        representations=[AS_ROWS],
        data_type=facts.data_type,
        ttl_seconds=facts.ttl_seconds,
        length=facts.length,
    )

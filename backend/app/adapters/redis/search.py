"""Finding keys by name, from the search field (D202).

A `SCAN` bounded by how many keys it looks at and by the clock, never by how
many matched: a word that matches nothing would otherwise walk the whole key
space before saying so. `MATCH` is case-sensitive and the words are not, so
names are case-folded and matched here; building `[aA]` classes out of typed
text would be compiling it (D2c). A database `INFO` says is empty is not
scanned at all.

The tree has no node path (D91). A key found here carries its ancestors,
worked out from its name by the listing's rule, so it can still be shown where
its tree would put it — by the header's field and by the tree's own search.
"""

from collections.abc import AsyncIterator, Iterable

from app.adapters.protocol import AdapterError
from app.adapters.redis.keyspace import (
    SCAN_BATCH,
    RedisKeyspace,
    ancestors_of,
    database_id,
    folder_id,
    folders_above,
    is_key,
    key_node,
    pattern_under,
    place_of,
)
from app.adapters.redis.session import RedisSession, text
from app.adapters.search import (
    Kept,
    KeptName,
    NameBatch,
    NodeMatch,
    NodeSearchRequest,
    NodeSearchResult,
    SearchBounds,
    class_of_name,
    class_rank,
    out_of_time,
    words_of,
)
from app.core.translation import say

# How many keys one search looks at, over every database it walks. A bound on
# the walk rather than on the matches, so a rare word costs what a common one
# does.
MAX_LOOKED_AT = 200_000


class RedisSearch:
    """Keys whose whole names hold every word, below a database or a folder."""

    def __init__(self, session: RedisSession, keyspace: RedisKeyspace) -> None:
        self._session = session
        self._keyspace = keyspace

    async def search_nodes(
        self, request: NodeSearchRequest, bounds: SearchBounds | None = None
    ) -> NodeSearchResult:
        words = words_of(request.query)
        if not words:
            raise ValueError(say("A search needs something to look for"))
        if is_key(request.node_id):
            raise ValueError(say("A search starts in a database or a folder"))
        place = None if request.node_id is None else place_of(request.node_id)

        async with self._session.connection() as client:
            counts = await self._keyspace.key_counts(client)
        if place is None:
            # Where the connection opens first, then the rest in order.
            opens_on = self._session.database
            databases = sorted(counts, key=lambda one: (one != opens_on, one))
        else:
            databases = [place.database] if counts.get(place.database) else []
        prefix = "" if place is None else place.prefix
        # The server's, whatever this search was scoped to: what the next
        # search's cost is stated from, and that one may scan all of it.
        extent = sum(counts.values())

        kept: Kept[tuple[int, int, str]] = Kept(request.limit)
        added: set[tuple[int, str]] = set()
        looked = 0
        notice: str | None = None
        broken: AdapterError | None = None
        for database in databases:
            if notice is not None or broken is not None:
                break
            try:
                async with self._session.connection(database) as client:
                    cursor = 0
                    while True:
                        if bounds is not None and bounds.over():
                            notice = out_of_time(looked, "keys")
                            break
                        if looked >= MAX_LOOKED_AT:
                            notice = say(
                                "More than {count} keys were looked at; the search stopped there",
                                count=f"{MAX_LOOKED_AT:,}",
                            )
                            break
                        cursor, batch = await client.scan(
                            cursor=cursor,
                            match=pattern_under(prefix) if prefix else None,
                            count=SCAN_BATCH,
                        )
                        for raw in batch:
                            looked += 1
                            name = text(raw)
                            match_class = class_of_name(words, name)
                            # A scan may return a key twice.
                            if (
                                match_class is None
                                or (database, name) in added
                                or not kept.wants(match_class)
                            ):
                                continue
                            added.add((database, name))
                            kept.add(match_class, (class_rank(match_class), database, name))
                        if cursor == 0:
                            break
            except AdapterError as failure:
                broken = failure

        found = sorted(kept.items())
        try:
            matches = await self._matches((database, name) for _, database, name in found)
        except AdapterError as failure:
            # Described by the server they were found on; gone with it.
            matches = []
            broken = broken or failure
        if broken is not None:
            return NodeSearchResult(
                matches=matches,
                complete=False,
                notice=broken.message,
                error_kind=broken.error_kind,
                extent=extent,
            )
        if notice is None and kept.dropped:
            notice = say(
                "More than {limit} matched; the best {limit} are shown", limit=request.limit
            )
        return NodeSearchResult(
            matches=matches, complete=notice is None, notice=notice, extent=extent
        )

    async def _matches(self, found: Iterable[tuple[int, str]]) -> list[NodeMatch]:
        """The kept keys as the listing builds them, one round trip per database.

        A key that expired since the scan met it is left out, as the listing
        leaves it out.
        """
        by_database: dict[int, list[str]] = {}
        order: list[tuple[int, str]] = []
        for database, name in found:
            by_database.setdefault(database, []).append(name)
            order.append((database, name))
        described = {
            (database, facts.name): facts
            for database, names in by_database.items()
            for facts in await self._keyspace.describe(database, names)
        }
        matches: list[NodeMatch] = []
        for database, name in order:
            facts = described.get((database, name))
            if facts is None:
                continue
            folders = folders_above(name)
            parent = folder_id(database, folders[-1]) if folders else database_id(database)
            matches.append(
                NodeMatch(
                    node=key_node(database, facts),
                    parent_id=parent,
                    location=" · ".join([f"db{database}", *folders[-1:]]),
                    ancestors=ancestors_of(database, name),
                    full_name=name,
                )
            )
        return matches

    async def enumerate_names(
        self, limit: int, bounds: SearchBounds
    ) -> AsyncIterator[NameBatch]:
        """Every key of every database, for a kept list (D213).

        A database is one scope: a scan that broke off leaves what was kept
        of it alone. Each batch of a scan is described in one round trip, as
        the search describes what it found.
        """
        async with self._session.connection() as client:
            counts = await self._keyspace.key_counts(client)
        read = 0
        for database in sorted(counts):
            seen: set[str] = set()
            try:
                async with self._session.connection(database) as client:
                    cursor = 0
                    while True:
                        if bounds.over():
                            yield NameBatch(
                                unread=[database_id(database)],
                                notice=out_of_time(read, "keys"),
                            )
                            return
                        cursor, batch = await client.scan(cursor=cursor, count=SCAN_BATCH)
                        fresh = [name for raw in batch if (name := text(raw)) not in seen]
                        seen.update(fresh)
                        if read + len(fresh) > limit:
                            fresh = fresh[: limit - read]
                        matches = await self._matches((database, name) for name in fresh)
                        read += len(fresh)
                        yield NameBatch(
                            names=[
                                KeptName(
                                    node=match.node,
                                    parent_id=match.parent_id,
                                    location=match.location,
                                    ancestors=match.ancestors,
                                    full_name=match.full_name,
                                    scope=database_id(database),
                                )
                                for match in matches
                            ]
                        )
                        if read >= limit and cursor != 0:
                            yield NameBatch(
                                unread=[database_id(database)],
                                notice=say(
                                    "More than {limit} keys; the first {limit} are kept",
                                    limit=f"{limit:,}",
                                ),
                            )
                            return
                        if cursor == 0:
                            break
            except AdapterError:
                # One database that dropped is one scope unread, not a failed
                # pass: what was kept of the others is still true.
                yield NameBatch(unread=[database_id(database)])

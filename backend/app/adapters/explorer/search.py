"""Finding a file below one folder: by its name, or by what is in it.

Breadth first, so what is near is found first and a search that stops at a
ceiling stops at the far end rather than in a random branch. The walk is
bounded three ways — how many matches are wanted, how many entries may be
looked at and how deep it may go — and says which of them stopped it (D76).

A search by name opens nothing: a name is compared, a directory is listed, and
the nodes that come back are built by the catalog's own builder, so a row found
by a search is the row the listing would have shown.

A search by content opens everything it is allowed to. That is the expensive
half and it is a separate capability for that reason — the client asks for it
deliberately and warns before it does. Its own bounds are on top of the walk's:
a file larger than a ceiling is skipped, one that looks binary is skipped, and
the whole search stops after so many bytes however many files that took.
"""

import io
from collections import deque
from dataclasses import dataclass

from anyio import to_thread

from app.adapters.explorer.binary import SNIFF_BYTES, bytes_look_binary
from app.adapters.explorer.catalog import node_of
from app.adapters.explorer.storage import Entry, Place, Storage, node_id_of
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.search import (
    MAX_EXCERPT_CHARACTERS,
    NodeMatch,
    NodeSearchRequest,
    NodeSearchResult,
)

# How many entries one search may look at. A personal directory is not a
# filesystem, and this is fifty times what one level may hold.
MAX_SCANNED = 100_000

# How far down it may go. A tree deeper than this is a mistake or a loop, and
# the walk refuses to follow either forever.
MAX_DEPTH = 24

# What reading inside files may cost is the storage's to say
# (`Storage.search_limits`): per file — a file larger than that is somebody's
# data set rather than something they are grepping — and for the whole search,
# so that a folder of a thousand large files stops rather than running for
# minutes.


@dataclass(frozen=True)
class _Level:
    """One folder waiting to be looked at, and how far down it is."""

    place: Place
    node_id: str | None
    depth: int


class ExplorerSearch:
    """The `catalog/search` capability of a tree of files."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def search_nodes(self, request: NodeSearchRequest) -> NodeSearchResult:
        return await to_thread.run_sync(self._search, request)

    async def search_contents(self, request: NodeSearchRequest) -> NodeSearchResult:
        """The same walk, deciding by what is in a file rather than its name."""
        return await to_thread.run_sync(self._search, request, True)

    def _search(
        self, request: NodeSearchRequest, inside: bool = False
    ) -> NodeSearchResult:
        # Containment is judged before anything is listed, as it is for every
        # other read of this source (D8).
        start = self._storage.place(request.node_id)
        found = self._storage.entry(start)
        if found is None:
            # The same two answers the listing gives: the root missing is the
            # connector being wrong, a node missing is a node being gone.
            if request.node_id is None:
                raise AdapterError(
                    "config", "The directory of this connector does not exist"
                )
            raise NodeNotFound(request.node_id)
        if not found.is_directory:
            raise ValueError("A search starts in a folder")

        needle = request.query.strip().casefold()
        if needle == "":
            raise ValueError("A search needs something to look for")

        # A match carries the folder it sits in twice over: the opaque id the
        # client sends back to stand there, and the same thing as this source
        # words it. The root is the empty string — it has no name of its own,
        # and what the catalog draws there is the name of the connection.
        limits = self._storage.search_limits
        matches: list[NodeMatch] = []
        scanned = 0
        read_bytes = 0
        deepest = False
        unread = 0
        queue: deque[_Level] = deque(
            [_Level(place=start, node_id=request.node_id or None, depth=0)]
        )

        while queue:
            level = queue.popleft()
            try:
                entries = self._storage.entries(level.place)
            except OSError:
                # A folder that cannot be read is not a failed search: the rest
                # of the tree is still an answer, and this one is left out the
                # way the listing leaves out what it cannot describe.
                continue
            for entry in entries:
                scanned += 1
                if scanned > MAX_SCANNED:
                    return _stopped(
                        matches,
                        f"More than {MAX_SCANNED:,} entries were looked "
                        "at; the search stopped there",
                    )

                excerpt: str | None = None
                matched = False
                if inside:
                    if read_bytes > limits.total_bytes:
                        return _stopped(
                            matches,
                            f"More than {_megabytes(limits.total_bytes)} MB "
                            "was read; the search stopped there",
                        )
                    looked = self._look_inside(entry, needle)
                    if looked is _UNREADABLE:
                        unread += 1
                    elif looked is not None:
                        matched = True
                        excerpt = looked
                    if not entry.is_directory:
                        read_bytes += entry.size_bytes
                else:
                    matched = needle in entry.name.casefold()

                if matched:
                    matches.append(
                        NodeMatch(
                            node=node_of(self._storage, entry),
                            parent_id=level.node_id,
                            location=level.node_id or "",
                            excerpt=excerpt,
                        )
                    )
                    if len(matches) == request.limit:
                        return _stopped(
                            matches,
                            f"The first {request.limit} matches; there may be more",
                        )

                if not _walkable(entry):
                    continue
                if level.depth + 1 > MAX_DEPTH:
                    deepest = True
                    continue
                queue.append(
                    _Level(
                        place=entry.place,
                        node_id=node_id_of(entry.place),
                        depth=level.depth + 1,
                    )
                )

        if deepest:
            return _stopped(
                matches,
                f"Folders deeper than {MAX_DEPTH} levels were not looked at",
            )
        if unread:
            # Complete about what it read, and honest about what it did not: a
            # picture and a database dump were not searched, and saying so is
            # what stops "no matches" from meaning "not in this folder".
            return NodeSearchResult(
                matches=matches,
                complete=True,
                notice=(
                    f"{unread} files were not read: they are binary or larger "
                    f"than {_megabytes(limits.file_bytes)} MB"
                ),
            )
        return NodeSearchResult(matches=matches, complete=True)

    def _look_inside(self, entry: Entry, needle: str) -> str | None:
        """The line these words are on in this file, or nothing, or unreadable.

        A line at a time, so a file is never held whole, and case-insensitively,
        which is what the name search does and therefore what somebody typing
        the same words expects. A link is not read through: the walk does not
        follow one either.
        """
        if entry.is_directory or entry.is_link:
            return None
        if entry.size_bytes > self._storage.search_limits.file_bytes:
            return _UNREADABLE
        try:
            with self._storage.open(entry.place) as raw:
                if bytes_look_binary(raw.read(SNIFF_BYTES)):
                    return _UNREADABLE
                raw.seek(0)
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
                for line in text:
                    if needle in line.casefold():
                        return line.strip()[:MAX_EXCERPT_CHARACTERS]
        except OSError:
            return _UNREADABLE
        return None


# Told apart from "no match here": a file nobody could read is worth counting,
# and a file that simply does not hold the words is not.
_UNREADABLE = "\x00unreadable"


def _walkable(entry: Entry) -> bool:
    """Whether the walk goes into this entry.

    A symbolic link is never followed, whether or not it stays inside the root:
    an alias can duplicate a whole tree into the results or point back at its
    own parent, and a search is exactly where a loop would be met. It is the
    same refusal the recursive archive walk makes, for the same reason.
    """
    return entry.is_directory and not entry.is_link


def _megabytes(size: int) -> int:
    return size // (1024 * 1024)


def _stopped(matches: list[NodeMatch], notice: str) -> NodeSearchResult:
    return NodeSearchResult(matches=matches, complete=False, notice=notice)

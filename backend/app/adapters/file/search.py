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

import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from anyio import to_thread

from app.adapters.file.binary import looks_binary
from app.adapters.file.catalog import node_from_entry
from app.adapters.file.session import FileSession
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

# What reading inside files may cost. The first is per file — a file larger
# than this is somebody's data set rather than something they are grepping —
# and the second is for the whole search, so that a folder of a thousand large
# files stops rather than running for minutes.
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_READ_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class _Level:
    """One folder waiting to be looked at, and how far down it is."""

    path: Path
    node_id: str | None
    depth: int


class FileSearch:
    """The `catalog/search` capability of the file source."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

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
        start = self._session.resolve(request.node_id)
        if not start.exists():
            # The same two answers the listing gives: the root missing is the
            # connector being wrong, a node missing is a node being gone.
            if request.node_id is None:
                raise AdapterError(
                    "config", "The directory of this connector does not exist"
                )
            raise NodeNotFound(request.node_id)
        if not start.is_dir():
            raise ValueError("A search starts in a folder")

        needle = request.query.strip().casefold()
        if needle == "":
            raise ValueError("A search needs something to look for")

        # A match carries the folder it sits in twice over: the opaque id the
        # client sends back to stand there, and the same thing as this source
        # words it. The root is the empty string — it has no name of its own,
        # and what the catalog draws there is the name of the connection.
        matches: list[NodeMatch] = []
        scanned = 0
        read_bytes = 0
        deepest = False
        unread = 0
        queue: deque[_Level] = deque(
            [_Level(path=start, node_id=request.node_id or None, depth=0)]
        )

        while queue:
            level = queue.popleft()
            try:
                with os.scandir(level.path) as entries:
                    for entry in entries:
                        scanned += 1
                        if scanned > MAX_SCANNED:
                            return _stopped(
                                matches,
                                f"More than {MAX_SCANNED:,} entries were looked "
                                "at; the search stopped there",
                            )

                        # The name decides first, and only a match is built
                        # into a node: describing every entry of a hundred
                        # thousand would cost a stat and a listing each, to
                        # answer a question a string comparison answers.
                        excerpt: str | None = None
                        found = False
                        if inside:
                            if read_bytes > MAX_READ_BYTES:
                                return _stopped(
                                    matches,
                                    f"More than {MAX_READ_BYTES // (1024 * 1024)} MB "
                                    "was read; the search stopped there",
                                )
                            looked = _look_inside(entry, needle)
                            if looked is _UNREADABLE:
                                unread += 1
                            elif looked is not None:
                                found = True
                                excerpt = looked
                            read_bytes += _size_of(entry)
                        else:
                            found = needle in entry.name.casefold()

                        if found:
                            node = node_from_entry(self._session, entry)
                            # None is a link out of the root, or an entry that
                            # has gone since the listing began.
                            if node is not None:
                                matches.append(
                                    NodeMatch(
                                        node=node,
                                        parent_id=level.node_id,
                                        location=level.node_id or "",
                                        excerpt=excerpt,
                                    )
                                )
                                if len(matches) == request.limit:
                                    return _stopped(
                                        matches,
                                        f"The first {request.limit} matches; "
                                        "there may be more",
                                    )

                        if not _walkable(entry):
                            continue
                        if level.depth + 1 > MAX_DEPTH:
                            deepest = True
                            continue
                        child = Path(entry.path)
                        queue.append(
                            _Level(
                                path=child,
                                node_id=self._session.relative_id(child),
                                depth=level.depth + 1,
                            )
                        )
            except OSError:
                # A folder that cannot be read is not a failed search: the rest
                # of the tree is still an answer, and this one is left out the
                # way the listing leaves out what it cannot stat.
                continue

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
                    f"than {MAX_FILE_BYTES // (1024 * 1024)} MB"
                ),
            )
        return NodeSearchResult(matches=matches, complete=True)


# Told apart from "no match here": a file nobody could read is worth counting,
# and a file that simply does not hold the words is not.
_UNREADABLE = "\x00unreadable"


def _size_of(entry: os.DirEntry[str]) -> int:
    try:
        return entry.stat(follow_symlinks=False).st_size
    except OSError:
        return 0


def _look_inside(entry: os.DirEntry[str], needle: str) -> str | None:
    """The line these words are on in this file, or nothing, or unreadable.

    A line at a time, so a file is never held whole, and case-insensitively,
    which is what the name search does and therefore what somebody typing the
    same words expects.
    """
    try:
        if not entry.is_file(follow_symlinks=False):
            return None
    except OSError:
        return None
    path = Path(entry.path)
    if _size_of(entry) > MAX_FILE_BYTES:
        return _UNREADABLE
    try:
        if looks_binary(path):
            return _UNREADABLE
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if needle in line.casefold():
                    return line.strip()[:MAX_EXCERPT_CHARACTERS]
    except OSError:
        return _UNREADABLE
    return None


def _walkable(entry: os.DirEntry[str]) -> bool:
    """Whether the walk goes into this entry.

    A symbolic link is never followed, whether or not it stays inside the root:
    an alias can duplicate a whole tree into the results or point back at its
    own parent, and a search is exactly where a loop would be met. It is the
    same refusal the recursive archive walk makes, for the same reason.
    """
    try:
        return entry.is_dir() and not entry.is_symlink()
    except OSError:
        return False


def _stopped(matches: list[NodeMatch], notice: str) -> NodeSearchResult:
    return NodeSearchResult(matches=matches, complete=False, notice=notice)


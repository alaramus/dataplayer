"""Finding a file by its name, below one folder.

Breadth first, so what is near is found first and a search that stops at a
ceiling stops at the far end rather than in a random branch. The walk is
bounded three ways — how many matches are wanted, how many entries may be
looked at and how deep it may go — and says which of them stopped it (D76).

Nothing here is opened. A name is compared, a directory is listed, and the
nodes that come back are built by the catalog's own builder, so a row found by
a search is the row the listing would have shown.
"""

import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from anyio import to_thread

from app.adapters.file.catalog import node_from_entry
from app.adapters.file.session import FileSession
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.search import NodeMatch, NodeSearchRequest, NodeSearchResult

# How many entries one search may look at. A personal directory is not a
# filesystem, and this is fifty times what one level may hold.
MAX_SCANNED = 100_000

# How far down it may go. A tree deeper than this is a mistake or a loop, and
# the walk refuses to follow either forever.
MAX_DEPTH = 24


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

    def _search(self, request: NodeSearchRequest) -> NodeSearchResult:
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
        deepest = False
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
                        if needle in entry.name.casefold():
                            node = node_from_entry(self._session, entry)
                            # None is a link out of the root, or an entry that
                            # has gone since the listing began.
                            if node is not None:
                                matches.append(
                                    NodeMatch(
                                        node=node,
                                        parent_id=level.node_id,
                                        location=level.node_id or "",
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
        return NodeSearchResult(matches=matches, complete=True)


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


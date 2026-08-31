"""The root of a file source and the only way in and out of it.

Everything the driver does goes through `resolve`, so the boundary has one
definition. The old application checked it in one branch of one method, and
the check let through any ancestor of the root.
"""

import os
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

from anyio import to_thread

from app.adapters.protocol import ConnectionCheckResult


def is_plain_name(part: str) -> bool:
    """A string that names one entry and nothing else.

    Judged by the rules of both platforms at once, so a node id means the same
    thing everywhere. On Windows a segment like "C:" is a drive reference and
    joining silently drops everything before it, turning one path into another
    without any error — the segment is refused instead. A separator of either
    platform makes it more than one entry, which is equally refused.

    Public because a name typed into a form — a new folder, the target of a
    rename, the name of an uploaded file — is the same kind of string as a
    path segment and must not get a second rule.
    """
    return (
        part not in {"", ".", ".."}
        and not PureWindowsPath(part).drive
        and not PureWindowsPath(part).root
        and len(PureWindowsPath(part).parts) == 1
        and len(PurePosixPath(part).parts) == 1
    )


def stays_inside_root(relative: str) -> bool:
    """Whether a relative path can only ever land inside the root it joins.

    Used both by `resolve` for a node id and by the options schema for the
    folder a connector points at, so both judge a path by one rule.
    """
    path = PurePosixPath(relative)
    return not path.is_absolute() and all(map(is_plain_name, path.parts))


class FileSession:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @property
    def resolved_root(self) -> Path:
        """The root with symlinks followed: what containment is judged against."""
        return self._root.resolve()

    def resolve(self, node_id: str | None) -> Path:
        """Absolute path of a node, guaranteed to sit inside the root.

        Raises ValueError for anything that leaves it — an absolute path, a
        `..` segment or a symlink pointing out. The message names the node the
        caller sent and never the layout of the server.
        """
        if node_id is None or node_id == "":
            return self._root

        if not stays_inside_root(node_id):
            raise ValueError(f"Path outside the connector root: {node_id}")

        candidate = (self._root / Path(*PurePosixPath(node_id).parts)).resolve()
        # resolve() follows symlinks, so a link out of the root fails here
        # rather than needing a check of its own.
        if not candidate.is_relative_to(self.resolved_root):
            raise ValueError(f"Path outside the connector root: {node_id}")
        return candidate

    def resolve_without_symlinks(self, node_id: str) -> Path:
        """Resolve one entry while refusing a link in any named segment.

        Reading a single node may safely follow a link that remains inside the
        root. Recursive archive traversal is different: aliases can duplicate
        a tree or form cycles, so that operation asks for this stricter path.
        """
        if not stays_inside_root(node_id):
            raise ValueError(f"Path outside the connector root: {node_id}")
        candidate = self._root
        for part in PurePosixPath(node_id).parts:
            candidate /= part
            if candidate.is_symlink():
                raise ValueError("Symbolic links are not downloaded")
        return self.resolve(node_id)

    def relative_id(self, path: Path) -> str:
        """The node id of a path: what the client gets back and may send in."""
        return path.relative_to(self.resolved_root).as_posix()

    async def check(self) -> ConnectionCheckResult:
        started = time.perf_counter()
        readable = await to_thread.run_sync(self._is_readable_directory)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not readable:
            return ConnectionCheckResult(
                ok=False,
                message="The directory does not exist or cannot be read",
                error_kind="config",
                latency_ms=latency_ms,
            )
        return ConnectionCheckResult(
            ok=True, message="Directory is readable", latency_ms=latency_ms
        )

    def _is_readable_directory(self) -> bool:
        try:
            return self._root.is_dir() and os.access(self._root, os.R_OK)
        except OSError:
            return False

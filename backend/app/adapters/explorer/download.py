"""Original and archived downloads produced by a tree of files."""

import io
import os
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from anyio import to_thread

from app.adapters.actions import (
    ActionDownload,
    ActionDownloadMetadata,
    ActionRefused,
)
from app.adapters.explorer import archive
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.members import ResolvedNode
from app.adapters.explorer.storage import Place, Storage, node_id_of

DOWNLOAD_CHUNK_BYTES = 256 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


class ExplorerDownload:
    """Prepare one original file, or one bounded archive of a selection."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def prepare(self, node_ids: Sequence[str]) -> ActionDownload:
        if not node_ids:
            raise ValueError("Choose at least one node to download")
        places = await to_thread.run_sync(self._places, node_ids)
        if len(places) == 1:
            found = await to_thread.run_sync(self._storage.entry, places[0])
            if found is not None and not found.is_directory:
                return await self._original(places[0], node_ids[0])

        staged, filename, size = await to_thread.run_sync(self._archived, places)
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=filename,
                media_type="application/zip",
                size_bytes=size,
            ),
            body=_temporary_chunks(staged),
        )

    def _places(self, node_ids: Sequence[str]) -> list[Place]:
        return [self._storage.unlinked_place(node_id) for node_id in node_ids]

    def _archived(self, places: list[Place]) -> tuple[Path, str, int]:
        """One zip of the selection, walked on this machine.

        The walk refuses every link it meets, so it walks the local tree, where
        a link is still a link: the storage's own listing leaves out a link it
        does not own, and a download that quietly lost one would be a download
        of something else than what was chosen.
        """
        for place in places:
            if self._storage.entry(place) is None:
                raise ValueError(f"No such node: {node_id_of(place) or ''}")
        with ExitStack() as held:
            targets = [held.enter_context(self._storage.local_tree(place)) for place in places]
            return _build_archive(targets)

    async def entry(self, resolved: ResolvedNode) -> ActionDownload:
        """One file inside an archive, expanded and streamed on its own (D53).

        A folder inside an archive is refused rather than repacked: a zip made
        out of a zip is a different result, and nothing has decided yet what it
        should be.
        """
        member = resolved.member or ""
        if format_of(resolved.name) != "archive":
            raise ActionRefused(
                "not_applicable", "This node is not a file inside an archive"
            )
        prepared = await to_thread.run_sync(self._extract, resolved.place, member)
        size = await to_thread.run_sync(lambda: prepared.stat().st_size)
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=member.rsplit("/", 1)[-1],
                media_type="application/octet-stream",
                size_bytes=size,
            ),
            body=_temporary_chunks(prepared),
        )

    def _extract(self, place: Place, member: str) -> Path:
        with self._storage.local_file(place) as container:
            return archive.extract(container, member)

    async def _original(self, place: Place, node_id: str) -> ActionDownload:
        # The open itself is the existence check: a separate look would still
        # leave the file free to vanish before it is read.
        try:
            handle = await to_thread.run_sync(self._storage.open, place)
        except OSError:
            raise ValueError(f"Could not open file: {node_id}") from None
        try:
            size = await to_thread.run_sync(_size_of, handle)
        except BaseException:
            await to_thread.run_sync(handle.close)
            raise
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=place.name,
                media_type="application/octet-stream",
                size_bytes=size,
            ),
            body=_handle_chunks(handle),
        )


def _build_archive(targets: list[Path]) -> tuple[Path, str, int]:
    names = [target.name for target in targets]
    if len(set(names)) != len(names):
        raise ActionRefused("conflict", "Two selected nodes have the same archive name")

    descriptor, temporary = tempfile.mkstemp(
        prefix="dataplayer-download-", suffix=".zip"
    )
    os.close(descriptor)
    staged = Path(temporary)
    try:
        with ZipFile(staged, "w", compression=ZIP_DEFLATED, allowZip64=True) as output:
            count = 0
            total = 0
            for target in targets:
                count, total = _add_target(
                    output, target, target.name, count=count, total=total
                )
        filename = (
            f"{targets[0].name}.zip"
            if len(targets) == 1 and targets[0].is_dir()
            else "download.zip"
        )
        return staged, filename, staged.stat().st_size
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _add_target(
    output: ZipFile,
    target: Path,
    archive_name: str,
    *,
    count: int,
    total: int,
) -> tuple[int, int]:
    if target.is_symlink():
        raise ActionRefused("not_applicable", "Symbolic links are not downloaded")
    if target.is_file():
        count = _next_entry(count)
        return count, _add_file(output, target, archive_name, total)
    if not target.is_dir():
        raise ValueError(f"Cannot download {target.name}")

    count = _next_entry(count)
    output.writestr(f"{archive_name.rstrip('/')}/", b"")
    children = sorted(target.iterdir(), key=lambda path: path.name.casefold())
    for child in children:
        count, total = _add_target(
            output,
            child,
            f"{archive_name.rstrip('/')}/{child.name}",
            count=count,
            total=total,
        )
    return count, total


def _next_entry(count: int) -> int:
    count += 1
    if count > MAX_ARCHIVE_ENTRIES:
        raise ActionRefused("too_large", "The selection contains too many archive entries")
    return count


def _add_file(output: ZipFile, path: Path, archive_name: str, total: int) -> int:
    try:
        source = path.open("rb")
    except OSError:
        raise ValueError(f"Could not open file: {path.name}") from None
    with source, output.open(archive_name, "w") as destination:
        while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
            total += len(chunk)
            if total > MAX_ARCHIVE_BYTES:
                raise ActionRefused("too_large", "The selection is too large to archive")
            destination.write(chunk)
    return total


def _size_of(handle: BinaryIO) -> int:
    """How long an open file is, asked of the file rather than of a name."""
    size = handle.seek(0, io.SEEK_END)
    handle.seek(0)
    return size


async def _handle_chunks(source: BinaryIO) -> AsyncIterator[bytes]:
    try:
        while chunk := await to_thread.run_sync(source.read, DOWNLOAD_CHUNK_BYTES):
            yield chunk
    finally:
        await to_thread.run_sync(source.close)


async def _temporary_chunks(path: Path) -> AsyncIterator[bytes]:
    source = await to_thread.run_sync(path.open, "rb")
    try:
        while chunk := await to_thread.run_sync(source.read, DOWNLOAD_CHUNK_BYTES):
            yield chunk
    finally:
        await to_thread.run_sync(source.close)
        await to_thread.run_sync(partial(path.unlink, missing_ok=True))

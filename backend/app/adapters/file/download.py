"""Original and archived downloads produced by the file source."""

import os
import tempfile
from collections.abc import AsyncIterator, Sequence
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
from app.adapters.file import archive
from app.adapters.file.formats import format_of
from app.adapters.file.members import ResolvedNode
from app.adapters.file.session import FileSession

DOWNLOAD_CHUNK_BYTES = 256 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


class FileDownload:
    """Prepare one original file, or one bounded archive of a selection."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def prepare(self, node_ids: Sequence[str]) -> ActionDownload:
        if not node_ids:
            raise ValueError("Choose at least one node to download")
        targets = [
            self._session.resolve_without_symlinks(node_id) for node_id in node_ids
        ]
        if len(targets) == 1 and await to_thread.run_sync(targets[0].is_file):
            return await self._original(targets[0], node_ids[0])

        staged, filename, size = await to_thread.run_sync(
            self._build_archive, targets
        )
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=filename,
                media_type="application/zip",
                size_bytes=size,
            ),
            body=_temporary_chunks(staged),
        )

    async def entry(self, resolved: ResolvedNode) -> ActionDownload:
        """One file inside an archive, expanded and streamed on its own (D53).

        A folder inside an archive is refused rather than repacked: a zip made
        out of a zip is a different result, and nothing has decided yet what it
        should be.
        """
        member = resolved.member or ""
        if format_of(resolved.path.name) != "archive":
            raise ActionRefused(
                "not_applicable", "This node is not a file inside an archive"
            )
        prepared = await to_thread.run_sync(archive.extract, resolved.path, member)
        size = await to_thread.run_sync(lambda: prepared.stat().st_size)
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=member.rsplit("/", 1)[-1],
                media_type="application/octet-stream",
                size_bytes=size,
            ),
            body=_temporary_chunks(prepared),
        )

    async def _original(self, path: Path, node_id: str) -> ActionDownload:
        # The open itself is the existence check: a separate stat would block the
        # loop and would still leave the file free to vanish before it is read.
        try:
            handle = await to_thread.run_sync(path.open, "rb")
        except OSError:
            raise ValueError(f"Could not open file: {node_id}") from None
        try:
            size = await to_thread.run_sync(lambda: os.fstat(handle.fileno()).st_size)
        except BaseException:
            await to_thread.run_sync(handle.close)
            raise
        return ActionDownload(
            metadata=ActionDownloadMetadata(
                filename=path.name,
                media_type="application/octet-stream",
                size_bytes=size,
            ),
            body=_handle_chunks(handle),
        )

    def _build_archive(self, targets: list[Path]) -> tuple[Path, str, int]:
        for target in targets:
            if not target.exists():
                raise ValueError(f"No such node: {self._session.relative_id(target)}")

        names = [target.name for target in targets]
        if len(set(names)) != len(names):
            raise ActionRefused(
                "conflict", "Two selected nodes have the same archive name"
            )

        descriptor, temporary = tempfile.mkstemp(
            prefix="dataplayer-download-", suffix=".zip"
        )
        os.close(descriptor)
        staged = Path(temporary)
        try:
            with ZipFile(
                staged, "w", compression=ZIP_DEFLATED, allowZip64=True
            ) as output:
                count = 0
                total = 0
                for target in targets:
                    count, total = self._add_target(
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
        self,
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
            count = self._next_entry(count)
            return count, self._add_file(output, target, archive_name, total)
        if not target.is_dir():
            raise ValueError(f"Cannot download {target.name}")

        count = self._next_entry(count)
        output.writestr(f"{archive_name.rstrip('/')}/", b"")
        children = sorted(target.iterdir(), key=lambda path: path.name.casefold())
        for child in children:
            count, total = self._add_target(
                output,
                child,
                f"{archive_name.rstrip('/')}/{child.name}",
                count=count,
                total=total,
            )
        return count, total

    @staticmethod
    def _next_entry(count: int) -> int:
        count += 1
        if count > MAX_ARCHIVE_ENTRIES:
            raise ActionRefused(
                "too_large", "The selection contains too many archive entries"
            )
        return count

    @staticmethod
    def _add_file(output: ZipFile, path: Path, archive_name: str, total: int) -> int:
        try:
            source = path.open("rb")
        except OSError:
            raise ValueError(f"Could not open file: {path.name}") from None
        with source, output.open(archive_name, "w") as destination:
            while chunk := source.read(DOWNLOAD_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise ActionRefused(
                        "too_large", "The selection is too large to archive"
                    )
                destination.write(chunk)
        return total


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

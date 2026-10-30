"""A delimited file too large for one request, kept on the server while a job
reads it (D45).

Kept in a folder of the owner's own storage rather than anywhere of the
server's: what one person uploads is theirs, it counts where their files
count, and the file source that reads it already confines itself to that
storage. Removed when the job that reads it ends, whatever the end.
"""

import uuid
from pathlib import Path

from anyio import to_thread
from fastapi import UploadFile

from app.adapters import registry
from app.adapters.actions import CHUNK_BYTES
from app.adapters.protocol import DataAdapter
from app.connectors.access import context_for
from app.connectors.service import build_adapter
from app.core.config import settings
from app.core.problems import Problem
from app.users import storage

# Hidden so a person browsing their files does not take it for one of theirs.
FOLDER = ".dataplayer-uploads"


def _folder(owner_id: uuid.UUID) -> Path:
    return storage.home_dir(owner_id) / FOLDER


async def receive(file: UploadFile, owner_id: uuid.UUID) -> str:
    """The upload, written to the owner's storage; its name there.

    Streamed a piece at a time and refused past MAX_UPLOAD_BYTES, the ceiling
    every upload into personal storage has.
    """
    folder = _folder(owner_id)
    name = f"{uuid.uuid4().hex}.csv"
    target = folder / name
    await to_thread.run_sync(lambda: folder.mkdir(parents=True, exist_ok=True))
    handle = await to_thread.run_sync(lambda: target.open("wb"))
    written = 0
    try:
        while chunk := await file.read(CHUNK_BYTES):
            written += len(chunk)
            if written > settings.MAX_UPLOAD_BYTES:
                raise Problem(
                    413,
                    "transfers.upload_too_large",
                    size=settings.MAX_UPLOAD_BYTES // (1024 * 1024),
                )
            await to_thread.run_sync(handle.write, chunk)
    except BaseException:
        await to_thread.run_sync(handle.close)
        await to_thread.run_sync(lambda: target.unlink(missing_ok=True))
        raise
    await to_thread.run_sync(handle.close)
    return name


def reader(owner_id: uuid.UUID) -> DataAdapter:
    """A file source over the uploads of one person, as the job reads them."""
    return build_adapter(
        registry.get("file"), {"path": f"/{FOLDER}"}, context_for(owner_id)
    )


async def discard(owner_id: uuid.UUID, name: str) -> None:
    """The upload, gone; nothing if it already is."""
    target = _folder(owner_id) / Path(name).name
    await to_thread.run_sync(lambda: target.unlink(missing_ok=True))

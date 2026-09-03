import uuid
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.db import SessionDep
from app.jobs import crud as job_crud
from app.jobs.models import JobPublic
from app.jobs.models import public as job_public
from app.jobs.runner import JobRunnerDep
from app.realtime.topics import TopicsDep
from app.services.backups import (
    BACKUP_FOLDER,
    BackUpConnector,
    RestoreConnector,
    storage_volume_reason,
)
from app.services.engine import ServiceEngineDep
from app.users import storage
from app.users.deps import CurrentUser

router = APIRouter(prefix="/backups", tags=["backups"])


class BackupRequest(BaseModel):
    """Which connection to copy out. Nothing else is a client's to say."""

    connector_id: uuid.UUID


class RestoreRequest(BaseModel):
    """Which backup to write back into which connection, and that it is meant.

    `understood` is not a formality: a restore drops every object in the dump
    from the target first, which nothing else in this application does. A
    client that has not said so gets a refusal rather than a database with
    yesterday's contents (D87).
    """

    connector_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    understood: bool = False


class BackupFile(BaseModel):
    """One backup in the caller's own storage."""

    filename: str
    size_bytes: int
    modified_at: float


class BackupOffer(BaseModel):
    """Whether this server can copy a database out at all, and why not."""

    available: bool
    reason: str | None = None
    folder: str = BACKUP_FOLDER


@router.get("/", response_model=list[BackupFile])
async def read_backups(current_user: CurrentUser) -> Any:
    """
    The backups in this person's own storage, newest first.

    Files rather than rows: a backup is a file in personal storage, which is
    already listed, downloaded, renamed and deleted through the file source.
    This is the same folder, read by name, so the two never disagree (D87).
    """
    folder = storage.home_dir(current_user.id) / BACKUP_FOLDER
    found = await to_thread.run_sync(_files_in, folder)
    return sorted(found, key=lambda item: item.modified_at, reverse=True)


@router.get("/offer", response_model=BackupOffer)
async def read_backup_offer(engine: ServiceEngineDep) -> Any:
    """
    Whether a backup could be taken now, and why not when it could not.

    Two reasons, and they are different: no container runtime to run the
    program in, and nowhere to write what it produces.
    """
    runtime = await engine.availability()
    if not runtime.available:
        return BackupOffer(available=False, reason=runtime.reason)
    nowhere = storage_volume_reason()
    if nowhere is not None:
        return BackupOffer(available=False, reason=nowhere)
    return BackupOffer(available=True)


@router.post("/", response_model=JobPublic)
async def back_up(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    engine: ServiceEngineDep,
    body: BackupRequest,
) -> Any:
    """
    Copy a connection's database out into a file of your own storage.

    A job, because a dump of anything real is minutes: the request records it
    and answers, and what happens is watched like any other work (D81).
    """
    await _own_connector_or_404(session, body.connector_id, current_user.id)
    await _refuse_unless_possible(engine)
    job = await job_crud.create(
        session,
        owner_id=current_user.id,
        kind="backup.create",
        subject_id=body.connector_id,
        step_count=len(runner.steps_of("backup.create")),
    )
    await runner.launch(job, topics)
    return job_public(job)


@router.post("/restore", response_model=JobPublic)
async def restore(
    session: SessionDep,
    current_user: CurrentUser,
    runner: JobRunnerDep,
    topics: TopicsDep,
    engine: ServiceEngineDep,
    body: RestoreRequest,
) -> Any:
    """
    Write a backup back into a connection, over what is there now.

    Destructive in a way nothing else in this application is, so the request
    must say that it is meant. The file is named rather than uploaded: it is
    one of the caller's own backups, and a name is checked against that folder
    rather than resolved as a path.
    """
    await _own_connector_or_404(session, body.connector_id, current_user.id)
    await _refuse_unless_possible(engine)
    if not body.understood:
        raise HTTPException(
            status_code=422,
            detail={
                "message": (
                    "A restore replaces what is in the database; say that it "
                    "is meant"
                )
            },
        )
    name = await to_thread.run_sync(
        _one_of_their_own, current_user.id, body.filename
    )
    job = await job_crud.create(
        session,
        owner_id=current_user.id,
        kind="backup.restore",
        subject_id=body.connector_id,
        step_count=len(runner.steps_of("backup.restore")),
        parameters={"filename": name},
    )
    await runner.launch(job, topics)
    return job_public(job)


def _files_in(folder: Path) -> list[BackupFile]:
    """What is in the folder, read off the file system in a worker thread."""
    if not folder.is_dir():
        return []
    return [
        BackupFile(
            filename=entry.name,
            size_bytes=entry.stat().st_size,
            modified_at=entry.stat().st_mtime,
        )
        for entry in folder.iterdir()
        if entry.is_file()
    ]


def _one_of_their_own(owner_id: uuid.UUID, filename: str) -> str:
    """The named backup, or a refusal.

    A name and not a path: it is matched against the files in one folder, so
    nothing here resolves anything a client wrote — the containment rule D8
    states for a file source, kept by having no path to contain.
    """
    folder = storage.home_dir(owner_id) / BACKUP_FOLDER
    for entry in folder.iterdir() if folder.is_dir() else []:
        if entry.is_file() and entry.name == filename:
            return entry.name
    raise HTTPException(
        status_code=404, detail={"message": "You have no backup by that name"}
    )


async def _refuse_unless_possible(engine: ServiceEngineDep) -> None:
    runtime = await engine.availability()
    if not runtime.available:
        raise HTTPException(
            status_code=503,
            detail={"message": runtime.reason or "This server cannot run programs"},
        )
    nowhere = storage_volume_reason()
    if nowhere is not None:
        raise HTTPException(status_code=503, detail={"message": nowhere})


async def _own_connector_or_404(
    session: SessionDep, connector_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    """A backup is the owner's, not a grant's.

    Copying a database out whole is more than reading it: it is every row,
    every schema and every function in one file the caller keeps. `own` is
    what that needs, and somebody else's connection is not found rather than
    refused (D33).
    """
    from app.connectors.models import Connector

    connector = await session.get(Connector, connector_id)
    if connector is None or connector.owner_id != owner_id:
        raise HTTPException(
            status_code=404, detail={"message": "No such connection"}
        )


# Named so the assembly can ask what the two kinds of work are without
# importing the handlers twice.
BACKUP_KINDS = (BackUpConnector.kind, RestoreConnector.kind)

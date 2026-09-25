"""Carrying out a transfer as an owned job (D168)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCache
from app.adapters.protocol import DataAdapter
from app.connectors.models import Connector, ConnectorGrant
from app.connectors.paste.files import FileCopy
from app.connectors.paste.transfer import (
    Transfer,
    TransferItem,
    TransferOutcome,
    TransferReport,
)
from app.core import crypto
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.transfers import handler as transfers
from app.transfers.handler import WAITING, RunTransfer
from app.users import crud as user_crud
from app.users import storage
from app.users.models import User


class Scripted(FileCopy):
    """Copies nothing; each item ends as the script says, and None waits to be stopped."""

    def __init__(self, script: list[TransferOutcome | None]) -> None:
        self.script = script
        self.waiting = asyncio.Event()

    async def transfer(
        self,
        source: DataAdapter,
        destination: DataAdapter,
        transfer: Transfer,
        report: TransferReport,
    ) -> None:
        for item, outcome in zip(transfer.items, self.script, strict=True):
            item.outcome = "running"
            await report.progressed()
            if outcome is None:
                self.waiting.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    item.outcome = "stopped"
                    raise
            else:
                item.outcome = outcome
                if outcome == "done":
                    item.arrived = 1
                    transfer.published += 1
                else:
                    item.failed = 1
            await report.progressed()


@pytest.fixture
async def owner(db: AsyncSession) -> User:
    user = await user_crud.get_user_by_email(session=db, email=settings.FIRST_SUPERUSER)
    assert user is not None
    return user


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


@pytest.fixture
def cache() -> MagicMock:
    spy = MagicMock()
    spy.invalidate_connector = AsyncMock()
    return spy


def payload(*names: str, source: uuid.UUID | None = None, destination: uuid.UUID | None = None) -> Transfer:
    return Transfer(
        kind="file_copy",
        title="Copy files",
        doing="Copying",
        done="copied",
        mode="copy",
        conflict="refuse",
        source_connector_id=source or uuid.uuid4(),
        source_label="Left",
        destination_connector_id=destination or uuid.uuid4(),
        destination_node_id="incoming",
        destination_label="Right",
        place_label="incoming",
        items=[TransferItem(node_id=name, name=name, size_bytes=1) for name in names],
        bytes_total=len(names),
    )


async def admitted(owner: User, transfer: Transfer) -> Job:
    async with async_session_maker() as session:
        return await crud.create(
            session,
            owner_id=owner.id,
            kind="paste.transfer",
            subject_id=transfer.destination_connector_id,
            step_count=3,
            parameters=transfer.model_dump(mode="json"),
        )


async def read(job_id: uuid.UUID) -> Job:
    async with async_session_maker() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        return job


def outcomes(job: Job) -> list[str]:
    return [item.outcome for item in Transfer.model_validate(job.parameters).items]


def scripted(
    monkeypatch: pytest.MonkeyPatch, cache: MagicMock, kind: Scripted
) -> tuple[RunTransfer, JobRunner]:
    """A handler whose kind is `kind`, with both ends found without a source."""

    async def ends(
        _self: RunTransfer, _job: Job, _transfer: Transfer, _kind: object
    ) -> tuple[DataAdapter, DataAdapter]:
        return cast(DataAdapter, object()), cast(DataAdapter, object())

    monkeypatch.setattr(transfers, "kind_named", lambda _name: kind)
    monkeypatch.setattr(RunTransfer, "_ends", ends)
    handler = RunTransfer(cast(DataCache, cache))
    return handler, JobRunner({handler.kind: handler})


async def test_every_item_done_is_a_success_in_its_own_words(
    owner: User, cache: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    transfer = payload("a.txt", "b.txt")
    _, runner = scripted(monkeypatch, cache, Scripted(["done", "done"]))
    job = await admitted(owner, transfer)

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await read(job.id)
    assert (settled.state, settled.message) == ("succeeded", "Copied 2 files to incoming")
    assert outcomes(settled) == ["done", "done"]
    # The catalog that re-reads after a file arrived is not answered from before it.
    cache.invalidate_connector.assert_any_await(transfer.destination_connector_id)


async def test_a_failed_item_fails_the_job_so_somebody_looks(
    owner: User, cache: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, runner = scripted(monkeypatch, cache, Scripted(["done", "failed"]))
    job = await admitted(owner, payload("a.txt", "b.txt"))

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await read(job.id)
    assert (settled.state, settled.message) == (
        "failed",
        "Copied 1 of 2 files to incoming; 1 failed",
    )


async def test_stopping_keeps_what_arrived_and_says_how_far_it_got(
    owner: User, cache: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    kind = Scripted(["done", None, "done"])
    _, runner = scripted(monkeypatch, cache, kind)
    job = await admitted(owner, payload("a.txt", "b.txt", "c.txt"))

    await runner.launch(job)
    await asyncio.wait_for(kind.waiting.wait(), timeout=5)
    await runner.cancel(job.id)
    await runner.wait_for(job.id)

    settled = await read(job.id)
    assert settled.state == "cancelled"
    assert settled.message == "Copied 1 of 3 files to incoming; stopped, 2 not attempted"
    assert outcomes(settled) == ["done", "stopped", "pending"]


async def test_a_transfer_waits_for_a_free_slot_and_says_so(
    owner: User, cache: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler, runner = scripted(monkeypatch, cache, Scripted(["done"]))
    slots, _ = handler._pools()
    for _ in range(transfers.SLOTS):
        await slots.acquire()
    job = await admitted(owner, payload("a.txt"))

    await runner.launch(job)
    for _ in range(100):
        if (await read(job.id)).step == WAITING:
            break
        await asyncio.sleep(0.02)
    assert (await read(job.id)).step == WAITING
    slots.release()
    await runner.wait_for(job.id)

    assert (await read(job.id)).state == "succeeded"


async def test_a_connection_gone_since_paste_fails_it_before_anything_moves(
    owner: User, cache: MagicMock
) -> None:
    handler = RunTransfer(cast(DataCache, cache))
    runner = JobRunner({handler.kind: handler})
    job = await admitted(owner, payload("a.txt"))

    await runner.launch(job)
    await runner.wait_for(job.id)

    settled = await read(job.id)
    assert (settled.state, settled.message) == (
        "failed",
        "Left is no longer available to you; nothing was transferred",
    )
    assert outcomes(settled) == ["pending"]


NO_SECRETS = crypto.encrypt(b"{}", purpose="connector")


@pytest.fixture
async def connections(owner: User) -> AsyncGenerator[tuple[Connector, Connector, User]]:
    """A connection of the owner's, and one somebody else granted them to read."""
    async with async_session_maker() as session:
        other = User(email=f"transfers-{uuid.uuid4().hex}@example.com", hashed_password="x")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        # A file connection opens only over its owner's personal folder.
        storage.create_home(owner.id)
        storage.create_home(other.id)
        mine = Connector(
            name="Mine", adapter_type="file", config={"path": "/"}, secrets=NO_SECRETS, owner_id=owner.id
        )
        theirs = Connector(
            name="Theirs", adapter_type="file", config={"path": "/"}, secrets=NO_SECRETS, owner_id=other.id
        )
        session.add_all([mine, theirs])
        await session.commit()
        await session.refresh(mine)
        await session.refresh(theirs)
        session.add(ConnectorGrant(connector_id=theirs.id, user_id=owner.id, access="read"))
        await session.commit()
    yield mine, theirs, other
    async with async_session_maker() as session:
        for row in (await session.get(Connector, mine.id), await session.get(Connector, theirs.id)):
            if row is not None:
                await session.delete(row)
        await session.commit()
        stored = await session.get(User, other.id)
        if stored is not None:
            await session.delete(stored)
            await session.commit()


async def test_a_withdrawn_level_or_a_switched_off_connection_fails_it(
    owner: User, cache: MagicMock, connections: tuple[Connector, Connector, User]
) -> None:
    mine, theirs, _ = connections
    handler = RunTransfer(cast(DataCache, cache))
    runner = JobRunner({handler.kind: handler})
    into_theirs = await admitted(owner, payload("a.txt", source=mine.id, destination=theirs.id))

    await runner.launch(into_theirs)
    await runner.wait_for(into_theirs.id)

    assert (await read(into_theirs.id)).message == (
        "You no longer have write access to Right; nothing was transferred"
    )

    async with async_session_maker() as session:
        stored = await session.get(Connector, mine.id)
        assert stored is not None
        stored.enabled = False
        session.add(stored)
        await session.commit()
    from_mine = await admitted(owner, payload("a.txt", source=mine.id, destination=mine.id))
    await runner.launch(from_mine)
    await runner.wait_for(from_mine.id)

    assert (await read(from_mine.id)).message == (
        "Left was switched off; nothing was transferred"
    )

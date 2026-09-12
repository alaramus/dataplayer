"""Carrying out an admitted source operation, one target at a time (D123)."""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.actions import Action, ActionRefused, UnknownAction
from app.adapters.cache import DataCache
from app.adapters.operations import (
    ObservedState,
    OperationPlan,
    OperationTarget,
    UnitOutcome,
)
from app.adapters.protocol import AdapterError, DataAdapter
from app.connectors.models import Connector, ConnectorGrant
from app.core.access import Access, Grant
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.source_operations.handler import RunSourceOperation, revision_of
from app.source_operations.models import SourceOperation
from app.users import crud as user_crud
from app.users.models import User
from tests.source_operations.records import PARAMS, UNIT, operation, read

Hook = Callable[[], Awaitable[None]]


class Units:
    """A source whose units answer from a script; None waits until cancelled."""

    def __init__(
        self, answers: Sequence[UnitOutcome | BaseException | None], *,
        observed: Mapping[str, ObservedState] | None = None, after_first: Hook | None = None,
    ) -> None:
        self.answers = list(answers)
        self.observed = dict(observed or {})
        self.after_first = after_first
        self.ran: list[str] = []
        self.waiting = asyncio.Event()

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str,
    ) -> OperationPlan:
        raise AssertionError("An admitted job never plans again")

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome:
        assert (node_id, dict(raw), unit_fingerprint) == ("lab.events", PARAMS, UNIT)
        self.ran.append(target.name)
        answer = self.answers.pop(0)
        if len(self.ran) == 1 and self.after_first is not None:
            await self.after_first()
        if answer is None:
            self.waiting.set()
            await asyncio.Event().wait()
        if isinstance(answer, BaseException):
            raise answer
        assert answer is not None
        return answer

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]:
        return [self.observed.get(target.name, "as_requested") for target in targets]


class Source:
    """An adapter offering one job-producing action by name."""

    def __init__(self, units: Units) -> None:
        self.units = units

    async def available(self, node_id: str | None) -> list[Action[Any]]:
        return []

    async def all_actions(self) -> list[Action[Any]]:
        return []

    def action(self, name: str) -> Action[Any]:
        if name != "fake_convert":
            raise UnknownAction(name)
        return cast(Action[Any], self.units)


def runner(cache: MagicMock, units: Units) -> JobRunner:
    handler = RunSourceOperation(
        cast(DataCache, cache), build=lambda _connector: cast(DataAdapter, Source(units)),
    )
    return JobRunner({handler.kind: handler})


@pytest.fixture
async def connector(owner: User) -> AsyncGenerator[Connector]:
    async with async_session_maker() as session:
        row = Connector(
            name=f"operations {uuid.uuid4()}", adapter_type="postgres", config={},
            secrets=b"", owner_id=owner.id,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    yield row
    async with async_session_maker() as session:
        stored = await session.get(Connector, row.id)
        if stored is not None:
            await session.delete(stored)
            await session.commit()


@pytest.fixture
async def colleague(db: AsyncSession, normal_user_token_headers: dict[str, str]) -> User:
    # The token fixture is what makes sure this user exists.
    assert normal_user_token_headers
    user = await user_crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    return user


async def accepted(
    owner_id: uuid.UUID, connector: Connector, names: Sequence[str] = ("one", "two", "three"), *,
    requires: Access = "structure", parameters: dict[str, object] | None = None,
    action: str = "fake_convert",
) -> Job:
    payload = parameters if parameters is not None else operation(
        names, revision=revision_of(connector), requires=requires, action=action,
    ).model_dump(mode="json")
    async with async_session_maker() as session:
        return await crud.create(
            session, owner_id=owner_id, kind="source.operation", subject_id=connector.id,
            step_count=3, parameters=payload,
        )


async def carried_out(jobs: JobRunner, job: Job) -> Job:
    await jobs.launch(job)
    await jobs.wait_for(job.id)
    return await read(job.id)


def settled(job: Job) -> SourceOperation:
    return SourceOperation.model_validate(job.parameters)


async def change_connector(connector_id: uuid.UUID, **values: object) -> None:
    async with async_session_maker() as session:
        stored = await session.get(Connector, connector_id)
        assert stored is not None
        for name, value in values.items():
            setattr(stored, name, value)
        session.add(stored)
        await session.commit()


async def grant(connector: Connector, user: User, access: Grant) -> None:
    async with async_session_maker() as session:
        session.add(ConnectorGrant(connector_id=connector.id, user_id=user.id, access=access))
        await session.commit()


async def revoke(connector: Connector, user: User) -> None:
    async with async_session_maker() as session:
        stored = await session.get(ConnectorGrant, (connector.id, user.id))
        assert stored is not None
        await session.delete(stored)
        await session.commit()


async def test_every_target_settles_in_order_and_each_unit_forgets_the_cache(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    units = Units(["completed", "already", "completed"])
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector))
    record = settled(stored)
    assert stored.state == "succeeded"
    assert stored.message == "Convert 3 things: 2 done, 1 already as requested"
    assert units.ran == ["one", "two", "three"]
    assert [target.outcome for target in record.targets] == ["completed", "already", "completed"]
    assert [target.observed for target in record.targets] == ["as_requested"] * 3
    assert cache.invalidate_connector.await_count == 3
    cache.invalidate_connector.assert_awaited_with(connector.id)


async def test_the_first_refusal_stops_the_job_and_leaves_the_rest_unattempted(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    refusal = ActionRefused("conflict", "This chunk is in use; nothing was converted")
    units = Units(["completed", refusal], observed={"two": "unchanged", "three": "unchanged"})
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector))
    record = settled(stored)
    assert stored.state == "failed"
    assert units.ran == ["one", "two"]
    assert [(target.outcome, target.message) for target in record.targets] == [
        ("completed", None), ("refused", refusal.message), ("pending", None),
    ]
    # Read back even so: what the source holds now is what a person needs to know.
    assert [target.observed for target in record.targets] == ["as_requested", "unchanged", "unchanged"]
    assert stored.message is not None
    assert "1 done, 1 refused, 1 not attempted" in stored.message
    assert "first target that did not complete" in stored.message
    assert cache.invalidate_connector.await_count == 2


async def test_an_unconfirmed_commit_is_unknown_and_stops_the_job(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    lost = AdapterError("unknown", "The connection was lost while this chunk was being converted; its outcome is unknown")
    units = Units([lost])
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector, ["one", "two"]))
    record = settled(stored)
    assert stored.state == "failed"
    assert [(target.outcome, target.message) for target in record.targets] == [
        ("unknown", lost.message), ("pending", None),
    ]


async def test_a_disabled_connection_refuses_before_any_target(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    await change_connector(connector.id, enabled=False)
    units = Units([])
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector))
    assert (stored.state, stored.message) == ("failed", "The connection was disabled; nothing was changed")
    assert units.ran == []
    cache.invalidate_connector.assert_not_awaited()


async def test_an_edited_connection_stops_the_job_before_the_next_target(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    async def edit() -> None:
        await change_connector(connector.id, updated_at=datetime.now(UTC))

    units = Units(["completed", "completed"], after_first=edit)
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector, ["one", "two"]))
    record = settled(stored)
    assert stored.state == "failed"
    assert units.ran == ["one"]
    assert [target.outcome for target in record.targets] == ["completed", "pending"]
    # Nothing more is read through a connection that changed underneath the job.
    assert [target.observed for target in record.targets] == [None, None]
    assert stored.message is not None
    assert "edited after this job was accepted" in stored.message
    assert "what was done stays done" in stored.message


async def test_revoked_access_stops_the_job_before_the_next_target(
    connector: Connector, colleague: User, cache: MagicMock,
) -> None:
    await grant(connector, colleague, "structure")

    async def take_it_away() -> None:
        await revoke(connector, colleague)

    units = Units(["completed", "completed"], after_first=take_it_away)
    stored = await carried_out(runner(cache, units), await accepted(colleague.id, connector, ["one", "two"]))
    assert stored.state == "failed"
    assert units.ran == ["one"]
    assert stored.message is not None and "Access to the connection changed" in stored.message


async def test_a_grant_below_what_the_action_needs_refuses_at_the_start(
    connector: Connector, colleague: User, cache: MagicMock,
) -> None:
    await grant(connector, colleague, "read")
    units = Units([])
    stored = await carried_out(runner(cache, units), await accepted(colleague.id, connector, ["one"]))
    assert stored.message == "Access to the connection changed; nothing was changed"
    assert units.ran == []


@pytest.mark.parametrize("observed,outcome", [("unchanged", "rolled_back"), ("as_requested", "completed")])
async def test_cancelling_mid_unit_reads_the_target_back_and_keeps_what_was_done(
    owner: User, connector: Connector, cache: MagicMock, observed: ObservedState, outcome: str,
) -> None:
    units = Units(["completed", None], observed={"two": observed})
    jobs = runner(cache, units)
    job = await accepted(owner.id, connector)
    await jobs.launch(job)
    await asyncio.wait_for(units.waiting.wait(), timeout=5)
    assert await jobs.cancel(job.id)
    await jobs.wait_for(job.id)
    stored = await read(job.id)
    record = settled(stored)
    assert stored.state == "cancelled"
    assert [target.outcome for target in record.targets] == ["completed", outcome, "pending"]
    assert record.targets[1].observed == observed
    assert units.ran == ["one", "two"]
    assert cache.invalidate_connector.await_count == 2


async def test_an_unreadable_plan_fails_without_opening_the_source(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    built = MagicMock()
    handler = RunSourceOperation(cast(DataCache, cache), build=built)
    stored = await carried_out(
        JobRunner({handler.kind: handler}),
        await accepted(owner.id, connector, parameters={"nonsense": True}),
    )
    assert (stored.state, stored.message) == ("failed", "This job's plan could not be read; nothing was changed")
    built.assert_not_called()


async def test_an_action_the_connection_no_longer_offers_fails_before_any_target(
    owner: User, connector: Connector, cache: MagicMock,
) -> None:
    units = Units([])
    stored = await carried_out(runner(cache, units), await accepted(owner.id, connector, ["one"], action="gone"))
    assert stored.message == "This connection no longer offers that action; nothing was changed"
    assert units.ran == []

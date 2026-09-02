"""Asking for a service, and everything that can happen to one (D81)."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.main import app
from app.services.engine import NO_ENGINE_MESSAGE, EngineError, NoEngine
from app.services.jobs import handlers
from app.services.models import ManagedService
from app.services.plan import ContainerSpec

BASE = f"{settings.API_V1_STR}/services"
JOBS = f"{settings.API_V1_STR}/jobs"


class _Engine:
    """An engine that does as it is told, and remembers what that was."""

    def __init__(self) -> None:
        self.pulled: list[str] = []
        self.created: list[ContainerSpec] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.restarted: list[str] = []
        self.removed: list[tuple[str, str | None]] = []
        self.refuse_on: str | None = None

    def _maybe_refuse(self, what: str) -> None:
        if self.refuse_on == what:
            raise EngineError(f"The engine would not {what}")

    async def pull(self, image: str) -> None:
        self._maybe_refuse("pull")
        self.pulled.append(image)

    async def create(self, spec: ContainerSpec) -> None:
        self._maybe_refuse("create")
        self.created.append(spec)

    async def start(self, container: str) -> None:
        self._maybe_refuse("start")
        self.started.append(container)

    async def stop(self, container: str) -> None:
        self._maybe_refuse("stop")
        self.stopped.append(container)

    async def restart(self, container: str) -> None:
        self._maybe_refuse("restart")
        self.restarted.append(container)

    async def remove(self, container: str, *, volume: str | None) -> None:
        self._maybe_refuse("remove")
        self.removed.append((container, volume))


@pytest.fixture(autouse=True)
async def without_services() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.exec(delete(ManagedService))
        await session.commit()
    yield
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.exec(delete(ManagedService))
        await session.commit()


@pytest.fixture
def engine() -> AsyncGenerator[_Engine]:
    """Swap the application's engine for one that does not need a daemon.

    The runner is built by the lifespan with the engine this deployment has;
    a test that wants to watch a service through its whole life supplies its
    own, which is the point of the engine being a protocol.
    """
    saved = app.state.job_runner
    fake = _Engine()
    app.state.job_runner = JobRunner(handlers(fake))
    try:
        yield fake
    finally:
        app.state.job_runner = saved


async def _wait(job_id: str) -> None:
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.wait_for(uuid.UUID(job_id))


async def _ask_for_one(
    client: AsyncClient, headers: dict[str, str], key: str = "postgres"
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/", headers=headers, json={"template_key": key}
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.usefixtures("engine")
async def test_asking_for_a_service_answers_before_anything_is_pulled(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The whole reason this is a job: an image is minutes of somebody else's
    network, and no HTTP request may wait for it."""
    accepted = await _ask_for_one(client, normal_user_token_headers)

    assert accepted["service"]["state"] == "creating"
    assert accepted["service"]["title"] == "PostgreSQL"
    assert accepted["job"]["kind"] == "service.create"
    assert accepted["job"]["state"] in {"queued", "running"}
    assert accepted["job"]["step_count"] == 3


async def test_the_job_pulls_creates_and_starts_and_the_service_says_running(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: _Engine
) -> None:
    accepted = await _ask_for_one(client, normal_user_token_headers)

    await _wait(accepted["job"]["id"])

    job = await client.get(
        f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
    )
    service = await client.get(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    assert engine.pulled == ["postgres:18"]
    assert [spec.name for spec in engine.created] == engine.started
    assert job.json()["state"] == "succeeded"
    assert job.json()["message"] == "PostgreSQL is running"
    assert service.json()["state"] == "running"
    # The service carries the last thing that happened to it, so a screen that
    # comes back after a reload knows what to show without a second question.
    assert service.json()["job"]["id"] == accepted["job"]["id"]


async def test_the_container_a_job_creates_is_the_one_the_service_named(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: _Engine
) -> None:
    """The names are settled when the service is written down, so a later
    command names the same container the create job made."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    assert engine.created[0].name == accepted["service"]["container_name"]


async def test_a_service_can_be_stopped_started_and_restarted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: _Engine
) -> None:
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    service_id = accepted["service"]["id"]
    container = accepted["service"]["container_name"]

    for command, expected in (
        ("stop", "stopped"),
        ("start", "running"),
        ("restart", "running"),
    ):
        answer = await client.post(
            f"{BASE}/{service_id}/{command}", headers=normal_user_token_headers
        )
        assert answer.status_code == 200, answer.text
        await _wait(answer.json()["job"]["id"])
        service = await client.get(
            f"{BASE}/{service_id}", headers=normal_user_token_headers
        )
        assert service.json()["state"] == expected, command

    assert engine.stopped == [container]
    assert engine.started == [container, container]
    assert engine.restarted == [container]


async def test_deleting_takes_the_container_and_its_volume(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: _Engine
) -> None:
    """Destructive on purpose: the volume was made for this service and
    belongs to nothing else."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    service_id = accepted["service"]["id"]

    removal = await client.delete(
        f"{BASE}/{service_id}", headers=normal_user_token_headers
    )
    await _wait(removal.json()["job"]["id"])

    gone = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)
    assert removal.json()["service"]["state"] == "removing"
    assert engine.removed == [
        (accepted["service"]["container_name"], _volume_of(accepted))
    ]
    assert gone.status_code == 404


async def test_a_failure_leaves_the_service_visible_and_says_why(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: _Engine
) -> None:
    engine.refuse_on = "create"

    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    job = await client.get(
        f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
    )
    service = await client.get(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    assert job.json()["state"] == "failed"
    assert job.json()["message"] == "The engine would not create"
    # Not removed: something a person can see, and delete when they choose.
    assert service.json()["state"] == "failed"


@pytest.mark.usefixtures("engine")
async def test_a_second_command_while_one_is_running_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Two jobs at once would be two processes telling one container what to
    do, and the second would report the outcome of a race."""
    accepted = await _ask_for_one(client, normal_user_token_headers)

    second = await client.post(
        f"{BASE}/{accepted['service']['id']}/stop", headers=normal_user_token_headers
    )

    await _wait(accepted["job"]["id"])
    assert second.status_code == 409
    assert second.json()["detail"]["job_id"] == accepted["job"]["id"]


@pytest.mark.usefixtures("engine")
async def test_a_service_being_created_takes_no_lifecycle_command(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    async with async_session_maker() as session:
        service = await session.get(
            ManagedService, uuid.UUID(accepted["service"]["id"])
        )
        assert service is not None
        service.state = "creating"
        session.add(service)
        await session.commit()

    refused = await client.post(
        f"{BASE}/{accepted['service']['id']}/start", headers=normal_user_token_headers
    )

    assert refused.status_code == 409


@pytest.mark.usefixtures("engine")
async def test_removal_is_the_way_out_of_a_state_a_stopped_job_left_behind(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A create that never finished leaves `creating`; delete must still work,
    or the row is stuck for ever."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    async with async_session_maker() as session:
        service = await session.get(
            ManagedService, uuid.UUID(accepted["service"]["id"])
        )
        assert service is not None
        service.state = "creating"
        session.add(service)
        await session.commit()

    removal = await client.delete(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    await _wait(removal.json()["job"]["id"])

    assert removal.status_code == 200
    gone = await client.get(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    assert gone.status_code == 404


@pytest.mark.usefixtures("engine")
async def test_a_service_is_only_its_owner_s(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """Not found rather than refused: an id is not an oracle, the rule
    connectors already follow (D33)."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    service_id = accepted["service"]["id"]

    read = await client.get(f"{BASE}/{service_id}", headers=superuser_token_headers)
    stopped = await client.post(
        f"{BASE}/{service_id}/stop", headers=superuser_token_headers
    )
    listed = await client.get(f"{BASE}/", headers=superuser_token_headers)
    job = await client.get(
        f"{JOBS}/{accepted['job']['id']}", headers=superuser_token_headers
    )

    assert read.status_code == 404
    assert stopped.status_code == 404
    assert job.status_code == 404
    assert service_id not in {item["id"] for item in listed.json()}


async def test_a_template_this_server_does_not_offer_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"template_key": "mongo"}
    )

    assert response.status_code == 422


async def test_without_a_container_runtime_the_job_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """No fixture here on purpose: this is the engine the application actually
    runs with until one is detected, and asking for a service on such a server
    must fail with a sentence rather than a traceback."""
    assert isinstance(app.state.job_runner, JobRunner)
    accepted = await _ask_for_one(client, normal_user_token_headers)

    await _wait(accepted["job"]["id"])

    job = await client.get(
        f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
    )
    assert job.json()["state"] == "failed"
    assert job.json()["message"] == NO_ENGINE_MESSAGE
    assert isinstance(NoEngine(), object)


def _volume_of(accepted: dict[str, Any]) -> str:
    return f"{accepted['service']['container_name']}-data"

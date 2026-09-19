"""Asking for a service, and everything that can happen to one (D81)."""

import json
import uuid
from collections.abc import AsyncGenerator, Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.adapters.credentials import KeyAccess
from app.adapters.ssh import keys
from app.connectors.models import Connector
from app.connectors.service import merge_options
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.runner import JobRunner
from app.main import app
from app.services.engine import NO_NETWORK_MESSAGE, SWITCHED_OFF_MESSAGE
from app.services.models import ManagedService
from tests.utils.service_engine import FakeEngine, engine_of, forget_services

BASE = f"{settings.API_V1_STR}/services"
JOBS = f"{settings.API_V1_STR}/jobs"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
async def without_services() -> AsyncGenerator[None]:
    await forget_services()
    yield
    await forget_services()


@pytest.fixture
def engine() -> Iterator[FakeEngine]:
    """Run the application with an engine that needs no daemon.

    The one this deployment has is built by the lifespan; a test that wants to
    watch a service through its whole life supplies its own, which is the
    point of the engine being a protocol.
    """
    fake = FakeEngine()
    with engine_of(app, fake):
        yield fake


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
    assert accepted["job"]["step_count"] == 7


async def test_the_job_pulls_creates_and_starts_and_the_service_says_running(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
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
    assert job.json()["message"] == "PostgreSQL is ready"
    assert service.json()["state"] == "running"
    # The connection it became, made from the same plan the container was
    # started with (D83).
    assert service.json()["connector_id"] is not None
    # The service carries the last thing that happened to it, so a screen that
    # comes back after a reload knows what to show without a second question.
    assert service.json()["job"]["id"] == accepted["job"]["id"]


async def test_the_container_a_job_creates_is_the_one_the_service_named(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """The names are settled when the service is written down, so a later
    command names the same container the create job made."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    assert engine.created[0].name == accepted["service"]["container_name"]


async def test_a_service_can_be_stopped_started_and_restarted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
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
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
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
    container = accepted["service"]["container_name"]
    assert engine.removed == [(container, f"{container}-data")]
    assert gone.status_code == 404


async def test_a_failure_leaves_the_service_visible_and_says_why(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
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


async def test_without_a_container_runtime_nothing_is_accepted(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """No fixture on purpose: this is the engine the application actually runs
    with in a test environment, and the refusal is what a person meets.

    Refused rather than accepted and failed: a row and a failed job would be a
    mess left behind by a question that could have been answered (D82).
    """
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={"template_key": "postgres"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == SWITCHED_OFF_MESSAGE


async def test_a_runtime_that_goes_away_after_the_answer_fails_the_job(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The check is a moment, the job is the authority: an engine that said
    yes and then refuses is a failed job with the engine's own sentence."""
    engine = FakeEngine()
    engine.refuse_on = "pull"

    with engine_of(app, engine):
        accepted = await _ask_for_one(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        job = await client.get(
            f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
        )

    assert job.json()["state"] == "failed"
    assert job.json()["message"] == "The engine would not pull"


@pytest.mark.usefixtures("engine")
async def test_a_ready_service_becomes_a_connector_of_its_own(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The point of the whole phase: a person receives a normal connection
    without the browser constructing anything (D83)."""
    accepted = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "postgres",
            "start": {"mode": "chosen", "name": "Sales database"},
        },
    )
    await _wait(accepted.json()["job"]["id"])

    service = await client.get(
        f"{BASE}/{accepted.json()['service']['id']}", headers=normal_user_token_headers
    )
    connector_id = service.json()["connector_id"]
    connector = await client.get(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )

    assert connector.status_code == 200
    assert connector.json()["name"] == "Sales database"
    assert connector.json()["adapter_type"] == "postgres"
    # An ordinary connector: it is the owner's, at the level ownership gives.
    assert connector.json()["access"] == "own"


async def test_the_connector_holds_what_the_container_was_started_with(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """The old application read the two out of different places and could save
    a connector that did not match its own container."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    started = engine.created[0]
    async with async_session_maker() as session:
        service = await session.get(
            ManagedService, uuid.UUID(accepted["service"]["id"])
        )
        assert service is not None and service.connector_id is not None
        connector = await session.get(Connector, service.connector_id)
        assert connector is not None
        options = merge_options(connector.config, connector.secrets)

    assert options["host"] == started.name
    assert options["port"] == 5432
    assert options["user"] == started.environment["POSTGRES_USER"]
    assert options["database"] == started.environment["POSTGRES_DB"]
    assert options["password"] == started.environment["POSTGRES_PASSWORD"]


async def test_a_started_ssh_server_keeps_the_key_it_answered_with(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """What the source answered to is what the connector keeps: the server
    key a started SSH server presented is the one its connection trusts
    (D153)."""
    engine = FakeEngine()
    presented = keys.generate("ed25519", None).facts.public_key

    async def pinning(
        _adapter_type: str,
        options: Mapping[str, str | int],
        *,
        home_dir: Path,
        timeout_seconds: int,
        keys: KeyAccess | None = None,
    ) -> dict[str, str | int] | None:
        del home_dir, timeout_seconds, keys
        return {**options, "host_key": presented}

    with engine_of(app, engine, probe=pinning):
        accepted = await _ask_for_one(client, normal_user_token_headers, "ssh")
        await _wait(accepted["job"]["id"])

    started = engine.created[0]
    async with async_session_maker() as session:
        service = await session.get(ManagedService, uuid.UUID(accepted["service"]["id"]))
        assert service is not None and service.connector_id is not None
        connector = await session.get(Connector, service.connector_id)
        assert connector is not None
        options = merge_options(connector.config, connector.secrets)

    assert connector.adapter_type == "ssh"
    assert options["host_key"] == presented
    assert options["host"] == started.name
    assert options["port"] == 2222
    assert options["username"] == started.environment["USER_NAME"]
    assert options["password"] == started.environment["USER_PASSWORD"]


async def test_the_password_is_not_stored_in_the_clear_anywhere(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """A service row holds no credentials: the connector is their one home,
    and there it is encrypted by the schema split (D4)."""
    accepted = await _ask_for_one(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])
    password = engine.created[0].environment["POSTGRES_PASSWORD"]

    async with async_session_maker() as session:
        service = await session.get(
            ManagedService, uuid.UUID(accepted["service"]["id"])
        )
        assert service is not None and service.connector_id is not None
        connector = await session.get(Connector, service.connector_id)
        assert connector is not None

    assert password not in json.dumps(connector.config)
    assert password.encode() not in connector.secrets
    assert password not in json.dumps(
        {"service": accepted["service"], "job": accepted["job"]}
    )


async def test_a_service_that_never_answers_is_a_failure_with_no_connector(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A container that starts and never answers is not a connection: nothing
    is saved, and the service says what happened."""
    with engine_of(app, FakeEngine(), ready=False):
        accepted = await _ask_for_one(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        job = await client.get(
            f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
        )
        service = await client.get(
            f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
        )

    assert job.json()["state"] == "failed"
    assert "did not answer" in job.json()["message"]
    assert service.json()["state"] == "failed"
    assert service.json()["connector_id"] is None


async def test_without_a_network_a_service_is_not_offered(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A service this server could start and never reach is not an offer."""
    with engine_of(app, FakeEngine(), network=""):
        listed = await client.get(
            f"{BASE}/templates", headers=normal_user_token_headers
        )
        asked = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={"template_key": "postgres"},
        )

    assert listed.json()[0]["available"] is False
    assert listed.json()[0]["unavailable_reason"] == NO_NETWORK_MESSAGE
    assert asked.status_code == 503

"""Asking twice, trying again, stopping, reading logs, and what is orphaned.

The half of the lifecycle that is about things going wrong (D84).
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.main import app
from app.services.models import ManagedService
from tests.utils.service_engine import FakeEngine, engine_of

BASE = f"{settings.API_V1_STR}/services"
JOBS = f"{settings.API_V1_STR}/jobs"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


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
def engine() -> Iterator[FakeEngine]:
    fake = FakeEngine()
    with engine_of(app, fake):
        yield fake


async def _wait(job_id: str) -> None:
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.wait_for(uuid.UUID(job_id))


async def _ask(
    client: AsyncClient, headers: dict[str, str], **body: Any
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE}/", headers=headers, json={"template_key": "postgres", **body}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- asking twice ----------------------------------------------------------


@pytest.mark.usefixtures("engine")
async def test_the_same_request_twice_makes_one_service(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A double press, or a POST the network retried: one container."""
    request_id = str(uuid.uuid4())

    first = await _ask(client, normal_user_token_headers, request_id=request_id)
    second = await _ask(client, normal_user_token_headers, request_id=request_id)
    await _wait(first["job"]["id"])

    assert second["service"]["id"] == first["service"]["id"]
    assert second["job"]["id"] == first["job"]["id"]
    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    assert len(listed.json()) == 1


@pytest.mark.usefixtures("engine")
async def test_two_requests_without_an_id_are_two_services(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Only the caller knows that two requests are one intention."""
    first = await _ask(client, normal_user_token_headers)
    second = await _ask(client, normal_user_token_headers)
    await _wait(first["job"]["id"])
    await _wait(second["job"]["id"])

    assert first["service"]["id"] != second["service"]["id"]


@pytest.mark.usefixtures("engine")
async def test_one_person_s_request_id_is_not_another_s(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    request_id = str(uuid.uuid4())
    mine = await _ask(client, normal_user_token_headers, request_id=request_id)
    theirs = await _ask(client, superuser_token_headers, request_id=request_id)
    await _wait(mine["job"]["id"])
    await _wait(theirs["job"]["id"])

    assert mine["service"]["id"] != theirs["service"]["id"]


# --- trying again ----------------------------------------------------------


async def test_retrying_starts_over_and_takes_the_earlier_attempt_away(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A container from a failed attempt has a password nobody knows, so it
    is removed rather than reused: that is what retry means here."""
    engine = FakeEngine()
    engine.refuse_on = "start"
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        service_id = accepted["service"]["id"]
        container = accepted["service"]["container_name"]
        engine.refuse_on = None

        again = await client.post(
            f"{BASE}/{service_id}/retry", headers=normal_user_token_headers
        )
        await _wait(again.json()["job"]["id"])
        service = await client.get(
            f"{BASE}/{service_id}", headers=normal_user_token_headers
        )

    assert again.status_code == 200
    # The first attempt's container and its data were taken away first.
    assert engine.removed == [(container, f"{container}-data")]
    assert engine.created[1].name == container
    assert service.json()["state"] == "running"
    assert service.json()["connector_id"] is not None


async def test_the_second_attempt_starts_the_container_with_a_new_password(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Which is why the first one's data cannot be kept."""
    engine = FakeEngine()
    engine.refuse_on = "start"
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        engine.refuse_on = None
        again = await client.post(
            f"{BASE}/{accepted['service']['id']}/retry",
            headers=normal_user_token_headers,
        )
        await _wait(again.json()["job"]["id"])

    first, second = engine.created[0], engine.created[1]
    assert (
        first.environment["POSTGRES_PASSWORD"]
        != second.environment["POSTGRES_PASSWORD"]
    )


@pytest.mark.usefixtures("engine")
async def test_a_service_that_already_works_is_not_retried(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Remaking it would destroy a database somebody is using."""
    accepted = await _ask(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    again = await client.post(
        f"{BASE}/{accepted['service']['id']}/retry", headers=normal_user_token_headers
    )

    assert again.status_code == 409
    assert "remove it instead" in again.json()["detail"]["message"]


# --- stopping --------------------------------------------------------------


async def test_a_job_can_be_asked_to_stop(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """What it had already done is left as it stands; the service is a thing
    to retry or remove afterwards."""
    engine = FakeEngine()
    # Held in the middle of the slow step, which is where a person watching a
    # pull would press stop.
    engine.hold_on = "pull"
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await asyncio.wait_for(engine.holding.wait(), timeout=5)
        stopped = await client.post(
            f"{JOBS}/{accepted['job']['id']}/cancel", headers=normal_user_token_headers
        )
        await _wait(accepted["job"]["id"])
        job = await client.get(
            f"{JOBS}/{accepted['job']['id']}", headers=normal_user_token_headers
        )

    assert stopped.status_code == 200
    assert job.json()["state"] == "cancelled"
    assert job.json()["message"] == "Stopped before it finished"


@pytest.mark.usefixtures("engine")
async def test_stopping_something_that_has_already_ended_is_not_an_error(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The caller asked for it to be over, and it is."""
    accepted = await _ask(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    stopped = await client.post(
        f"{JOBS}/{accepted['job']['id']}/cancel", headers=normal_user_token_headers
    )

    assert stopped.status_code == 200
    assert stopped.json()["state"] == "succeeded"


@pytest.mark.usefixtures("engine")
async def test_a_job_is_only_its_owner_s_to_stop(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    accepted = await _ask(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    stopped = await client.post(
        f"{JOBS}/{accepted['job']['id']}/cancel", headers=superuser_token_headers
    )

    assert stopped.status_code == 404


# --- what the runtime says -------------------------------------------------


async def test_a_service_says_what_the_runtime_reports_about_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The two can differ, and that is exactly what has to be visible."""
    engine = FakeEngine()
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        running = await client.get(f"{BASE}/", headers=normal_user_token_headers)

        # Somebody removed the container by hand.
        engine.holds.clear()
        gone = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert running.json()[0]["container_state"] == "running"
    assert running.json()[0]["state"] == "running"
    assert gone.json()[0]["container_state"] == "missing"
    # What this application believes is unchanged, and says so beside it.
    assert gone.json()[0]["state"] == "running"


async def test_a_server_that_cannot_ask_says_unknown_rather_than_guessing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    engine = FakeEngine()
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        engine.refuse_on = "managed"
        listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    assert listed.json()[0]["container_state"] == "unknown"


# --- logs ------------------------------------------------------------------


async def test_the_output_of_a_service_can_be_read(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    engine = FakeEngine()
    engine.printed = ["database system is ready to accept connections"]
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        logs = await client.get(
            f"{BASE}/{accepted['service']['id']}/logs",
            headers=normal_user_token_headers,
        )

    assert logs.status_code == 200
    assert logs.json()["lines"] == [
        "database system is ready to accept connections"
    ]


@pytest.mark.usefixtures("engine")
async def test_the_output_of_somebody_else_s_service_is_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    accepted = await _ask(client, normal_user_token_headers)
    await _wait(accepted["job"]["id"])

    logs = await client.get(
        f"{BASE}/{accepted['service']['id']}/logs", headers=superuser_token_headers
    )

    assert logs.status_code == 404


# --- orphans ---------------------------------------------------------------


async def test_a_container_no_row_claims_is_found(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    """What is left when a row went and its container did not."""
    engine = FakeEngine()
    engine.holds["dataplayer-svc-postgres-abandoned"] = "running"
    with engine_of(app, engine):
        listed = await client.get(f"{BASE}/unclaimed", headers=superuser_token_headers)

    assert [item["name"] for item in listed.json()] == [
        "dataplayer-svc-postgres-abandoned"
    ]


async def test_a_container_a_service_claims_is_not_an_orphan(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    engine = FakeEngine()
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        listed = await client.get(f"{BASE}/unclaimed", headers=superuser_token_headers)
        refused = await client.delete(
            f"{BASE}/unclaimed/{accepted['service']['container_name']}",
            headers=superuser_token_headers,
        )

    assert listed.json() == []
    assert refused.status_code == 409


async def test_an_orphan_can_be_taken_away(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    engine = FakeEngine()
    engine.holds["dataplayer-svc-postgres-abandoned"] = "running"
    with engine_of(app, engine):
        removed = await client.delete(
            f"{BASE}/unclaimed/dataplayer-svc-postgres-abandoned",
            headers=superuser_token_headers,
        )

    assert removed.status_code == 200
    assert engine.removed == [
        (
            "dataplayer-svc-postgres-abandoned",
            "dataplayer-svc-postgres-abandoned-data",
        )
    ]


@pytest.mark.usefixtures("engine")
async def test_orphans_are_an_administrator_s_question(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """What runs on the machine is not one user's business, and what is found
    there may be anybody's."""
    listed = await client.get(f"{BASE}/unclaimed", headers=normal_user_token_headers)

    assert listed.status_code == 403


# --- what deleting means ---------------------------------------------------


async def test_removing_a_service_leaves_the_connection_for_its_owner_to_remove(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A connection may be shared, may be in somebody's query history, and is
    not this command's to destroy — so it stays, and stops working (D84)."""
    engine = FakeEngine()
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        service = await client.get(
            f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
        )
        connector_id = service.json()["connector_id"]

        removal = await client.delete(
            f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
        )
        await _wait(removal.json()["job"]["id"])

    connector = await client.get(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )
    assert connector.status_code == 200
    await client.delete(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )


async def test_removing_a_connection_leaves_the_service_running(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Deleting a connector must not silently delete a volume, and here it
    does not touch the runtime at all."""
    engine = FakeEngine()
    with engine_of(app, engine):
        accepted = await _ask(client, normal_user_token_headers)
        await _wait(accepted["job"]["id"])
        service = await client.get(
            f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
        )

        await client.delete(
            f"{CONNECTORS}/{service.json()['connector_id']}",
            headers=normal_user_token_headers,
        )
        after = await client.get(
            f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
        )

    assert engine.removed == []
    assert after.json()["container_state"] == "running"
    # The row lost the connection it made, and says so rather than pretending.
    assert after.json()["connector_id"] is None


# --- what one person may hold ---------------------------------------------


@pytest.mark.usefixtures("engine")
async def test_one_person_may_hold_only_so_many_services(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Not a quota system: a number that turns "somebody left a loop running"
    into a refusal they can read rather than an outage everybody meets."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "SERVICE_MAX_PER_USER", 2)
        first = await _ask(client, normal_user_token_headers)
        second = await _ask(client, normal_user_token_headers)
        third = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={"template_key": "postgres"},
        )
        await _wait(first["job"]["id"])
        await _wait(second["job"]["id"])

    assert third.status_code == 409
    assert "remove one before starting another" in third.json()["detail"]["message"]


@pytest.mark.usefixtures("engine")
async def test_what_somebody_else_holds_is_not_counted_against_you(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "SERVICE_MAX_PER_USER", 1)
        mine = await _ask(client, normal_user_token_headers)
        theirs = await _ask(client, superuser_token_headers)
        await _wait(mine["job"]["id"])
        await _wait(theirs["job"]["id"])

    assert mine["service"]["id"] != theirs["service"]["id"]

"""The two ways to ask for a service, and what each of them decides (D88)."""

import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.jobs.runner import JobRunner
from app.main import app
from tests.utils.service_engine import (
    FakeEngine,
    FakeFiller,
    engine_of,
    forget_services,
)

BASE = f"{settings.API_V1_STR}/services"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
async def without_services() -> AsyncGenerator[None]:
    await forget_services()
    yield
    await forget_services()


@pytest.fixture
def filler() -> FakeFiller:
    return FakeFiller()


@pytest.fixture
def engine(filler: FakeFiller) -> Iterator[FakeEngine]:
    fake = FakeEngine()
    with engine_of(app, fake, filler=filler):
        yield fake


async def _wait(job_id: str) -> None:
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.wait_for(uuid.UUID(job_id))


async def _start(
    client: AsyncClient, headers: dict[str, str], start: dict[str, Any] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"template_key": "postgres"}
    if start is not None:
        body["start"] = start
    response = await client.post(f"{BASE}/", headers=headers, json=body)
    assert response.status_code == 200, response.text
    accepted = response.json()
    await _wait(accepted["job"]["id"])
    return accepted


# --- asking for nothing ----------------------------------------------------


@pytest.mark.usefixtures("engine")
async def test_an_automatic_start_asks_for_nothing_and_names_it_itself(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Somebody who has not been asked for a name has not got one in mind."""
    first = await _start(client, normal_user_token_headers)
    second = await _start(client, normal_user_token_headers)

    assert first["service"]["connector_name"] == "PostgreSQL 1"
    assert second["service"]["connector_name"] == "PostgreSQL 2"


@pytest.mark.usefixtures("engine")
async def test_a_request_with_no_start_at_all_is_the_automatic_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The default, so a client that says only which template gets the
    demonstration rather than a refusal."""
    accepted = await _start(client, normal_user_token_headers, start=None)

    assert accepted["service"]["connector_name"] == "PostgreSQL 1"


async def test_an_automatic_start_fills_it_and_publishes_it(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
    filler: FakeFiller,
) -> None:
    """It is the demonstration: something to look at, and somewhere to open it
    from."""
    await _start(client, normal_user_token_headers)

    assert filler.filled == ["postgres"]
    assert [spec.publish for spec in engine.created] == [True]


# --- asking for what is a person's to decide -------------------------------


@pytest.mark.usefixtures("engine")
async def test_a_chosen_start_uses_the_names_it_was_given(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    accepted = await _start(
        client,
        normal_user_token_headers,
        {
            "mode": "chosen",
            "name": "Sales",
            "user": "sales_admin",
            "database": "sales",
            "publish": False,
            "sample_data": False,
        },
    )

    assert accepted["service"]["connector_name"] == "Sales"
    environment = engine.created[0].environment
    assert environment["POSTGRES_USER"] == "sales_admin"
    assert environment["POSTGRES_DB"] == "sales"


async def test_a_chosen_start_may_say_no_to_both_extras(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
    filler: FakeFiller,
) -> None:
    await _start(
        client,
        normal_user_token_headers,
        {
            "mode": "chosen",
            "name": "Quiet",
            "publish": False,
            "sample_data": False,
        },
    )

    assert filler.filled == []
    assert [spec.publish for spec in engine.created] == [False]


@pytest.mark.usefixtures("engine")
async def test_the_password_is_still_the_server_s_in_both_modes(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """There is no field for it, and a request that invents one is refused.

    A chosen password would have to be written down between the request and
    the job that uses it, and the only encrypted home for a service's password
    is the connector it becomes (D4).
    """
    refused = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "postgres",
            "start": {"mode": "chosen", "name": "Sneaky", "password": "hunter2"},
        },
    )

    assert refused.status_code == 422
    assert engine.created == []


@pytest.mark.usefixtures("engine")
async def test_a_name_the_template_does_not_open_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A Redis server has no role to name, so saying one is a mistake worth
    telling somebody about rather than dropping."""
    refused = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "redis",
            "start": {"mode": "chosen", "name": "Cache", "user": "someone"},
        },
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["message"] == "This service has no user to name"


@pytest.mark.usefixtures("engine")
async def test_a_name_that_is_not_a_name_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """These become an environment variable in a container's specification and
    a role in somebody's server; neither takes a quote."""
    for written in ["drop table", "a'b", "1st", "x" * 80]:
        refused = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={
                "template_key": "postgres",
                "start": {"mode": "chosen", "name": "Bad", "user": written},
            },
        )
        assert refused.status_code == 422, written


@pytest.mark.usefixtures("engine")
async def test_nothing_about_the_container_can_be_asked_for(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The whole of D80 in one test: the old application took the image from
    the connector form."""
    for extra in [
        {"image": "evil:latest"},
        {"command": ["sh", "-c", "curl evil"]},
        {"volume": "/etc"},
        {"port": 5432},
        {"network": "host"},
    ]:
        refused = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={
                "template_key": "postgres",
                "start": {"mode": "chosen", "name": "Bad", **extra},
            },
        )
        assert refused.status_code == 422, extra


# --- what a service is reachable on ----------------------------------------


async def test_the_port_is_the_runtime_s_answer_and_is_written_down(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """This application never picks one: it would have to bind a socket to
    find out what is free and then race whoever took it in between."""
    engine.gives_port = 49213

    accepted = await _start(client, normal_user_token_headers)

    service = await client.get(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    assert service.json()["published_port"] == 49213


# --- the password, shown once ----------------------------------------------


async def test_the_credentials_are_shown_once_and_then_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """The password was made up by the server, so the person who asked for the
    database has to be told it — and it lives encrypted in the connector from
    then on, with no second way to read it out (D4)."""
    engine.gives_port = 49214
    accepted = await _start(client, normal_user_token_headers)
    service_id = accepted["service"]["id"]

    shown = await client.get(
        f"{BASE}/{service_id}/credentials", headers=normal_user_token_headers
    )
    again = await client.get(
        f"{BASE}/{service_id}/credentials", headers=normal_user_token_headers
    )

    assert shown.status_code == 200
    body = shown.json()
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 49214
    assert body["user"] == "dataplayer"
    assert body["database"] == "dataplayer"
    assert len(body["password"]) == 32
    # And the same thing as one line, which is what most tools take. Written
    # by the source type that owns the grammar, never joined together here.
    assert body["url"] == (
        f"postgresql://dataplayer:{body['password']}@127.0.0.1:49214/dataplayer"
    )
    assert again.status_code == 409


async def test_a_service_says_whether_its_password_has_been_shown(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """What greys the button out, rather than a button that would refuse."""
    engine.gives_port = 49215
    accepted = await _start(client, normal_user_token_headers)
    service_id = accepted["service"]["id"]

    before = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)
    await client.get(f"{BASE}/{service_id}/credentials", headers=normal_user_token_headers)
    after = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)

    assert before.json()["credentials_shown"] is False
    assert after.json()["credentials_shown"] is True


@pytest.mark.usefixtures("engine")
async def test_a_service_with_no_port_says_why_there_is_no_address(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Only this server can reach it, and the window says so rather than
    showing a host somebody would try."""
    accepted = await _start(
        client,
        normal_user_token_headers,
        {"mode": "chosen", "name": "Quiet", "publish": False, "sample_data": False},
    )

    shown = await client.get(
        f"{BASE}/{accepted['service']['id']}/credentials",
        headers=normal_user_token_headers,
    )

    assert shown.json()["host"] is None
    assert shown.json()["port"] is None
    # No address means no address, rather than one pointing at nothing.
    assert shown.json()["url"] is None
    assert "only this application can reach it" in shown.json()["unreachable_reason"]


@pytest.mark.usefixtures("engine")
async def test_somebody_else_s_credentials_are_not_found(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    accepted = await _start(client, normal_user_token_headers)

    refused = await client.get(
        f"{BASE}/{accepted['service']['id']}/credentials",
        headers=superuser_token_headers,
    )

    assert refused.status_code == 404

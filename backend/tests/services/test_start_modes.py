"""The two ways to ask for a service, and what each of them decides (D88)."""

import json
import uuid
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.runner import JobRunner
from app.main import app
from app.services.models import ManagedService
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
            "sample_data": False,
        },
    )

    assert accepted["service"]["connector_name"] == "Sales"
    environment = engine.created[0].environment
    assert environment["POSTGRES_USER"] == "sales_admin"
    assert environment["POSTGRES_DB"] == "sales"


async def test_a_chosen_start_may_say_no_to_sample_data(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
    filler: FakeFiller,
) -> None:
    await _start(
        client,
        normal_user_token_headers,
        {"mode": "chosen", "name": "Quiet", "sample_data": False},
    )

    assert filler.filled == []
    # Reachable from the machine all the same: that stopped being a question,
    # because a database nobody can open in their own tools was a choice that
    # only ever produced a service somebody then had to remake.
    assert [spec.publish for spec in engine.created] == [True]


@pytest.mark.usefixtures("engine")
async def test_asking_to_keep_it_unreachable_is_not_a_thing_to_ask(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The field is gone rather than ignored: a request that still sends it is
    a client that believes something untrue."""
    refused = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "postgres",
            "start": {"mode": "chosen", "name": "Quiet", "publish": False},
        },
    )

    assert refused.status_code == 422


# --- the password ----------------------------------------------------------


@pytest.mark.usefixtures("engine")
async def test_a_password_nobody_typed_is_still_the_server_s(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """The default in both modes, and the whole of the automatic one."""
    await _start(client, normal_user_token_headers, {"mode": "chosen", "name": "Made"})

    assert len(engine.created[0].environment["POSTGRES_PASSWORD"]) == 32


@pytest.mark.usefixtures("engine")
async def test_a_password_somebody_typed_is_the_one_the_container_gets(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """A person setting a database up for their own tools may want one they
    already know. It reaches the container through an encrypted column on the
    service row and nowhere else (D88)."""
    await _start(
        client,
        normal_user_token_headers,
        {
            "mode": "chosen",
            "name": "Typed",
            "password": {"kind": "chosen", "value": "correct-horse-9"},
        },
    )

    assert engine.created[0].environment["POSTGRES_PASSWORD"] == "correct-horse-9"


@pytest.mark.usefixtures("engine")
async def test_a_typed_password_is_never_written_down_in_the_clear(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Not in the JSON column the chosen names live in, and not in the answer.

    The copy that carries it from the request to the job is encrypted under
    the connector key, and it is erased once the connector holds it — so a
    finished service has one home for its password again (D4)."""
    accepted = await _start(
        client,
        normal_user_token_headers,
        {
            "mode": "chosen",
            "name": "Secret",
            "password": {"kind": "chosen", "value": "correct-horse-9"},
        },
    )

    async with async_session_maker() as session:
        service = await session.get(
            ManagedService, uuid.UUID(accepted["service"]["id"])
        )
        assert service is not None

    assert "correct-horse-9" not in json.dumps(service.chosen_credentials)
    assert service.chosen_password is None
    assert "correct-horse-9" not in json.dumps(accepted)


@pytest.mark.usefixtures("engine")
async def test_a_password_that_would_not_survive_where_it_goes_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """It becomes an environment variable, a command-line argument and part of
    a connection string, and a space or a newline survives none of those."""
    for written in ["short", "with space", "line\nbreak", ""]:
        refused = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={
                "template_key": "postgres",
                "start": {
                    "mode": "chosen",
                    "name": "Bad",
                    "password": {"kind": "chosen", "value": written},
                },
            },
        )
        assert refused.status_code == 422, written


async def test_a_redis_may_be_asked_to_want_no_password_at_all(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """The one image here where that is an ordinary configuration: no
    `--requirepass`, and a connector that says it authenticates with none."""
    accepted = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "redis",
            "start": {"mode": "chosen", "name": "Open", "password": {"kind": "none"}},
        },
    )
    assert accepted.status_code == 200, accepted.text
    await _wait(accepted.json()["job"]["id"])

    assert engine.created[0].command == ("redis-server",)


@pytest.mark.usefixtures("engine")
async def test_a_postgres_may_not_be_asked_to_want_none(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """A server that trusts every connection is not one this will start, and
    saying so beats quietly making a password up instead."""
    refused = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={
            "template_key": "postgres",
            "start": {"mode": "chosen", "name": "Open", "password": {"kind": "none"}},
        },
    )

    assert refused.status_code == 422
    assert "without a password" in refused.json()["detail"]["message"]
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
        {"data_path": "/etc"},
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
    """Unless somebody named one, this application never picks: it would have
    to bind a socket to find out what is free and then race whoever took it in
    between."""
    engine.gives_port = 49213

    accepted = await _start(client, normal_user_token_headers)

    service = await client.get(
        f"{BASE}/{accepted['service']['id']}", headers=normal_user_token_headers
    )
    assert service.json()["published_port"] == 49213
    assert engine.created[0].host_port is None


async def test_a_port_somebody_named_is_the_one_the_runtime_is_asked_for(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """Somebody with a configuration file pointing at 5433 wants 5433, and
    zero — the default — is the way of saying it does not matter."""
    engine.gives_port = 5433

    await _start(
        client,
        normal_user_token_headers,
        {"mode": "chosen", "name": "Fixed port", "port": 5433},
    )

    assert engine.created[0].host_port == 5433


async def test_a_named_port_that_will_not_bind_says_what_to_do_about_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The daemon's own words name a port and an address on this machine and
    do not cross (D82), so the sentence is this repository's and names the
    number the request carried."""
    engine = FakeEngine()
    engine.refuse_on = "start"
    with engine_of(app, engine):
        accepted = await _start(
            client,
            normal_user_token_headers,
            {"mode": "chosen", "name": "Taken", "port": 5433},
        )
        job = await client.get(
            f"{settings.API_V1_STR}/jobs/{accepted['job']['id']}",
            headers=normal_user_token_headers,
        )

    assert job.json()["state"] == "failed"
    assert "Port 5433 may already be in use" in job.json()["message"]


@pytest.mark.usefixtures("engine")
async def test_a_port_outside_the_range_of_ports_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    for written in [-1, 70000, "5433; rm -rf /"]:
        refused = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={
                "template_key": "postgres",
                "start": {"mode": "chosen", "name": "Bad", "port": written},
            },
        )
        assert refused.status_code == 422, written


# --- where it listens, as often as it is asked -----------------------------


async def test_where_a_service_listens_can_be_asked_again_and_again(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """An address and the names it goes by are not a secret, so there is
    nothing to ration: somebody who closed the window can open it tomorrow."""
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
    assert again.status_code == 200
    body = shown.json()
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 49214
    assert body["user"] == "dataplayer"
    assert body["database"] == "dataplayer"
    # And the same thing as one line, which is what most tools take. Written
    # by the source type that owns the grammar, never joined together here.
    assert body["url"] == "postgresql://dataplayer@127.0.0.1:49214/dataplayer"


async def test_no_password_is_ever_in_that_answer(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """Not the field, and not inside the address either. It is encrypted in
    the connector and stays there; somebody who needs to know a service's
    password starts one with a password of their own (D89)."""
    engine.gives_port = 49216
    accepted = await _start(client, normal_user_token_headers)
    password = engine.created[0].environment["POSTGRES_PASSWORD"]

    shown = await client.get(
        f"{BASE}/{accepted['service']['id']}/credentials",
        headers=normal_user_token_headers,
    )

    assert "password" not in shown.json()
    assert password not in shown.text
    assert shown.json()["password_mode"] == "generated"


async def test_where_it_listens_survives_the_connection_being_deleted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """Read off the service row and its template rather than the connector,
    which is exactly the case where somebody still has a container and no
    longer has the row that described it."""
    engine.gives_port = 49217
    accepted = await _start(client, normal_user_token_headers)
    service_id = accepted["service"]["id"]
    service = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)
    await client.delete(
        f"{CONNECTORS}/{service.json()['connector_id']}",
        headers=normal_user_token_headers,
    )

    shown = await client.get(
        f"{BASE}/{service_id}/credentials", headers=normal_user_token_headers
    )

    assert shown.status_code == 200
    assert shown.json()["port"] == 49217


async def test_a_service_says_whether_it_ever_became_a_connection(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """What tells a creation that never got there from one whose connection
    somebody deleted: only the first may be started over (D84)."""
    engine.gives_port = 49215
    accepted = await _start(client, normal_user_token_headers)
    service_id = accepted["service"]["id"]
    made = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)

    await client.delete(
        f"{CONNECTORS}/{made.json()['connector_id']}", headers=normal_user_token_headers
    )
    after = await client.get(f"{BASE}/{service_id}", headers=normal_user_token_headers)

    assert accepted["service"]["was_connected"] is False
    assert made.json()["was_connected"] is True
    assert after.json()["connector_id"] is None
    assert after.json()["was_connected"] is True


@pytest.mark.usefixtures("engine")
async def test_a_service_with_no_port_says_why_there_is_no_address(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A runtime that published nothing leaves nothing to paste, and the
    window says so rather than showing a host somebody would try."""
    accepted = await _start(
        client,
        normal_user_token_headers,
        {"mode": "chosen", "name": "Quiet", "sample_data": False},
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

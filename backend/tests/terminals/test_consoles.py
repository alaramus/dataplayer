"""A source whose terminal is a client program run by the server (D286).

The runtime is played by a runner that records what it was asked to run and
answers with a terminal of its own; the programs a MongoDB, a Redis and a
PostgreSQL connection ask for are checked here as well, since they reach no
server until they are run.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from wsproto.events import BytesMessage, TextMessage

from app.adapters.terminal import ConsoleProgram, Terminal, TerminalSize
from app.core.config import settings
from app.main import app
from app.terminals.consoles import ConsoleRefused
from tests.utils.socket import hung_up_on, open_socket, token_of

CONNECTORS = f"{settings.API_V1_STR}/connectors"
TERMINALS = "/terminals"


class _Screen:
    """A program that prints a prompt, echoes one line and ends."""

    def __init__(self) -> None:
        self._out = [b"test> "]
        self.typed = b""
        self.closed = False

    async def read(self) -> bytes:
        return self._out.pop(0) if self._out else b""

    async def write(self, data: bytes) -> None:
        self.typed += data

    def resize(self, size: TerminalSize) -> None:
        pass

    async def exit_status(self) -> int | None:
        return 0

    async def close(self) -> None:
        self.closed = True


class _Runner:
    def __init__(self, refusal: str | None = None) -> None:
        self.programs: list[ConsoleProgram] = []
        self.screens: list[_Screen] = []
        self._refusal = refusal

    async def open_console(
        self, program: ConsoleProgram, size: TerminalSize, *, owner: uuid.UUID
    ) -> Terminal:
        if self._refusal is not None:
            raise ConsoleRefused(self._refusal)
        self.programs.append(program)
        screen = _Screen()
        self.screens.append(screen)
        return screen


async def _mongodb(client: AsyncClient, headers: dict[str, str], **options: Any) -> str:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"mongodb {uuid.uuid4().hex[:8]}",
            "adapter_type": "mongodb",
            "options": {
                "auth_method": "user_password",
                "host": "mongodb",
                "user": "ann",
                "password": "secret-password",
                "database": "shop",
                **options,
            },
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _redis(client: AsyncClient, headers: dict[str, str], **options: Any) -> str:
    given = {
        "auth_method": "password",
        "host": "redis",
        "port": 6380,
        "database": 3,
        "password": "secret-password",
        **options,
    }
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"redis {uuid.uuid4().hex[:8]}",
            "adapter_type": "redis",
            # A None drops a field the other way of signing in does not have.
            "options": {key: value for key, value in given.items() if value is not None},
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _postgres(client: AsyncClient, headers: dict[str, str], **options: Any) -> str:
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"postgres {uuid.uuid4().hex[:8]}",
            "adapter_type": "postgres",
            "options": {
                "auth_method": "user_password",
                "host": "db",
                "port": 5433,
                "database": "shop",
                "user": "ann",
                "password": "secret-password",
                **options,
            },
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


def _opening(headers: dict[str, str], connector_id: str) -> dict[str, Any]:
    return {
        "type": "open",
        "token": token_of(headers),
        "connector_id": connector_id,
        "cols": 80,
        "rows": 24,
    }


async def _refused(first_frame: dict[str, Any]) -> dict[str, Any]:
    async with hung_up_on(TERMINALS) as ws:
        await ws.send_json(first_frame)
        frame: dict[str, Any] = await ws.receive_json(timeout=15)
        await ws.receive_json(timeout=5)
    return frame


async def test_mongosh_runs_signed_in_and_without_its_password_in_the_arguments(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _mongodb(client, normal_user_token_headers)

    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, connector_id))
        assert (await ws.receive_json(timeout=10))["type"] == "ready"
        event = await ws.receive(timeout=10)
        assert isinstance(event, BytesMessage)
        assert bytes(event.data) == b"test> "
        ended = await ws.receive(timeout=10)
        assert isinstance(ended, TextMessage)

    [program] = runner.programs
    assert program.argv[0] == "mongosh"
    assert "secret-password" not in " ".join(program.argv)
    assert program.environment["DP_MONGODB_URI"] == (
        "mongodb://ann:secret-password@mongodb:27017/shop?authSource=admin"
    )
    assert runner.screens[0].closed


async def test_redis_cli_runs_signed_in_and_without_its_password_in_the_arguments(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _redis(client, normal_user_token_headers)

    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, connector_id))
        assert (await ws.receive_json(timeout=10))["type"] == "ready"
        event = await ws.receive(timeout=10)
        assert isinstance(event, BytesMessage)
        await ws.receive(timeout=10)

    [program] = runner.programs
    assert program.argv == ("redis-cli", "-h", "redis", "-p", "6380", "-n", "3")
    assert dict(program.environment) == {"REDISCLI_AUTH": "secret-password"}


async def test_redis_cli_without_a_password_is_given_none(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _redis(
        client, normal_user_token_headers, auth_method="no_auth", password=None
    )

    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, connector_id))
        assert (await ws.receive_json(timeout=10))["type"] == "ready"
        await ws.receive(timeout=10)
        await ws.receive(timeout=10)

    [program] = runner.programs
    assert program.environment == {}


async def test_psql_runs_signed_in_and_without_its_password_in_the_arguments(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _postgres(client, normal_user_token_headers)

    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(normal_user_token_headers, connector_id))
        assert (await ws.receive_json(timeout=10))["type"] == "ready"
        await ws.receive(timeout=10)
        await ws.receive(timeout=10)

    [program] = runner.programs
    assert program.argv[0] == "psql"
    [conninfo] = program.argv[1:]
    for part in ("host=db", "port=5433", "dbname=shop", "user=ann"):
        assert part in conninfo
    assert "secret-password" not in conninfo
    assert dict(program.environment) == {"PGPASSWORD": "secret-password"}


async def test_a_server_that_runs_no_containers_says_so(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app.state, "console_runner", _Runner("Services are switched off"), raising=False
    )
    connector_id = await _mongodb(client, normal_user_token_headers)

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert (frame["code"], frame["message"]) == ("source", "Services are switched off")


async def test_without_a_runner_there_is_no_console(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app.state, "console_runner", None, raising=False)
    connector_id = await _mongodb(client, normal_user_token_headers)

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert frame["code"] == "unsupported"


@pytest.mark.parametrize("make", [_mongodb, _redis, _postgres])
async def test_a_console_does_not_go_through_a_tunnel(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    make: Any,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await make(client, normal_user_token_headers, ssh_tunnel=str(uuid.uuid4()))

    frame = await _refused(_opening(normal_user_token_headers, connector_id))

    assert (frame["code"], frame["error_kind"]) == ("source", "config")
    assert runner.programs == []


async def test_the_types_offer_a_terminal(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    types = await client.get(
        f"{settings.API_V1_STR}/adapter-types/", headers=normal_user_token_headers
    )

    assert types.status_code == 200, types.text
    for name in ("mongodb", "redis", "postgres"):
        [found] = [item for item in types.json() if item["name"] == name]
        assert "terminal" in {capability["code"] for capability in found["capabilities"]}

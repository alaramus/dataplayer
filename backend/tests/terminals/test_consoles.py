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
            "options": {
                key: value for key, value in given.items() if value is not None
            },
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _postgres(
    client: AsyncClient, headers: dict[str, str], **options: Any
) -> str:
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


async def _zookeeper(
    client: AsyncClient, headers: dict[str, str], **options: Any
) -> str:
    given = {
        "auth_method": "digest",
        "host": "zookeeper",
        "port": 2181,
        "chroot": "/apps",
        "user": "ann",
        "password": "secret-password",
        **options,
    }
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"zookeeper {uuid.uuid4().hex[:8]}",
            "adapter_type": "zookeeper",
            "options": {
                key: value for key, value in given.items() if value is not None
            },
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _kafka(client: AsyncClient, headers: dict[str, str], **options: Any) -> str:
    given = {
        "auth_method": "scram-sha-512",
        "bootstrap_servers": "kafka:9092",
        "user": "ann",
        "password": r'secret"pass\word',
        **options,
    }
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"kafka {uuid.uuid4().hex[:8]}",
            "adapter_type": "kafka",
            "options": {
                key: value for key, value in given.items() if value is not None
            },
        },
    )
    assert created.status_code == 200, created.text
    return str(created.json()["id"])


async def _rabbitmq(
    client: AsyncClient, headers: dict[str, str], **options: Any
) -> str:
    given = {
        "host": "rabbitmq",
        "port": 5672,
        "management_url": "http://rabbitmq:15672",
        "user": "ann",
        "password": 'secret"pass\\word\n=x',
        "vhost": "dp test/one",
        **options,
    }
    created = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"rabbitmq {uuid.uuid4().hex[:8]}",
            "adapter_type": "rabbitmq",
            "options": {
                key: value for key, value in given.items() if value is not None
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


async def _program_of(
    headers: dict[str, str], connector_id: str, runner: _Runner
) -> ConsoleProgram:
    async with open_socket(TERMINALS) as ws:
        await ws.send_json(_opening(headers, connector_id))
        assert (await ws.receive_json(timeout=10))["type"] == "ready"
        await ws.receive(timeout=10)
        await ws.receive(timeout=10)
    [program] = runner.programs
    return program


async def test_zkcli_runs_at_the_root_path_and_says_how_to_sign_in(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _zookeeper(client, normal_user_token_headers)

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    assert program.image.startswith("zookeeper:")
    assert program.argv[:2] == ("sh", "-c")
    assert "zkCli.sh -server" in program.argv[2]
    assert program.environment["ZK_SERVER"] == "zookeeper:2181/apps"
    # zkCli takes a digest identity only as `addauth`: the note says how, and
    # the password is nowhere (D299).
    assert "addauth digest ann:" in program.environment["ZK_NOTE"]
    assert "secret-password" not in repr(program.argv) + repr(dict(program.environment))


async def test_zkcli_for_an_anonymous_connection_has_no_note(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _zookeeper(
        client,
        normal_user_token_headers,
        auth_method="anonymous",
        user=None,
        password=None,
    )

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    assert set(program.environment) == {"ZK_SERVER", "CLIENT_JVMFLAGS"}
    assert program.environment["ZK_SERVER"] == "zookeeper:2181/apps"


async def test_kafka_s_tools_are_set_up_with_the_password_only_in_the_settings(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _kafka(client, normal_user_token_headers)

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    assert program.image.startswith("apache/kafka:")
    assert program.argv[:2] == ("sh", "-c")
    assert program.environment["KAFKA_BOOTSTRAP"] == "kafka:9092"
    assert "secret" not in repr(program.argv)
    # The JAAS line quotes the password, and the properties format escapes
    # that again, so its quote and backslash cannot end the value (D307).
    settings_text = program.environment["DP_PROPERTIES"]
    assert "sasl.mechanism=SCRAM-SHA-512" in settings_text
    assert r'password="secret\\"pass\\\\word";' in settings_text
    # The start file drops every variable that carried it before the prompt.
    assert "unset DP_PROPERTIES" in program.environment["DP_RC"]
    assert (
        'kafka-topics.sh() { _dp_run kafka-topics.sh "$@"; }'
        in program.environment["DP_RC"]
    )


async def test_kafka_s_tools_without_a_user_carry_no_sasl(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _kafka(
        client, normal_user_token_headers, auth_method="none", user=None, password=None
    )

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    assert "sasl" not in program.environment["DP_PROPERTIES"]
    assert "security.protocol=PLAINTEXT" in program.environment["DP_PROPERTIES"]
    assert "DP_CA" not in program.environment


async def test_rabbitmqadmin_is_set_up_with_the_password_only_in_its_file(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _rabbitmq(client, normal_user_token_headers)

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    assert program.image.startswith("rabbitmq:") and program.image.endswith(
        "-management"
    )
    assert program.argv[:2] == ("sh", "-c")
    assert "secret" not in repr(program.argv)
    assert program.environment["RABBITMQADMIN_CONFIG_FILE_PATH"] == (
        "/tmp/rabbitmqadmin.conf"
    )
    # A TOML basic string escapes the quote, the backslash and the line
    # break, so nothing in the password can end its value (D328).
    config = program.environment["DP_CONFIG"]
    assert config.startswith("[default]\n")
    assert 'base_uri = "http://rabbitmq:15672"' in config
    assert r'password = "secret\"pass\\word\n=x"' in config
    assert 'virtual_host = "dp test/one"' in config
    assert "tls" not in config
    # The start file drops every variable that carried it before the prompt.
    assert "unset DP_CONFIG DP_CA DP_RC" in program.environment["DP_RC"]
    assert "DP_CA" not in program.environment


async def test_rabbitmqadmin_without_a_virtual_host_uses_the_root_one(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await _rabbitmq(
        client,
        normal_user_token_headers,
        vhost=None,
        management_url="https://rabbitmq:15671",
        ca_certificate="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
    )

    program = await _program_of(normal_user_token_headers, connector_id, runner)

    config = program.environment["DP_CONFIG"]
    assert 'virtual_host = "/"' in config
    assert "tls = true" in config
    assert 'ca_certificate_bundle_path = "/tmp/ca.pem"' in config
    assert program.environment["DP_CA"].startswith("-----BEGIN CERTIFICATE-----")


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


@pytest.mark.parametrize("make", [_mongodb, _redis, _postgres, _zookeeper])
async def test_a_console_does_not_go_through_a_tunnel(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    make: Any,
) -> None:
    runner = _Runner()
    monkeypatch.setattr(app.state, "console_runner", runner, raising=False)
    connector_id = await make(
        client, normal_user_token_headers, ssh_tunnel=str(uuid.uuid4())
    )

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
    for name in ("mongodb", "redis", "postgres", "zookeeper", "kafka"):
        [found] = [item for item in types.json() if item["name"] == name]
        assert "terminal" in {
            capability["code"] for capability in found["capabilities"]
        }

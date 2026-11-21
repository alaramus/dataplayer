"""Metrics, and a container as a connection, without a daemon (D415, D417).

The `stats` answers are shaped as Engine 29.10 wrote them on the stand.
"""

import uuid
from typing import Any

import httpx
import pytest
from pydantic import TypeAdapter

from app.adapters.actions import ActionRefused, ConnectorDraft, PreparesConnector
from app.adapters.clickhouse.options import ClickhouseOptions
from app.adapters.docker.adapter import DockerAdapter
from app.adapters.docker.connect import address, environment
from app.adapters.docker.metrics import container_samples, cpu_percent, memory_used
from app.adapters.docker.options import DockerOptions
from app.adapters.mongodb.options import MongodbOptions
from app.adapters.mysql.options import MysqlOptions
from app.adapters.postgres.options import PostgresOptions
from app.adapters.redis.options import RedisOptions
from app.adapters.registry import repository_of, type_for_image

THROUGH = str(uuid.uuid4())
HEX = "b" * 64

STATS: dict[str, Any] = {
    "cpu_stats": {
        "cpu_usage": {"total_usage": 9_505_178_000},
        "system_cpu_usage": 15_026_554_000_000,
        "online_cpus": 24,
    },
    "precpu_stats": {
        "cpu_usage": {"total_usage": 8_501_240_000},
        "system_cpu_usage": 15_002_554_000_000,
    },
    "memory_stats": {
        "usage": 1_875_968,
        "limit": 16_299_216_896,
        "stats": {"inactive_file": 875_968},
    },
    "networks": {
        "eth0": {"rx_bytes": 4598, "tx_bytes": 126},
        "eth1": {"rx_bytes": 2, "tx_bytes": 4},
    },
    "blkio_stats": {
        "io_service_bytes_recursive": [
            {"major": 8, "minor": 48, "op": "read", "value": 1_490_944},
            {"major": 8, "minor": 48, "op": "write", "value": 0},
        ]
    },
    "pids_stats": {"current": 1},
}


def test_cpu_is_the_share_of_one_cpu_between_the_paired_samples() -> None:
    # A second of one CPU out of 24 seconds of 24 CPUs: one CPU, fully.
    assert cpu_percent(STATS) == pytest.approx(1_003_938_000 / 24_000_000_000 * 24 * 100)


def test_a_sample_without_its_pair_has_no_cpu() -> None:
    # What `one-shot` answers, and what a stopped container answers.
    lone = {**STATS, "precpu_stats": {"cpu_usage": {"total_usage": 0}}}
    assert cpu_percent(lone) is None
    assert cpu_percent({"cpu_stats": {}, "precpu_stats": {}}) is None


def test_memory_leaves_out_the_cache_the_kernel_may_take_back() -> None:
    assert memory_used(STATS) == 1_000_000
    cgroup_v1 = {"memory_stats": {"usage": 10, "stats": {"total_inactive_file": 4}}}
    assert memory_used(cgroup_v1) == 6
    assert memory_used({"memory_stats": {}}) is None


def test_traffic_and_disk_are_counters_summed_over_interfaces() -> None:
    found = {sample.field: sample for sample in container_samples("web", STATS)}
    assert found["network_in"].value == 4600 and found["network_in"].counter
    assert found["network_out"].value == 130
    assert found["disk_read"].value == 1_490_944 and found["disk_read"].counter
    assert found["disk_write"].value == 0
    assert found["processes"].value == 1
    assert not found["cpu"].counter and found["cpu"].unit == "%"
    assert {sample.label for sample in found.values()} == {"web"}


def test_a_stopped_container_gives_nothing_to_draw() -> None:
    stopped = {
        "cpu_stats": {"cpu_usage": {"total_usage": 0}},
        "memory_stats": {},
        "pids_stats": {},
        "blkio_stats": {"io_service_bytes_recursive": None},
    }
    assert container_samples("old", stopped) == []


# --- a container as a connection (D417) -------------------------------------------


@pytest.mark.parametrize(
    ("image", "repository"),
    [
        ("postgres", "postgres"),
        ("postgres:16-alpine", "postgres"),
        ("docker.io/library/postgres:16", "postgres"),
        ("postgres@sha256:" + "c" * 64, "postgres"),
        ("timescale/timescaledb:latest-pg16", "timescale/timescaledb"),
        ("localhost:5000/postgres", "localhost:5000/postgres"),
        ("ghcr.io/someone/postgres:1", "ghcr.io/someone/postgres"),
    ],
)
def test_an_image_is_its_repository_without_tag_or_docker_hub(image: str, repository: str) -> None:
    assert repository_of(image) == repository


def test_the_types_declare_their_images() -> None:
    found = {
        image: (declared[0].name if (declared := type_for_image(image)) else None)
        for image in (
            "postgres:17",
            "postgis/postgis:16-3.4",
            "mariadb:11",
            "mysql:8.4",
            "redis:7",
            "mongo:7",
            "clickhouse/clickhouse-server:24.8",
            "alpine:3.20",
            "ghcr.io/someone/postgres",
        )
    }
    assert found == {
        "postgres:17": "postgres",
        "postgis/postgis:16-3.4": "postgres",
        "mariadb:11": "mysql",
        "mysql:8.4": "mysql",
        "redis:7": "redis",
        "mongo:7": "mongodb",
        "clickhouse/clickhouse-server:24.8": "clickhouse",
        "alpine:3.20": None,
        "ghcr.io/someone/postgres": None,
    }


def _options(image: str, env: dict[str, str]) -> dict[str, Any]:
    declared = type_for_image(image)
    assert declared is not None
    return {**declared[1].options(env), "host": "10.0.0.2", "port": declared[1].port}


@pytest.mark.parametrize(
    ("image", "env", "schema", "expected"),
    [
        (
            "postgres:17",
            {"POSTGRES_PASSWORD": "pw"},
            PostgresOptions,
            {"auth_method": "user_password", "user": "postgres", "database": "postgres"},
        ),
        (
            "postgres:17",
            {"POSTGRES_USER": "app", "POSTGRES_PASSWORD": "pw", "POSTGRES_DB": "shop"},
            PostgresOptions,
            {"user": "app", "database": "shop"},
        ),
        (
            "postgres:17",
            {"POSTGRES_HOST_AUTH_METHOD": "trust"},
            PostgresOptions,
            {"auth_method": "no_auth"},
        ),
        (
            "mariadb:11",
            {"MARIADB_ROOT_PASSWORD": "pw", "MARIADB_DATABASE": "shop"},
            MysqlOptions,
            {"auth_method": "user_password", "user": "root", "database": "shop"},
        ),
        (
            "mysql:8.4",
            {"MYSQL_ROOT_PASSWORD": "r", "MYSQL_USER": "app", "MYSQL_PASSWORD": "pw"},
            MysqlOptions,
            {"user": "app"},
        ),
        (
            "mysql:8.4",
            {"MYSQL_ALLOW_EMPTY_PASSWORD": "yes"},
            MysqlOptions,
            {"auth_method": "no_password", "user": "root"},
        ),
        ("redis:7", {}, RedisOptions, {"auth_method": "no_auth"}),
        ("bitnami/redis:7", {"REDIS_PASSWORD": "pw"}, RedisOptions, {"auth_method": "password"}),
        (
            "mongo:7",
            {"MONGO_INITDB_ROOT_USERNAME": "root", "MONGO_INITDB_ROOT_PASSWORD": "pw"},
            MongodbOptions,
            {"auth_method": "user_password", "user": "root", "auth_source": "admin"},
        ),
        ("mongo:7", {}, MongodbOptions, {"auth_method": "no_password"}),
        (
            "clickhouse/clickhouse-server:24.8",
            {"CLICKHOUSE_PASSWORD": "pw"},
            ClickhouseOptions,
            {"auth_method": "user_password", "user": "default"},
        ),
    ],
)
def test_a_container_s_environment_makes_options_its_type_accepts(
    image: str, env: dict[str, str], schema: Any, expected: dict[str, Any]
) -> None:
    options = _options(image, env)
    assert expected.items() <= options.items()
    # A draft with a password is complete; the form is only finished.
    TypeAdapter(schema).validate_python(options)


def test_a_password_the_environment_does_not_hold_is_left_to_the_form() -> None:
    options = _options("postgres:17", {})
    assert "password" not in options


def test_the_first_of_a_repeated_name_is_read() -> None:
    assert environment({"Config": {"Env": ["A=1", "A=2", "B", "C=x=y"]}}) == {"A": "1", "C": "x=y"}


@pytest.mark.parametrize(
    ("inspected", "where"),
    [
        (
            {"NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "0.0.0.0", "HostPort": "15432"}]}}},
            ("127.0.0.1", 15432),
        ),
        (
            {"NetworkSettings": {"Ports": {"5432/tcp": [{"HostIp": "10.1.2.3", "HostPort": "5433"}]}}},
            ("10.1.2.3", 5433),
        ),
        (
            # Stopped: the bindings it asked for.
            {"HostConfig": {"PortBindings": {"5432/tcp": [{"HostIp": "", "HostPort": "6000"}]}}},
            ("127.0.0.1", 6000),
        ),
        (
            {
                "NetworkSettings": {
                    "Ports": {"5432/tcp": None},
                    "Networks": {"app": {"IPAddress": "172.18.0.5"}},
                }
            },
            ("172.18.0.5", 5432),
        ),
        ({"HostConfig": {"NetworkMode": "host"}}, ("127.0.0.1", 5432)),
        ({"NetworkSettings": {"Networks": {"app": {"IPAddress": ""}}}}, None),
    ],
)
def test_the_address_is_the_published_port_or_the_network_s(
    inspected: dict[str, Any], where: tuple[str, int] | None
) -> None:
    assert address(inspected, 5432) == where


def _inspected(image: str) -> dict[str, Any]:
    return {
        "Id": HEX,
        "Name": "/shop-db-1",
        "Config": {"Image": image, "Env": ["POSTGRES_PASSWORD=secret", "PATH=/usr/bin"]},
        "NetworkSettings": {"Networks": {"shop": {"IPAddress": "172.18.0.5"}}},
    }


def _adapter(inspected: dict[str, Any]) -> DockerAdapter:
    class _Loopback:
        async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
            raise AssertionError("not a port")

        async def socket_endpoint(self, connection_id: uuid.UUID, path: str) -> tuple[str, int]:
            return "127.0.0.1", 1

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/_ping":
            return httpx.Response(200, text="OK")
        if request.url.path == "/version":
            return httpx.Response(200, json={"ApiVersion": "1.57", "Version": "29.10.0"})
        if request.url.path.endswith(f"/containers/{HEX}/json"):
            return httpx.Response(200, json=inspected)
        return httpx.Response(404, json={"message": "no such container"})

    return DockerAdapter(
        DockerOptions(ssh_connection=THROUGH), _Loopback(), httpx.MockTransport(handler)
    )


async def test_a_database_container_drafts_a_connection_through_the_same_ssh() -> None:
    adapter = _adapter(_inspected("postgres:17"))
    offered = {action.name for action in await adapter.available(f"container:{HEX}")}
    assert "docker_open_as_connection" in offered
    action = adapter.action("docker_open_as_connection")
    assert isinstance(action, PreparesConnector)
    assert action.requires == "own"  # type: ignore[attr-defined] # an Action's declaration
    draft = await action.prepare_connector(f"container:{HEX}", {})
    assert draft == ConnectorDraft(
        name="shop-db-1",
        adapter_type="postgres",
        options={
            "auth_method": "user_password",
            "user": "postgres",
            "database": "postgres",
            "password": "secret",
            "host": "172.18.0.5",
            "port": 5432,
            "ssh_tunnel": THROUGH,
        },
    )


async def test_a_container_of_no_declared_image_is_not_offered_and_refused() -> None:
    adapter = _adapter(_inspected("alpine:3.20"))
    offered = {action.name for action in await adapter.available(f"container:{HEX}")}
    assert "docker_open_as_connection" not in offered
    action = adapter.action("docker_open_as_connection")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ActionRefused, match="alpine:3.20"):
        await action.prepare_connector(f"container:{HEX}", {})


async def test_a_container_without_an_address_is_refused_with_the_port() -> None:
    inspected = {**_inspected("postgres:17"), "NetworkSettings": {}}
    action = _adapter(inspected).action("docker_open_as_connection")
    assert isinstance(action, PreparesConnector)
    with pytest.raises(ActionRefused, match="5432"):
        await action.prepare_connector(f"container:{HEX}", {})

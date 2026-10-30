"""Databases read through the development SSH server as a tunnel (D282).

Needs `docker compose up -d sshd` and the database each test reads. The SSH
server reaches them by their service names on its own network — `db`,
`mysql`, `clickhouse`, `redis` — which is what a host "as that server sees it"
means, and what CI names its services too.
"""

import uuid
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.adapters.clickhouse.adapter import ClickhouseAdapter
from app.adapters.clickhouse.options import ClickhouseUserPassword
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.options import MysqlUserPassword
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.protocol import AdapterError
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.options import RedisNoAuth
from app.adapters.registry import AdapterContext
from app.adapters.ssh.adapter import SshAdapter
from app.adapters.ssh.options import SshPassword
from app.adapters.tunnels import reach
from tests.utils import services
from tests.utils.ssh import pinned_key

TUNNEL = str(uuid.uuid4())


class _Through:
    """The one SSH connection every tunnel of these tests goes through."""

    def __init__(self, ssh: SshAdapter) -> None:
        self._ssh = ssh

    async def endpoint(self, connection_id: uuid.UUID, host: str, port: int) -> tuple[str, int]:
        assert str(connection_id) == TUNNEL
        return await self._ssh.forward(host, port)


@pytest.fixture
async def through() -> _Through:
    parts = urlsplit(services.SSH.require())
    host, port = str(parts.hostname), parts.port or 22
    options = SshPassword.model_validate(
        {
            "auth_method": "password",
            "host": host,
            "port": port,
            "username": parts.username,
            "password": parts.password,
            "host_key": await pinned_key(host, port),
        }
    )
    return _Through(SshAdapter(options, AdapterContext(home_dir=Path("."))))


def _credentials(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return str(parts.username), str(parts.password)


async def test_postgres_is_read_through_the_ssh_server(through: _Through) -> None:
    parts = urlsplit(services.POSTGRES.require())
    options = PostgresUserPassword.model_validate(
        {
            "auth_method": "user_password",
            "host": "db",
            "port": 5432,
            "user": parts.username,
            "password": parts.password,
            "database": parts.path.lstrip("/"),
            "ssh_tunnel": TUNNEL,
        }
    )
    adapter = PostgresAdapter(options, tunnels=through)

    result = await adapter.check_connection()

    assert result.ok, result.message
    # The address is the database's, as the SSH server sees it, not a port
    # on this machine's loopback.
    assert "@db:5432/" in adapter.connection_string()


async def test_mysql_is_read_through_the_ssh_server(through: _Through) -> None:
    user, password = _credentials(services.MYSQL.require())
    options = MysqlUserPassword.model_validate(
        {
            "auth_method": "user_password",
            "host": "mysql",
            "port": 3306,
            "user": user,
            "password": password,
            "ssh_tunnel": TUNNEL,
        }
    )

    result = await MysqlAdapter(options, tunnels=through).check_connection()

    assert result.ok, result.message


async def test_clickhouse_is_read_through_the_ssh_server(through: _Through) -> None:
    user, password = _credentials(services.CLICKHOUSE.require())
    options = ClickhouseUserPassword.model_validate(
        {
            "auth_method": "user_password",
            "host": "clickhouse",
            "port": 8123,
            "user": user,
            "password": password,
            "ssh_tunnel": TUNNEL,
        }
    )

    result = await ClickhouseAdapter(options, tunnels=through).check_connection()

    assert result.ok, result.message


async def test_clickhouse_over_https_is_refused_through_a_tunnel(through: _Through) -> None:
    """A certificate names the server, never a port on this loopback."""
    options = ClickhouseUserPassword.model_validate(
        {
            "auth_method": "user_password",
            "host": "clickhouse",
            "port": 8443,
            "secure": True,
            "user": "default",
            "password": "irrelevant",
            "ssh_tunnel": TUNNEL,
        }
    )

    result = await ClickhouseAdapter(options, tunnels=through).check_connection()

    assert not result.ok
    assert result.error_kind == "config"
    assert "HTTPS" in result.message


async def test_redis_is_read_through_the_ssh_server(through: _Through) -> None:
    services.REDIS.require()
    options = RedisNoAuth.model_validate(
        {"auth_method": "no_auth", "host": "redis", "port": 6379, "ssh_tunnel": TUNNEL}
    )

    result = await RedisAdapter(options, tunnels=through).check_connection()

    assert result.ok, result.message


async def test_one_target_is_one_port_and_another_is_another(through: _Through) -> None:
    services.POSTGRES.require()
    first = await through.endpoint(uuid.UUID(TUNNEL), "db", 5432)
    again = await through.endpoint(uuid.UUID(TUNNEL), "db", 5432)
    other = await through.endpoint(uuid.UUID(TUNNEL), "redis", 6379)

    assert first == again
    assert first[0] == "127.0.0.1"
    assert other != first


async def test_a_target_the_ssh_server_cannot_reach_is_said_before_anything_dials(
    through: _Through,
) -> None:
    with pytest.raises(AdapterError) as refused:
        await reach(through, TUNNEL, "db", 1)

    assert refused.value.error_kind == "network"
    assert "db:1" in refused.value.message


async def test_a_dropped_ssh_connection_is_signed_into_again_on_the_same_port(
    through: _Through,
) -> None:
    from app.adapters.ssh.tunnel import TUNNELS

    parts = urlsplit(services.POSTGRES.require())
    options = PostgresUserPassword.model_validate(
        {
            "auth_method": "user_password",
            "host": "db",
            "port": 5432,
            "user": parts.username,
            "password": parts.password,
            "database": parts.path.lstrip("/"),
            "ssh_tunnel": TUNNEL,
        }
    )
    adapter = PostgresAdapter(options, tunnels=through)
    before = await through.endpoint(uuid.UUID(TUNNEL), "db", 5432)
    # What a network drop leaves behind: the listener, and a closed session.
    for forwarder in TUNNELS._forwarders.values():
        if forwarder._connection is not None:
            forwarder._connection.close()
            await forwarder._connection.wait_closed()

    result = await adapter.check_connection()

    assert result.ok, result.message
    assert await through.endpoint(uuid.UUID(TUNNEL), "db", 5432) == before

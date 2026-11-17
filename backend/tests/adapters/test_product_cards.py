"""Each product that is a card of a type answers that type's driver (D377).

A smoke test per product against its own image: the connection is checked,
the server names itself, and the catalog's top level opens. What the type does
beyond that is the type's own suite, run against its original.
"""

import uuid
from urllib.parse import urlsplit

import pytest
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import SecretStr
from starlette.concurrency import run_in_threadpool

from app.adapters.kafka.adapter import KafkaAdapter
from app.adapters.kafka.options import KafkaNoAuth
from app.adapters.mysql.adapter import MysqlAdapter
from app.adapters.mysql.options import MysqlUserPassword
from app.adapters.mysql.session import options_from_url
from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.options import RedisPassword
from tests.utils.services import (
    CITUS,
    KEYDB,
    PARADEDB,
    PERCONA,
    REDPANDA,
    VALKEY,
    Server,
)


def _redis(server: Server) -> RedisAdapter:
    parts = urlsplit(server.require())
    return RedisAdapter(
        RedisPassword(
            auth_method="password",
            host=parts.hostname or "127.0.0.1",
            port=parts.port or 6379,
            database=int(parts.path.lstrip("/") or 0),
            password=SecretStr(parts.password or ""),
        )
    )


def _postgres(server: Server) -> PostgresAdapter:
    parts = urlsplit(server.require())
    return PostgresAdapter(
        PostgresUserPassword(
            auth_method="user_password",
            host=parts.hostname or "127.0.0.1",
            port=parts.port or 5432,
            database=parts.path.lstrip("/") or "postgres",
            user=parts.username or "postgres",
            password=SecretStr(parts.password or ""),
        )
    )


def _bootstrap() -> str:
    parts = urlsplit(REDPANDA.require())
    return f"{parts.hostname or '127.0.0.1'}:{parts.port or 9092}"


@pytest.mark.parametrize(
    ("server", "named"),
    [(VALKEY, "Valkey "), (KEYDB, "KeyDB ")],
    ids=["valkey", "keydb"],
)
async def test_a_redis_fork_answers_and_names_itself(server: Server, named: str) -> None:
    adapter = _redis(server)

    result = await adapter.check_connection()
    features = await adapter.source_features()
    top = await adapter.list_children(None)

    assert result.ok, result.message
    assert features.server_version is not None
    assert features.server_version.startswith(named)
    assert top is not None


async def test_percona_server_answers_and_names_itself() -> None:
    adapter = MysqlAdapter(MysqlUserPassword(**options_from_url(PERCONA.require())))

    result = await adapter.check_connection()
    features = await adapter.source_features()
    databases = {node.name for node in await adapter.list_children(None)}

    assert result.ok, result.message
    assert features.server_version is not None
    assert features.server_version.startswith("Percona Server 8.4")
    assert "mysql" in databases


@pytest.mark.parametrize(
    ("server", "extension"),
    [(CITUS, "citus"), (PARADEDB, "pg_search")],
    ids=["citus", "paradedb"],
)
async def test_a_postgres_extension_image_answers_with_its_extension(
    server: Server, extension: str
) -> None:
    adapter = _postgres(server)

    result = await adapter.check_connection()
    features = await adapter.source_features()
    schemas = {node.name for node in await adapter.list_children(None)}

    assert result.ok, result.message
    assert extension in {found.name for found in features.extensions}
    assert "public" in schemas


async def test_redpanda_answers_kafka_s_driver_and_lists_a_topic() -> None:
    topic = f"dp-test-{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": _bootstrap()})
    for future in admin.create_topics([NewTopic(topic, num_partitions=1)]).values():
        await run_in_threadpool(future.result, 15)
    try:
        adapter = KafkaAdapter(KafkaNoAuth(bootstrap_servers=_bootstrap()))
        result = await adapter.check_connection()
        top = [node.id for node in await adapter.list_children(None)]
        topics = {node.name for node in await adapter.list_children("topics")}
    finally:
        for future in admin.delete_topics([topic]).values():
            await run_in_threadpool(future.result, 15)

    assert result.ok, result.message
    assert top == ["cluster", "topics", "groups", "internal"]
    assert topic in topics

"""Sources signing in with what a cloud account issues (D449, D450, D453, D454).

The account is a stand-in that hands out what the test says, so the servers
are real and only the cloud is not: PostgreSQL behind verified TLS with an
IAM-shaped variant, MySQL with a password from a store, Redis over TLS with a
token for its ACL user, S3 with an account's keys. Each is skipped without its
server. MongoDB's and Kafka's are proven by what their drivers are handed.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiomysql
import psycopg
import pytest
from psycopg import sql

from app.adapters.cloud import AccountKind, IssuedSecret, SecretRequest
from app.adapters.cloud.requests import (
    CloudCredentials,
    MskToken,
    RdsAuthToken,
    StoredSecret,
)
from app.adapters.kafka.console import client_properties
from app.adapters.kafka.options import KafkaAwsMskIam
from app.adapters.kafka.session import KafkaSession
from app.adapters.mongodb import session as mongodb_session
from app.adapters.mongodb.options import MongodbAwsIam, MongodbSecretStore
from app.adapters.mongodb.session import auth_query, make_client
from app.adapters.mysql.options import MysqlAwsIam, MysqlSecretStore
from app.adapters.mysql.session import MysqlSession
from app.adapters.postgres.options import PostgresAwsIam, PostgresSecretStore
from app.adapters.postgres.pool import PooledConnections, key_for
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import AdapterError
from app.adapters.redis.adapter import RedisAdapter
from app.adapters.redis.options import RedisAwsIam
from app.adapters.registry import AdapterContext
from app.adapters.resources import Pooling, ResourceStore
from app.adapters.s3.adapter import S3Adapter
from app.adapters.s3.options import S3CloudAccount
from tests.utils import services

ACCOUNT = str(uuid.uuid4())


class Cloud:
    """An account that answers what `answer` says, and remembers every ask."""

    def __init__(self, answer: Callable[[SecretRequest], IssuedSecret]) -> None:
        self.answer = answer
        self.asked: list[SecretRequest] = []

    async def issue(
        self, account_id: uuid.UUID, kinds: tuple[AccountKind, ...], request: SecretRequest
    ) -> IssuedSecret:
        assert str(account_id) == ACCOUNT
        self.asked.append(request)
        return self.answer(request)


def _token(value: str, user: str | None = None, seconds: float = 900) -> IssuedSecret:
    return IssuedSecret(value=value, expires_at=time.time() + seconds, user=user)


def _verified() -> dict[str, Any]:
    ca = (services.tls_test_certificates() / "ca.crt").read_text(encoding="ascii")
    return {"tls_mode": "verify_full", "tls_trust": "certificate", "tls_ca_certificate": ca}


# --- PostgreSQL: a pool that never keys on its token (D450) ----------------------


@pytest.fixture
async def pg_role() -> AsyncIterator[tuple[str, Callable[[str], Any]]]:
    """A role on pg-tls whose password the test changes, and how to change it."""
    url = services.PG_TLS.require()
    role = f"iam_{uuid.uuid4().hex[:8]}"
    admin = await psycopg.AsyncConnection.connect(url, sslmode="require", autocommit=True)

    async def password(value: str) -> None:
        await admin.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(value))
        )

    await admin.execute(
        sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal("tok-1"))
    )
    try:
        yield role, password
    finally:
        await admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
        await admin.close()


async def test_a_pool_signs_every_new_connection_in_with_the_token_issued_then(
    pg_role: tuple[str, Callable[[str], Any]],
) -> None:
    role, change_password = pg_role
    parts = urlsplit(services.PG_TLS.require())
    options = PostgresAwsIam(
        host=parts.hostname or "",
        port=parts.port or 5432,
        database="postgres",
        user=role,
        account=ACCOUNT,
        region="eu-west-1",
        **_verified(),
    )
    issued = ["tok-1"]
    cloud = Cloud(lambda _: _token(issued[-1]))
    store = ResourceStore(max_entries=4, max_idle_seconds=300.0)
    connector = uuid.uuid4()
    session = PostgresSession(options, Pooling(store=store, connector_id=connector), cloud=cloud)
    key = key_for(connector, session.pool_identity((options.host, options.port)))
    try:
        async with session.acquire() as first:
            pool = await store.existing(key, PooledConnections)
            # The token the first connection signed in with stops working.
            await change_password("tok-2")
            issued.append("tok-2")
            async with session.acquire() as second:
                answer = await (await second.execute("SELECT current_user")).fetchone()
                assert answer == (role,)
            # A connection already open keeps working with the old token.
            assert await (await first.execute("SELECT 1")).fetchone() == (1,)

        assert pool is not None
        assert await store.existing(key, PooledConnections) is pool
        assert issued[-1] not in key and "tok-1" not in key
        asked = [one for one in cloud.asked if isinstance(one, RdsAuthToken)]
        assert len(asked) >= 2
        # Signed for the form's host, the one RDS checks.
        assert {(one.host, one.port, one.user) for one in asked} == {(options.host, options.port, role)}
    finally:
        await store.aclose()


async def test_an_iam_token_is_never_sent_without_tls() -> None:
    with pytest.raises(ValueError, match="needs TLS"):
        PostgresAwsIam(host="db", database="app", user="u", account=ACCOUNT, tls_mode="disabled")


async def test_a_stored_secret_names_the_user_when_the_form_does_not() -> None:
    options = PostgresSecretStore(host="db", database="app", account=ACCOUNT, secret_name="prod/db")
    cloud = Cloud(lambda _: IssuedSecret(value="s3cret", expires_at=None, user="app"))

    credentials = await PostgresSession(options, cloud=cloud).credentials()

    assert credentials == {"user": "app", "password": "s3cret"}
    assert cloud.asked == [StoredSecret("prod/db", "password", "username")]


async def test_a_secret_without_a_user_and_a_form_without_one_is_refused() -> None:
    options = PostgresSecretStore(host="db", database="app", account=ACCOUNT, secret_name="plain")
    cloud = Cloud(lambda _: IssuedSecret(value="s3cret", expires_at=None))

    with pytest.raises(AdapterError) as refused:
        await PostgresSession(options, cloud=cloud).credentials()

    assert "username" in refused.value.message and "s3cret" not in refused.value.message


async def test_a_source_built_without_its_owner_s_accounts_says_so() -> None:
    options = PostgresSecretStore(host="db", database="app", account=ACCOUNT, secret_name="x")

    with pytest.raises(AdapterError) as refused:
        await PostgresSession(options).credentials()

    assert refused.value.error_kind == "config"


# --- MySQL: a pool told the next password before every checkout ------------------


async def test_a_mysql_pool_opens_its_next_connection_with_the_password_read_then() -> None:
    parts = urlsplit(services.MYSQL.require())
    user = f"store_{uuid.uuid4().hex[:8]}"
    admin = await aiomysql.connect(
        host=parts.hostname, port=parts.port, user=parts.username, password=parts.password, autocommit=True
    )
    async with admin.cursor() as cursor:
        await cursor.execute("CREATE USER %s@'%%' IDENTIFIED BY 'pw-1'", (user,))
    options = MysqlSecretStore(
        host=parts.hostname or "",
        port=parts.port or 3306,
        database="",
        account=ACCOUNT,
        secret_name="mysql/app",
    )
    issued = ["pw-1"]
    cloud = Cloud(lambda _: IssuedSecret(value=issued[-1], expires_at=None, user=user))
    store = ResourceStore(max_entries=4, max_idle_seconds=300.0)
    session = MysqlSession(options, Pooling(store=store, connector_id=uuid.uuid4()), cloud=cloud)
    try:
        async with session.acquire() as first:
            async with admin.cursor() as cursor:
                await cursor.execute("ALTER USER %s@'%%' IDENTIFIED BY 'pw-2'", (user,))
            issued.append("pw-2")
            async with session.acquire() as second, second.cursor() as cursor:
                await cursor.execute("SELECT CURRENT_USER()")
                assert str((await cursor.fetchone())[0]).startswith(f"{user}@")
            async with first.cursor() as cursor:
                await cursor.execute("SELECT 1")
                assert (await cursor.fetchone())[0] == 1
    finally:
        await store.aclose()
        async with admin.cursor() as cursor:
            await cursor.execute("DROP USER IF EXISTS %s@'%%'", (user,))
        admin.close()


async def test_an_rds_token_goes_to_mysql_in_the_clear_and_only_over_verified_tls() -> None:
    options = MysqlAwsIam(
        host="db.example.com", database="app", user="iam", account=ACCOUNT, tls_mode="verify_full"
    )
    cloud = Cloud(lambda _: _token("signed-token"))

    credentials = await MysqlSession(options, cloud=cloud)._credentials()  # noqa: SLF001 - what aiomysql is handed

    assert credentials == {"user": "iam", "password": "signed-token", "auth_plugin": "mysql_clear_password"}
    with pytest.raises(ValueError, match="in the clear"):
        MysqlAwsIam(host="db", database="app", user="iam", account=ACCOUNT, tls_mode="required")


# --- Redis: a token for an ACL user over TLS ------------------------------------


async def test_redis_signs_in_with_the_issued_token_as_its_user() -> None:
    parts = urlsplit(services.REDIS_TLS.require())
    options = RedisAwsIam(
        host=parts.hostname or "",
        port=parts.port or 6379,
        user="reader",
        cache_name="orders",
        account=ACCOUNT,
        **_verified(),
    )
    # redis-tls knows `reader` by a password; the token stands in for it.
    cloud = Cloud(lambda _: _token("dataplayer"))

    result = await RedisAdapter(options, cloud=cloud).check_connection()

    assert result.ok, result.message
    assert len(cloud.asked) == 1


def test_an_elasticache_token_is_never_sent_without_tls() -> None:
    with pytest.raises(ValueError, match="needs TLS"):
        RedisAwsIam(host="c", user="u", cache_name="c", account=ACCOUNT, tls_mode="disabled")


# --- MongoDB: MONGODB-AWS with the account's keys -------------------------------


async def test_mongodb_is_handed_the_account_s_keys_for_mongodb_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    made: dict[str, Any] = {}
    monkeypatch.setattr(mongodb_session, "AsyncMongoClient", lambda **kwargs: made.update(kwargs))
    options = MongodbAwsIam(host="cluster.example.com", account=ACCOUNT, region="eu-west-1")
    cloud = Cloud(
        lambda _: IssuedSecret(value="SECRET", user="ASIAKEY", session_token="TOKEN", expires_at=None)
    )

    signed = await options.sign_in(cloud)
    make_client("cluster.example.com", 27017, options, signed, pool_size=1)

    assert cloud.asked == [CloudCredentials(region="eu-west-1")]
    assert (made["username"], made["password"], made["authSource"]) == ("ASIAKEY", "SECRET", "$external")
    assert made["authMechanism"] == "MONGODB-AWS"
    assert made["authMechanismProperties"] == {"AWS_SESSION_TOKEN": "TOKEN"}
    assert ("authMechanism", "MONGODB-AWS") in auth_query(signed)
    assert "SECRET" not in repr(signed)


async def test_mongodb_reads_a_stored_password_into_its_own_auth_source() -> None:
    options = MongodbSecretStore(
        host="db", account=ACCOUNT, secret_name="mongo", user="app", auth_source="orders"
    )
    cloud = Cloud(lambda _: IssuedSecret(value="s3cret", expires_at=None, user="ignored"))

    signed = await options.sign_in(cloud)

    assert (signed.user, signed.password, signed.auth_source, signed.mechanism) == ("app", "s3cret", "orders", "")


# --- Kafka: MSK's token, renewed from librdkafka's thread ------------------------


async def test_msk_is_given_a_token_and_asks_the_loop_again_before_it_expires() -> None:
    options = KafkaAwsMskIam(
        bootstrap_servers="b-1.msk.example.com:9098", account=ACCOUNT, region="eu-west-1", tls_mode="verify_full"
    )
    tokens = iter([_token("first", seconds=30), _token("second")])
    cloud = Cloud(lambda _: next(tokens))
    session = KafkaSession(options, cloud)

    config = session.config(await options.token(cloud))
    renewed = await asyncio.to_thread(config["oauth_cb"], "")

    assert config["sasl.mechanism"] == "OAUTHBEARER" and config["security.protocol"] == "SASL_SSL"
    assert renewed[0] == "second" and renewed[1] > time.time() + 800
    assert cloud.asked == [MskToken("eu-west-1"), MskToken("eu-west-1")]


async def test_a_token_still_good_is_handed_back_without_asking() -> None:
    options = KafkaAwsMskIam(bootstrap_servers="b:9098", account=ACCOUNT, tls_mode="verify_full")
    cloud = Cloud(lambda _: _token("only"))
    session = KafkaSession(options, cloud)

    config = session.config(await options.token(cloud))
    value, _ = await asyncio.to_thread(config["oauth_cb"], "")

    assert value == "only" and len(cloud.asked) == 1


def test_kafka_s_tools_say_they_cannot_sign_in_to_msk_yet() -> None:
    options = KafkaAwsMskIam(bootstrap_servers="b:9098", account=ACCOUNT, tls_mode="verify_full")

    with pytest.raises(AdapterError, match="cannot sign in with AWS IAM"):
        client_properties(options)


# --- S3: an account's keys, asked by the client from its worker thread ----------


async def test_s3_reads_a_store_with_the_account_s_keys(tmp_path: Path) -> None:
    parts = urlsplit(services.S3.require())
    options = S3CloudAccount(endpoint=f"http://{parts.hostname}:{parts.port}", account=ACCOUNT)
    cloud = Cloud(lambda _: IssuedSecret(value=parts.password or "", user=parts.username, expires_at=None))

    result = await S3Adapter(options, AdapterContext(home_dir=tmp_path, cloud=cloud)).check_connection()

    assert result.ok, result.message
    assert cloud.asked and all(isinstance(one, CloudCredentials) for one in cloud.asked)


async def test_s3_without_its_owner_s_accounts_says_so(tmp_path: Path) -> None:
    options = S3CloudAccount(endpoint="http://127.0.0.1:1", account=ACCOUNT, bucket="b")

    result = await S3Adapter(options, AdapterContext(home_dir=tmp_path)).check_connection()

    assert not result.ok
    assert "none is at hand" in result.message


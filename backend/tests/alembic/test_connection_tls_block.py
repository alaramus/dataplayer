"""The data migration that turns a TLS switch into the TLS block (D446)."""

import importlib
from typing import Any

import pytest
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as options_schema
from app.adapters import registry
from app.connectors.models import Connector
from tests.utils.user import create_random_user

migration = importlib.import_module(
    "app.alembic.versions.d7e2f9a4c1b8_connection_tls_block"
)

# What a form of each type held before the block, and what a validated model
# needs besides it (the secrets live apart and are not migrated).
_OLD: list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]] = [
    (
        "mongodb",
        {"host": "db", "port": 27017, "tls": True, "auth_method": "no_password"},
        {},
        {"tls_mode": "verify_full"},
    ),
    (
        "clickhouse",
        {"host": "ch", "port": 8443, "secure": True, "auth_method": "no_password", "user": "default"},
        {},
        {"tls_mode": "verify_full"},
    ),
    (
        "cassandra",
        {"host": "cs", "port": 9042, "secure": False, "auth_method": "no_password"},
        {},
        {"tls_mode": "disabled"},
    ),
    (
        "zookeeper",
        {"host": "zk", "port": 2281, "tls": True, "auth_method": "anonymous"},
        {},
        {"tls_mode": "verify_ca"},
    ),
    (
        "kafka",
        {
            "bootstrap_servers": "broker:9093",
            "tls": True,
            "ca_certificate": "PLACEHOLDER",
            "auth_method": "none",
        },
        {},
        {"tls_mode": "verify_full", "tls_trust": "certificate"},
    ),
    (
        "rabbitmq",
        {"host": "mq", "port": 5672, "tls": False, "ca_certificate": "", "user": "guest"},
        {"password": "guest"},
        {"tls_mode": "disabled"},
    ),
]


@pytest.fixture
def ca_pem() -> str:
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test ca")])
    now = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode()


async def test_an_old_switch_becomes_the_mode_it_meant(db: AsyncSession, ca_pem: str) -> None:
    user = await create_random_user(db)
    made: list[tuple[Connector, dict[str, Any], dict[str, Any]]] = []
    for adapter_type, config, secrets, expected in _OLD:
        stored = {
            key: (ca_pem if value == "PLACEHOLDER" else value) for key, value in config.items()
        }
        connector = Connector(
            name=f"old {adapter_type}",
            adapter_type=adapter_type,
            config=stored,
            secrets=b"x",
            owner_id=user.id,
        )
        db.add(connector)
        made.append((connector, secrets, expected))
    await db.commit()

    await db.exec(text(migration.UPGRADE))  # type: ignore[call-overload]  # a raw statement, as Alembic runs it
    await db.commit()

    for connector, secrets, expected in made:
        await db.refresh(connector)
        config = connector.config
        for key, value in expected.items():
            assert config[key] == value, (connector.adapter_type, key)
        assert not {"tls", "secure", "ca_certificate"} & config.keys()
        if expected.get("tls_trust") == "certificate":
            assert config["tls_ca_certificate"] == ca_pem
        # The row opens with today's model: nothing it holds is refused.
        schema = registry.get(connector.adapter_type).options_schema
        options_schema.validate(schema, {**config, **secrets})


async def test_a_row_already_migrated_is_left_alone(db: AsyncSession) -> None:
    user = await create_random_user(db)
    connector = Connector(
        name="new mongodb",
        adapter_type="mongodb",
        config={"host": "db", "tls_mode": "verify_ca", "auth_method": "no_password"},
        secrets=b"x",
        owner_id=user.id,
    )
    db.add(connector)
    await db.commit()

    await db.exec(text(migration.UPGRADE))  # type: ignore[call-overload]  # a raw statement, as Alembic runs it
    await db.commit()
    await db.refresh(connector)

    assert connector.config["tls_mode"] == "verify_ca"


async def test_postgres_and_mysql_need_no_migration() -> None:
    """Their default is what they did: libpq's `prefer`, MySQL's unverified TLS."""
    for adapter_type, auth in (("postgres", "no_auth"), ("mysql", "no_password")):
        schema = registry.get(adapter_type).options_schema
        old = {"host": "h", "port": 1, "database": "d", "user": "u", "auth_method": auth}
        model = options_schema.validate(schema, old)
        assert model.tls().mode == "preferred"  # type: ignore[attr-defined]  # every variant has the block

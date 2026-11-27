"""The data migration that names how an old S3 connection signs in (D453)."""

import importlib

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options as options_schema
from app.adapters import registry
from app.connectors.models import Connector
from tests.utils.user import create_random_user

migration = importlib.import_module("app.alembic.versions.f2a9d4c7e1b3_s3_auth_method")

OLD = {"endpoint": "https://s3.example.com", "region": "", "access_key_id": "key", "bucket": "b"}


async def _run(db: AsyncSession, statement: str) -> None:
    await db.exec(text(statement))  # type: ignore[call-overload]  # a raw statement, as Alembic runs it
    await db.commit()


async def test_an_old_s3_connection_signs_in_with_its_key(db: AsyncSession) -> None:
    user = await create_random_user(db)
    old = Connector(name="old s3", adapter_type="s3", config=dict(OLD), secrets=b"x", owner_id=user.id)
    other = Connector(
        name="old mongodb",
        adapter_type="mongodb",
        config={"host": "db", "auth_method": "no_password"},
        secrets=b"x",
        owner_id=user.id,
    )
    db.add_all([old, other])
    await db.commit()

    await _run(db, migration.UPGRADE)
    await db.refresh(old)
    await db.refresh(other)

    assert old.config == {**OLD, "auth_method": "access_key"}
    assert other.config == {"host": "db", "auth_method": "no_password"}
    # The row opens with today's model, its secret beside it as it is kept.
    schema = registry.get("s3").options_schema
    options_schema.validate(schema, {**old.config, "secret_access_key": "secret"})


async def test_an_account_s3_connection_is_left_alone_both_ways(db: AsyncSession) -> None:
    user = await create_random_user(db)
    config = {"endpoint": "", "region": "", "auth_method": "aws_account", "account": "x"}
    connector = Connector(name="new s3", adapter_type="s3", config=dict(config), secrets=b"x", owner_id=user.id)
    db.add(connector)
    await db.commit()

    await _run(db, migration.UPGRADE)
    await _run(db, migration.DOWNGRADE)
    await db.refresh(connector)

    assert connector.config == config


async def test_going_back_takes_the_key_s_name_off(db: AsyncSession) -> None:
    user = await create_random_user(db)
    connector = Connector(
        name="keyed s3",
        adapter_type="s3",
        config={**OLD, "auth_method": "access_key"},
        secrets=b"x",
        owner_id=user.id,
    )
    db.add(connector)
    await db.commit()

    await _run(db, migration.DOWNGRADE)
    await db.refresh(connector)

    assert connector.config == OLD

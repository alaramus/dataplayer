"""The data migration that gives stored connectors a discriminator.

Pydantic refuses an object that names no variant (`union_tag_not_found`), so
the moment PostgreSQL options become a union every connector saved before it
stops being readable — and a connector that cannot be read cannot be opened,
checked or browsed. That is a failure at the first request rather than at
startup, which is exactly why the migration is tested rather than trusted.

The test runs the statement the revision runs, against a row shaped the way
rows were shaped before it.
"""

import importlib.util
import json
import uuid
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters import options, registry
from app.connectors.models import Connector
from app.core import crypto
from app.users.models import User
from tests.utils.user import create_random_user

REVISION = "a7f1c2d43b90_add_auth_method_to_postgres_connectors"

# The options of a connector as they were stored before the variants: no
# `auth_method` anywhere.
LEGACY_CONFIG = {
    "host": "db.example.com",
    "port": 5432,
    "database": "analytics",
    "user": "reader",
}

# The same connector as the driver is handed it: the password comes back out
# of the encrypted blob before anything is validated. Stated separately so the
# test below fails for the reason it names — a config without a password is
# refused whether there are variants or not.
LEGACY_OPTIONS = {**LEGACY_CONFIG, "password": "s3cret"}


def _revision() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "alembic"
        / "versions"
        / f"{REVISION}.py"
    )
    spec = importlib.util.spec_from_file_location(REVISION, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _legacy_connector(db: AsyncSession, owner: User) -> Connector:
    connector = Connector(
        name=f"legacy {uuid.uuid4()}",
        adapter_type="postgres",
        config=dict(LEGACY_CONFIG),
        secrets=crypto.encrypt(json.dumps({"password": "s3cret"}).encode(), purpose="connector"),
        owner_id=owner.id,
    )
    db.add(connector)
    await db.commit()
    await db.refresh(connector)
    return connector


async def _run(db: AsyncSession, statement: str) -> None:
    await db.exec(text(statement))  # type: ignore[call-overload]
    await db.commit()


async def _config_of(db: AsyncSession, connector: Connector) -> dict[str, object]:
    db.expire(connector)
    await db.refresh(connector)
    return connector.config


async def test_a_connector_saved_before_the_variants_is_unreadable(
    db: AsyncSession,
) -> None:
    """The failure the migration exists to prevent, stated first."""
    schema = registry.get("postgres").options_schema

    with pytest.raises(ValidationError, match="union_tag_not_found"):
        options.validate(schema, LEGACY_OPTIONS)


async def test_the_migration_makes_it_readable_again(db: AsyncSession) -> None:
    owner = await create_random_user(db)
    connector = await _legacy_connector(db, owner)

    await _run(db, _revision().FILL_AUTH_METHOD)

    config = await _config_of(db, connector)
    assert config["auth_method"] == "user_password"
    model = options.validate(
        registry.get("postgres").options_schema, {**config, "password": "s3cret"}
    )
    assert model.model_dump()["host"] == "db.example.com"


async def test_the_migration_leaves_a_stated_method_alone(db: AsyncSession) -> None:
    """It fills what is missing; it does not overwrite what is there."""
    owner = await create_random_user(db)
    connector = Connector(
        name=f"already {uuid.uuid4()}",
        adapter_type="postgres",
        config={**LEGACY_CONFIG, "auth_method": "no_auth"},
        secrets=crypto.encrypt(b"{}", purpose="connector"),
        owner_id=owner.id,
    )
    db.add(connector)
    await db.commit()

    await _run(db, _revision().FILL_AUTH_METHOD)

    config = await _config_of(db, connector)
    assert config["auth_method"] == "no_auth"


async def test_the_migration_touches_no_other_source_type(db: AsyncSession) -> None:
    """A file connector has no way of being authenticated to."""
    owner = await create_random_user(db)
    connector = Connector(
        name=f"files {uuid.uuid4()}",
        adapter_type="file",
        config={"path": ""},
        secrets=crypto.encrypt(b"{}", purpose="connector"),
        owner_id=owner.id,
    )
    db.add(connector)
    await db.commit()

    await _run(db, _revision().FILL_AUTH_METHOD)

    assert await _config_of(db, connector) == {"path": ""}


async def test_going_back_removes_the_key_again(db: AsyncSession) -> None:
    owner = await create_random_user(db)
    connector = await _legacy_connector(db, owner)

    await _run(db, _revision().FILL_AUTH_METHOD)
    await _run(db, _revision().DROP_AUTH_METHOD)

    assert await _config_of(db, connector) == LEGACY_CONFIG

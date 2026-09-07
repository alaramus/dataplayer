"""The data migration that gives stored file paths their leading separator.

Nothing stops working without it: the driver joins from the folder either way.
What it prevents is two forms of the same path in one table — the root written
as the empty string beside the root written as "/" — so the test runs the
statement the revision runs against rows shaped the way rows were shaped
before it.
"""

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.file.options import FileOptions
from app.connectors.models import Connector
from app.core import crypto
from app.users.models import User
from tests.utils.user import create_random_user

REVISION = "d5c81a3f7b62_root_file_connector_paths"


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


async def _connector(
    db: AsyncSession, owner: User, adapter_type: str, config: dict[str, object]
) -> Connector:
    connector = Connector(
        name=f"legacy {uuid.uuid4()}",
        adapter_type=adapter_type,
        config=config,
        secrets=crypto.encrypt(b"{}", purpose="connector"),
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


async def test_the_root_stops_being_the_empty_string(db: AsyncSession) -> None:
    owner = await create_random_user(db)
    connector = await _connector(db, owner, "file", {"path": ""})

    await _run(db, _revision().ROOT_FILE_PATHS)

    assert await _config_of(db, connector) == {"path": "/"}


async def test_a_folder_keeps_its_name_and_gains_a_separator(
    db: AsyncSession,
) -> None:
    owner = await create_random_user(db)
    connector = await _connector(db, owner, "file", {"path": "reports/2026"})

    await _run(db, _revision().ROOT_FILE_PATHS)

    config = await _config_of(db, connector)
    assert config == {"path": "/reports/2026"}
    assert FileOptions.model_validate(config).below_home == "reports/2026"


async def test_running_it_again_changes_nothing(db: AsyncSession) -> None:
    """Only rows that are not rooted yet are touched."""
    owner = await create_random_user(db)
    connector = await _connector(db, owner, "file", {"path": "/reports"})

    await _run(db, _revision().ROOT_FILE_PATHS)

    assert await _config_of(db, connector) == {"path": "/reports"}


async def test_the_migration_touches_no_other_source_type(db: AsyncSession) -> None:
    """A database is not addressed by a path."""
    owner = await create_random_user(db)
    connector = await _connector(
        db, owner, "postgres", {"host": "db.example.com", "database": "analytics"}
    )

    await _run(db, _revision().ROOT_FILE_PATHS)

    assert await _config_of(db, connector) == {
        "host": "db.example.com",
        "database": "analytics",
    }


async def test_going_back_leaves_the_paths_as_they_were(db: AsyncSession) -> None:
    owner = await create_random_user(db)
    root = await _connector(db, owner, "file", {"path": ""})
    folder = await _connector(db, owner, "file", {"path": "reports"})

    await _run(db, _revision().ROOT_FILE_PATHS)
    await _run(db, _revision().UNROOT_FILE_PATHS)

    assert await _config_of(db, root) == {"path": ""}
    assert await _config_of(db, folder) == {"path": "reports"}

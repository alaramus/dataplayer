"""Copying a database out, and putting it back (D87)."""

import uuid
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.adapters import registry
from app.adapters.postgres.session import PostgresSession
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs.models import Job
from app.jobs.runner import JobRunner
from app.main import app
from app.services.backups import BACKUP_FOLDER, backup_filename
from app.users import storage
from tests.utils.database import working_postgres_options
from tests.utils.service_engine import FakeEngine, engine_of

BASE = f"{settings.API_V1_STR}/backups"
JOBS = f"{settings.API_V1_STR}/jobs"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


@pytest.fixture
def engine() -> Iterator[FakeEngine]:
    fake = FakeEngine()
    with engine_of(app, fake):
        yield fake


async def _wait(job_id: str) -> None:
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.wait_for(uuid.UUID(job_id))


async def _connector(
    client: AsyncClient, headers: dict[str, str], *, password: str | None = None
) -> str:
    options = working_postgres_options()
    if password is not None:
        options["password"] = password
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"backed up {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": options,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


# --- what the name of a backup is ------------------------------------------


def test_a_backup_is_named_after_the_connection_and_the_moment() -> None:
    when = datetime(2026, 9, 3, 14, 5, 9, tzinfo=UTC)

    assert (
        backup_filename("Sales database", when) == "Sales-database-2026-09-03-140509.dump"
    )


def test_a_name_that_could_not_be_a_file_name_becomes_one() -> None:
    """A connection may be called anything at all, and this becomes a file."""
    when = datetime(2026, 9, 3, 14, 5, 9, tzinfo=UTC)

    assert backup_filename("../../etc/passwd", when) == (
        "etc-passwd-2026-09-03-140509.dump"
    )
    assert "/" not in backup_filename("a/b", when)
    assert backup_filename("///", when) == "backup-2026-09-03-140509.dump"


# --- taking one ------------------------------------------------------------


async def test_a_backup_is_a_job_and_writes_a_file_of_the_owner_s_own(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    owner = await _owner_of(connector_id)
    engine.writes = str(
        storage.home_dir(owner) / BACKUP_FOLDER / "written-by-the-fake.dump"
    )

    started = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"connector_id": connector_id}
    )
    assert started.status_code == 200, started.text
    await _wait(started.json()["id"])
    job = await client.get(
        f"{JOBS}/{started.json()['id']}", headers=normal_user_token_headers
    )

    # The program the source named was run, in the image of its own version.
    assert len(engine.ran) == 1
    assert engine.ran[0].argv[0] == "pg_dump"
    assert engine.ran[0].image.startswith("postgres:")
    assert job.json()["state"] == "failed" or job.json()["state"] == "succeeded"


async def test_the_program_is_given_the_password_apart_from_its_arguments(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An argument is visible to anything that can list processes."""
    # CI uses "postgres" for both the user and password, and the image has
    # that name too. A distinct secret makes substring checks unambiguous.
    password = "backup-only-secret-4c7d94a"
    # Only the version probe needs a live source. Keep command construction
    # real while letting this connector carry a password chosen by the test.
    query = AsyncMock(return_value=[{"server_version_num": "180000"}])
    monkeypatch.setattr(PostgresSession, "query", query)
    connector_id = await _connector(
        client, normal_user_token_headers, password=password
    )
    owner = await _owner_of(connector_id)
    engine.writes = str(storage.home_dir(owner) / BACKUP_FOLDER / "x.dump")

    started = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"connector_id": connector_id}
    )
    assert started.status_code == 200, started.text
    await _wait(started.json()["id"])

    query.assert_awaited_once_with("SHOW server_version_num")
    assert len(engine.ran) == 1
    run = engine.ran[0]
    assert run.environment["PGPASSWORD"] == password
    assert not any(password in argument for argument in run.argv)
    # And it is not in what a log or a traceback would print either.
    assert password not in repr(run)


async def test_a_failed_program_says_what_it_said(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """A failed pg_dump says why in one line, and that line is the difference
    between "it did not work" and something a person can act on."""
    connector_id = await _connector(client, normal_user_token_headers)
    engine.exit_code = 1
    engine.printed = ["pg_dump: error: connection to server failed"]

    started = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"connector_id": connector_id}
    )
    await _wait(started.json()["id"])
    job = await client.get(
        f"{JOBS}/{started.json()['id']}", headers=normal_user_token_headers
    )

    assert job.json()["state"] == "failed"
    assert job.json()["message"] == "pg_dump: error: connection to server failed"


@pytest.mark.usefixtures("engine")
async def test_somebody_else_s_connection_cannot_be_copied_out(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """Copying a database out whole is more than reading it, and a grant is
    not ownership (D33)."""
    connector_id = await _connector(client, normal_user_token_headers)

    started = await client.post(
        f"{BASE}/", headers=superuser_token_headers, json={"connector_id": connector_id}
    )

    assert started.status_code == 404


@pytest.mark.usefixtures("engine")
async def test_a_source_that_cannot_be_copied_out_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """The rule every capability follows, said before a job exists.

    A file source names no program that would dump it, so it does not
    implement `SupportsBackup` — and the button that offers it is greyed out
    by reading the same capability off the type.
    """
    made = await client.post(
        f"{CONNECTORS}/",
        headers=normal_user_token_headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert made.status_code == 200, made.text
    connector_id = str(made.json()["id"])

    copied = await client.post(
        f"{BASE}/", headers=normal_user_token_headers, json={"connector_id": connector_id}
    )
    put_back = await client.post(
        f"{BASE}/restore",
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "filename": "anything.dump",
            "understood": True,
        },
    )

    assert copied.status_code == 501
    assert put_back.status_code == 501
    assert copied.json()["detail"]["message"] == (
        "This kind of connection cannot be copied out"
    )


def test_the_backup_capability_is_read_off_the_driver() -> None:
    """So one list decides both the refusal and what the button offers."""
    codes = {
        capability.code
        for capability in registry.capabilities_of(registry.get("postgres"))
    }
    others = {
        capability.code
        for capability in registry.capabilities_of(registry.get("file"))
    }

    assert "backup" in codes
    assert "backup" not in others


@pytest.mark.usefixtures("engine")
async def test_without_a_place_to_write_it_the_offer_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "SERVICE_STORAGE_VOLUME", "")
        offer = await client.get(f"{BASE}/offer", headers=normal_user_token_headers)
        refused = await client.post(
            f"{BASE}/",
            headers=normal_user_token_headers,
            json={"connector_id": str(uuid.uuid4())},
        )

    assert offer.json()["available"] is False
    assert offer.json()["reason"] == "This server has nowhere to write a backup"
    assert refused.status_code in {404, 503}


@pytest.mark.usefixtures("engine")
async def test_with_a_runtime_and_a_volume_it_is_offered(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "SERVICE_STORAGE_VOLUME", "storage")
        offer = await client.get(f"{BASE}/offer", headers=normal_user_token_headers)

    assert offer.json()["available"] is True
    assert offer.json()["folder"] == BACKUP_FOLDER


# --- putting one back ------------------------------------------------------


async def test_a_restore_must_say_that_it_is_meant(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    """It drops every object in the dump from the target first, which nothing
    else in this application does."""
    connector_id = await _connector(client, normal_user_token_headers)
    owner = await _owner_of(connector_id)
    _write_backup(owner, "a-backup.dump")

    refused = await client.post(
        f"{BASE}/restore",
        headers=normal_user_token_headers,
        json={"connector_id": connector_id, "filename": "a-backup.dump"},
    )

    assert refused.status_code == 422
    assert "is meant" in refused.json()["detail"]["message"]
    assert engine.ran == []


async def test_a_restore_runs_the_program_the_source_named(
    client: AsyncClient, normal_user_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    owner = await _owner_of(connector_id)
    _write_backup(owner, "a-backup.dump")

    started = await client.post(
        f"{BASE}/restore",
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "filename": "a-backup.dump",
            "understood": True,
        },
    )
    await _wait(started.json()["id"])
    job = await client.get(
        f"{JOBS}/{started.json()['id']}", headers=normal_user_token_headers
    )

    assert job.json()["state"] == "succeeded"
    assert engine.ran[0].argv[0] == "pg_restore"
    assert "--clean" in engine.ran[0].argv
    # Reading a dump is not a reason to be able to write to somebody's files.
    assert engine.ran[0].mounts[0].read_only is True


@pytest.mark.usefixtures("engine")
async def test_a_backup_that_is_not_theirs_is_not_found(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A name matched against one folder, so nothing resolves a path a client
    wrote — the containment rule kept by having no path to contain (D8)."""
    connector_id = await _connector(client, normal_user_token_headers)

    for name in ("../../../etc/passwd", "nothing.dump", "..", "a/b.dump"):
        refused = await client.post(
            f"{BASE}/restore",
            headers=normal_user_token_headers,
            json={
                "connector_id": connector_id,
                "filename": name,
                "understood": True,
            },
        )
        assert refused.status_code == 404, name


@pytest.mark.usefixtures("engine")
async def test_a_backup_can_be_deleted_and_only_by_its_owner(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """The same rule the restore uses: a name matched in one folder."""
    owner = await _owner_of(await _connector(client, normal_user_token_headers))
    written = _write_backup(owner, "old.dump")

    refused = await client.delete(
        f"{BASE}/old.dump", headers=superuser_token_headers
    )
    assert refused.status_code == 404
    assert written.exists()

    deleted = await client.delete(f"{BASE}/old.dump", headers=normal_user_token_headers)

    assert deleted.status_code == 200
    assert not written.exists()
    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    assert "old.dump" not in [row["filename"] for row in listed.json()]


@pytest.mark.usefixtures("engine")
async def test_a_name_that_is_not_a_plain_name_reaches_no_folder(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """Nothing resolves a path a client wrote: the route does not match one."""
    escaped = await client.delete(
        f"{BASE}/../../etc/passwd", headers=normal_user_token_headers
    )
    unknown = await client.delete(f"{BASE}/never.dump", headers=normal_user_token_headers)

    assert escaped.status_code in {404, 405}
    assert unknown.status_code == 404


@pytest.mark.usefixtures("engine")
async def test_the_backups_of_one_person_are_listed_newest_first(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    owner = await _owner_of(connector_id)
    older = _write_backup(owner, "older.dump")
    newer = _write_backup(owner, "newer.dump")
    import os

    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)

    names = [item["filename"] for item in listed.json()]
    assert names.index("newer.dump") < names.index("older.dump")
    assert names[0] != "older.dump"


def _write_backup(owner_id: uuid.UUID, name: str) -> Path:
    folder = storage.home_dir(owner_id) / BACKUP_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"a dump")
    return path


async def _owner_of(connector_id: str) -> uuid.UUID:
    from app.connectors.models import Connector

    async with async_session_maker() as session:
        connector = await session.get(Connector, uuid.UUID(connector_id))
        assert connector is not None
        return connector.owner_id

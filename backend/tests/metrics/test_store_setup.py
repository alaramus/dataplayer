"""Starting the metrics store as a service, with a runtime a test holds (D126)."""

import uuid
from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import AsyncClient
from sqlmodel import col, delete, select

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud as job_crud
from app.jobs.runner import JobRunner
from app.main import app
from app.metrics import crud
from app.metrics.models import MetricsStoreSetting
from app.services import crud as service_crud
from app.services.models import ManagedService
from tests.utils.service_engine import FakeEngine, engine_of, forget_services

BASE = f"{settings.API_V1_STR}/metrics"
SERVICES = f"{settings.API_V1_STR}/services"


@pytest.fixture(autouse=True)
async def clean() -> AsyncGenerator[None]:
    await _forget()
    yield
    await _forget()


async def _forget() -> None:
    async with async_session_maker() as session:
        await session.exec(delete(MetricsStoreSetting))
        await session.commit()
    await forget_services()


@pytest.fixture
def engine() -> Iterator[FakeEngine]:
    fake = FakeEngine()
    with engine_of(app, fake):
        yield fake


async def _wait(job_id: str) -> None:
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.wait_for(uuid.UUID(job_id))


async def _store_services() -> list[ManagedService]:
    async with async_session_maker() as session:
        statement = select(ManagedService).where(
            col(ManagedService.purpose) == "metrics_store"
        )
        return list((await session.exec(statement)).all())


async def test_starting_the_store_saves_it_as_a_setting_and_not_as_a_connection(
    client: AsyncClient, superuser_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    started = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)

    assert started.status_code == 200, started.text
    assert started.json()["state"] == "starting"
    job = started.json()["job"]
    assert job["kind"] == "metrics.store.create"
    await _wait(job["id"])

    assert engine.pulled == ["timescale/timescaledb:2.30.0-pg18"]
    (service,) = await _store_services()
    assert service.state == "running"
    assert service.connector_id is None
    # Reached by name on the network, published nowhere.
    assert not service.publish
    async with async_session_maker() as session:
        setting = await crud.store_setting(session)
        assert setting is not None
        assert setting.service_id == service.id
        assert setting.config["host"] == service.container_name
        assert "password" not in setting.config
        # Not a person's service: in nobody's list, against nobody's ceiling.
        assert await service_crud.count_for_owner(session, service.owner_id) == 0
    listed = await client.get(f"{SERVICES}/", headers=superuser_token_headers)
    assert all(item["id"] != str(service.id) for item in listed.json())
    one = await client.get(f"{SERVICES}/{service.id}", headers=superuser_token_headers)
    assert one.status_code == 404


async def test_a_started_store_is_set_up_once(
    client: AsyncClient, superuser_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    started = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)
    await _wait(started.json()["job"]["id"])

    again = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)

    assert again.status_code == 409
    assert len(engine.pulled) == 1


async def test_asking_twice_while_it_starts_starts_one(
    client: AsyncClient, superuser_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    engine.hold_on = "pull"
    first = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)
    await engine.holding.wait()

    second = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)

    assert second.status_code == 200
    assert second.json()["state"] == "starting"
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    assert len(await _store_services()) == 1
    runner = app.state.job_runner
    assert isinstance(runner, JobRunner)
    await runner.cancel(uuid.UUID(first.json()["job"]["id"]))


async def test_a_failed_start_says_why_and_starting_again_reuses_the_service(
    client: AsyncClient, superuser_token_headers: dict[str, str], engine: FakeEngine
) -> None:
    engine.refuse_on = "pull"
    started = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)
    await _wait(started.json()["job"]["id"])

    failed = await client.get(f"{BASE}/store", headers=superuser_token_headers)
    assert failed.json()["state"] == "failed"
    assert failed.json()["message"]

    engine.refuse_on = None
    retried = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)
    await _wait(retried.json()["job"]["id"])

    (service,) = await _store_services()
    assert service.state == "running"


async def test_without_a_runtime_nothing_is_started(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    with engine_of(app, FakeEngine(available=False)):
        response = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)

    assert response.status_code == 503
    assert await _store_services() == []


async def test_removing_a_started_store_removes_its_service_and_its_data(
    client: AsyncClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    engine: FakeEngine,
) -> None:
    started = await client.post(f"{BASE}/store/start", headers=superuser_token_headers)
    await _wait(started.json()["job"]["id"])
    (service,) = await _store_services()

    refused = await client.delete(f"{BASE}/store", headers=normal_user_token_headers)
    removed = await client.delete(f"{BASE}/store", headers=superuser_token_headers)

    assert refused.status_code == 403
    assert removed.status_code == 200, removed.text
    status = await client.get(f"{BASE}/store", headers=superuser_token_headers)
    assert status.json()["state"] == "not_configured"
    async with async_session_maker() as session:
        assert await crud.store_setting(session) is None
        jobs = await job_crud.for_subject(session, service.id, limit=5)
    (job,) = [one for one in jobs if one.kind == "service.delete"]
    await _wait(str(job.id))
    assert engine.removed == [(service.container_name, service.volume_name)]
    assert await _store_services() == []

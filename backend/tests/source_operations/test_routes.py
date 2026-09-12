"""Turning a reviewed action into an owned job (D123)."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.actions import ActionRefused
from app.adapters.operations import OperationPlan, OperationTarget
from app.adapters.postgres.actions import CreateSchema
from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job
from app.main import app
from app.users import crud as user_crud
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"
PLAN = OperationPlan(
    summary="Convert 2 things", unit_fingerprint="b" * 64,
    targets=(OperationTarget(schema_name="lab", name="one"), OperationTarget(schema_name="lab", name="two")),
)
REQUEST = {"node_id": None, "params": {"name": "lab"}, "reviewed_fingerprint": "a" * 64}


@pytest.fixture
def as_job(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """CreateSchema, offered at the root of every connection, made a job-producing action."""
    plan = AsyncMock(return_value=PLAN)
    monkeypatch.setattr(CreateSchema, "plan_job", plan, raising=False)
    monkeypatch.setattr(CreateSchema, "run_unit", AsyncMock(return_value="completed"), raising=False)
    monkeypatch.setattr(
        CreateSchema, "observe", AsyncMock(return_value=["as_requested", "as_requested"]), raising=False,
    )
    return plan


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    options = working_postgres_options()
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={"name": f"pg {uuid.uuid4()}", "adapter_type": "postgres", "options": options},
    )
    assert response.status_code == 200
    return str(response.json()["id"])


def _jobs(connector_id: str) -> str:
    return f"{BASE}/{connector_id}/actions/create_schema/jobs"


async def test_an_action_that_is_not_a_job_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str],
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.post(_jobs(connector_id), headers=normal_user_token_headers, json=REQUEST)
    assert response.status_code == 415


@pytest.mark.usefixtures("as_job")
async def test_a_job_needs_a_reviewed_fingerprint(
    client: AsyncClient, normal_user_token_headers: dict[str, str],
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.post(
        _jobs(connector_id), headers=normal_user_token_headers,
        json={**REQUEST, "reviewed_fingerprint": None},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "Review the operation plan before running it"


async def test_a_reviewed_job_is_admitted_then_carried_out_by_the_server(
    client: AsyncClient, normal_user_token_headers: dict[str, str], as_job: AsyncMock,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.post(_jobs(connector_id), headers=normal_user_token_headers, json=REQUEST)
    assert response.status_code == 202
    job = response.json()
    assert (job["kind"], job["subject_id"], job["state"]) == ("source.operation", connector_id, "queued")
    parameters = job["parameters"]
    assert [item["target"]["name"] for item in parameters["targets"]] == ["one", "two"]
    assert {item["outcome"] for item in parameters["targets"]} == {"pending"}
    assert (parameters["action"], parameters["requires"], parameters["unit_fingerprint"]) == (
        "create_schema", "structure", "b" * 64,
    )
    as_job.assert_awaited_once_with(None, {"name": "lab"}, "a" * 64)

    await app.state.job_runner.wait_for(uuid.UUID(job["id"]))
    done = await client.get(f"{settings.API_V1_STR}/jobs/{job['id']}", headers=normal_user_token_headers)
    assert (done.json()["state"], done.json()["message"]) == ("succeeded", "Convert 2 things: 2 done")


@pytest.mark.usefixtures("as_job")
async def test_a_second_operation_on_the_connection_is_refused_with_the_running_one(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession,
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    user = await user_crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    async with async_session_maker() as session:
        running = await crud.create(
            session, owner_id=user.id, kind="source.operation",
            subject_id=uuid.UUID(connector_id), step_count=3,
        )
    response = await client.post(_jobs(connector_id), headers=normal_user_token_headers, json=REQUEST)
    assert response.status_code == 409
    assert response.json()["detail"]["job_id"] == str(running.id)


async def test_a_stale_review_is_refused_before_anything_is_recorded(
    client: AsyncClient, normal_user_token_headers: dict[str, str], as_job: AsyncMock,
) -> None:
    as_job.side_effect = ActionRefused("conflict", "The operation plan changed; review it again")
    connector_id = await _postgres_connector(client, normal_user_token_headers)
    response = await client.post(_jobs(connector_id), headers=normal_user_token_headers, json=REQUEST)
    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "The operation plan changed; review it again"
    async with async_session_maker() as session:
        recorded = (await session.exec(select(Job).where(Job.subject_id == uuid.UUID(connector_id)))).all()
    assert recorded == []


async def _create_schema_info(client: AsyncClient, headers: dict[str, str]) -> dict[str, object]:
    connector_id = await _postgres_connector(client, headers)
    response = await client.post(f"{BASE}/{connector_id}/actions", headers=headers, json={"node_ids": None})
    assert response.status_code == 200
    return dict(next(item for item in response.json() if item["name"] == "create_schema"))


@pytest.mark.usefixtures("as_job")
async def test_the_menu_says_an_action_is_a_reviewed_job(
    client: AsyncClient, normal_user_token_headers: dict[str, str],
) -> None:
    info = await _create_schema_info(client, normal_user_token_headers)
    assert (info["produces_job"], info["requires_plan_review"]) == (True, True)


async def test_an_ordinary_action_is_neither_reviewed_nor_a_job(
    client: AsyncClient, normal_user_token_headers: dict[str, str],
) -> None:
    info = await _create_schema_info(client, normal_user_token_headers)
    assert (info["produces_job"], info["requires_plan_review"]) == (False, False)

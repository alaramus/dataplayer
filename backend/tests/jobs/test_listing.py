"""The process window reads bounded, owned history with active work first."""

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlmodel import delete

from app.core.config import settings
from app.core.db import async_session_maker
from app.jobs import crud
from app.jobs.models import Job
from app.users import crud as user_crud
from app.users.models import UserCreate
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/jobs/"


@pytest.fixture(autouse=True)
async def without_jobs() -> AsyncGenerator[None]:
    async with async_session_maker() as session:
        await session.exec(delete(Job))
        await session.commit()
    yield


async def test_listing_is_owned_active_first_and_counts_beyond_the_page(
    client: AsyncClient, superuser_token_headers: dict[str, str]
) -> None:
    async with async_session_maker() as session:
        owner = await user_crud.get_user_by_email(
            session=session, email=settings.FIRST_SUPERUSER
        )
        assert owner is not None
        other = await user_crud.create_user(
            session=session,
            user_create=UserCreate(email=random_email(), password="a-test-password-123"),
        )
        active = await crud.create(
            session, owner_id=owner.id, kind="service.start", subject_id=None, step_count=1
        )
        finished = await crud.create(
            session, owner_id=owner.id, kind="backup.create", subject_id=None, step_count=2
        )
        finished.state = "cancelled"
        session.add(finished)
        await session.commit()
        foreign = await crud.create(
            session, owner_id=other.id, kind="service.start", subject_id=None, step_count=1
        )

    first = await client.get(BASE, headers=superuser_token_headers, params={"limit": 1})
    assert first.status_code == 200, first.text
    assert first.json()["count"] == 2
    assert first.json()["active_count"] == 1
    assert [job["id"] for job in first.json()["data"]] == [str(active.id)]
    second = await client.get(
        BASE, headers=superuser_token_headers, params={"skip": 1, "limit": 1}
    )
    assert [job["id"] for job in second.json()["data"]] == [str(finished.id)]
    assert str(foreign.id) not in first.text + second.text
    assert (await client.get(BASE)).status_code == 401


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"skip": -1}])
async def test_listing_has_a_hard_page_ceiling(
    client: AsyncClient, superuser_token_headers: dict[str, str], params: dict[str, int]
) -> None:
    response = await client.get(BASE, headers=superuser_token_headers, params=params)
    assert response.status_code == 422

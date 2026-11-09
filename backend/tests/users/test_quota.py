"""The limit on a person's directory: the server's figure, one set for a person, and the usage it is held against (D324)."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud, quota, storage
from tests.utils.user import create_random_user
from tests.utils.utils import random_email, random_lower_string

MB = 1024 * 1024


def test_the_server_figure_applies_until_one_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    person = uuid.uuid4()
    monkeypatch.setattr(settings, "USER_STORAGE_QUOTA_MB", 100)

    assert quota.limit_bytes(person) == 100 * MB
    quota.remember(person, 5)
    assert quota.limit_bytes(person) == 5 * MB
    quota.remember(person, None)
    assert quota.limit_bytes(person) == 100 * MB


def test_zero_is_no_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    person = uuid.uuid4()
    monkeypatch.setattr(settings, "USER_STORAGE_QUOTA_MB", 0)
    assert quota.limit_bytes(person) is None

    monkeypatch.setattr(settings, "USER_STORAGE_QUOTA_MB", 100)
    quota.remember(person, 0)
    assert quota.limit_bytes(person) is None
    quota.remember(person, None)


def test_usage_counts_every_file_below_the_directory(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.bin").write_bytes(b"x" * 3)
    (tmp_path / "two.bin").write_bytes(b"x" * 4)

    assert storage.used_bytes(tmp_path) == 7
    assert storage.used_bytes(tmp_path / "missing") == 0


async def test_the_limits_set_for_people_are_read_back_at_start(db: AsyncSession) -> None:
    user = await create_random_user(db)
    user.storage_quota_mb = 11
    db.add(user)
    await db.commit()
    quota.remember(user.id, None)

    await quota.load(db)

    assert quota.limit_bytes(user.id) == 11 * MB
    quota.remember(user.id, None)


async def test_a_superuser_sets_and_clears_a_persons_limit(
    client: AsyncClient, superuser_token_headers: dict[str, str], db: AsyncSession
) -> None:
    user = await create_random_user(db)
    url = f"{settings.API_V1_STR}/users/{user.id}"

    set_ = await client.patch(url, headers=superuser_token_headers, json={"storage_quota_mb": 7})
    assert set_.status_code == 200, set_.text
    assert set_.json()["storage_quota_mb"] == 7
    assert quota.limit_bytes(user.id) == 7 * MB

    cleared = await client.patch(
        url, headers=superuser_token_headers, json={"storage_quota_mb": None}
    )
    assert cleared.json()["storage_quota_mb"] is None
    assert quota.limit_bytes(user.id) == quota.limit_bytes(uuid.uuid4())


async def test_a_negative_limit_is_refused(
    client: AsyncClient, superuser_token_headers: dict[str, str], db: AsyncSession
) -> None:
    user = await create_random_user(db)

    response = await client.patch(
        f"{settings.API_V1_STR}/users/{user.id}",
        headers=superuser_token_headers,
        json={"storage_quota_mb": -1},
    )

    assert response.status_code == 422


async def test_a_person_cannot_set_their_own_limit(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    me = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert me is not None
    before = quota.limit_bytes(me.id)

    response = await client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=normal_user_token_headers,
        json={"storage_quota_mb": 100000},
    )

    assert response.status_code == 200
    assert response.json()["storage_quota_mb"] is None
    assert quota.limit_bytes(me.id) == before


async def test_signing_up_cannot_name_a_limit(client: AsyncClient) -> None:
    response = await client.post(
        f"{settings.API_V1_STR}/users/signup",
        json={
            "email": random_email(),
            "password": random_lower_string(),
            "storage_quota_mb": 1,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["storage_quota_mb"] is None


async def test_deleting_a_person_forgets_their_limit(
    client: AsyncClient, superuser_token_headers: dict[str, str], db: AsyncSession
) -> None:
    user = await create_random_user(db)
    quota.remember(user.id, 3)

    response = await client.delete(
        f"{settings.API_V1_STR}/users/{user.id}", headers=superuser_token_headers
    )

    assert response.status_code == 200
    assert quota.limit_bytes(user.id) == quota.limit_bytes(uuid.uuid4())


async def test_a_person_reads_how_full_their_storage_is(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    me = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert me is not None
    home = storage.create_home(me.id)
    (home / "quota-probe.bin").write_bytes(b"x" * 5)
    quota.remember(me.id, 9)
    try:
        response = await client.get(
            f"{settings.API_V1_STR}/users/me/storage", headers=normal_user_token_headers
        )
    finally:
        quota.remember(me.id, None)
        (home / "quota-probe.bin").unlink()

    assert response.status_code == 200
    body = response.json()
    assert body["limit_bytes"] == 9 * MB
    assert body["used_bytes"] >= 5

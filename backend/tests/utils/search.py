"""Asking the search as a person does, and reading its lines (D201)."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud as user_crud
from tests.utils.database import working_postgres_options
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

SEARCH = f"{settings.API_V1_STR}/search"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@dataclass(frozen=True)
class Person:
    id: uuid.UUID
    email: str
    headers: dict[str, str]


async def person(client: AsyncClient, db: AsyncSession, full_name: str | None = None) -> Person:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await user_crud.get_user_by_email(session=db, email=email)
    assert user is not None
    if full_name is not None:
        user.full_name = full_name
        db.add(user)
        await db.commit()
    return Person(id=user.id, email=email, headers=headers)


async def connection(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    """A PostgreSQL connection of the person's own, to the development database."""
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={"name": name, "adapter_type": "postgres", "options": working_postgres_options()},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def grant(
    client: AsyncClient, owner: dict[str, str], connector_id: str, to: Person
) -> None:
    response = await client.put(
        f"{CONNECTORS}/{connector_id}/grants",
        headers=owner,
        json={"user_id": str(to.id), "access": "read"},
    )
    assert response.status_code == 200, response.text


async def search(
    client: AsyncClient,
    headers: dict[str, str],
    words: str,
    mode: str = "search",
    **extra: Any,
) -> list[dict[str, Any]]:
    response = await client.post(
        SEARCH, headers=headers, json={"words": words, "mode": mode, **extra}
    )
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines() if line]


def hits(lines: list[dict[str, Any]], group: str | None = None) -> list[dict[str, Any]]:
    """The hits of every cell of a group, or of every cell, in the order sent."""
    keys = {
        cell["key"]
        for line in lines
        if line["type"] == "plan"
        for cell in line["cells"]
        if group is None or cell["group"]["key"] == group
    }
    return [
        hit
        for line in lines
        if line["type"] == "cell" and line["key"] in keys
        for hit in line["hits"]
    ]


def object_ids(lines: list[dict[str, Any]], object_type: str) -> list[str]:
    return [
        hit["target"]["object_id"]
        for hit in hits(lines)
        if hit["target"]["kind"] == "object" and hit["target"]["object_type"] == object_type
    ]


def outcome(lines: list[dict[str, Any]], key: str) -> dict[str, Any]:
    [line] = [line for line in lines if line["type"] == "cell" and line["key"] == key]
    found: dict[str, Any] = line["outcome"]
    return found

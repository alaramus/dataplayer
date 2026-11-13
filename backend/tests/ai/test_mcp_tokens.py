"""Personal access tokens for /mcp: made, listed, revoked, verified (D358)."""

import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai import mcp_tokens
from app.ai.mcp_tokens import McpToken
from app.core.config import settings
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.users import crud
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

TOKENS = f"{settings.API_V1_STR}/ai/mcp-tokens/"


async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def make(
    client: AsyncClient, headers: dict[str, str], **body: object
) -> dict[str, object]:
    response = await client.post(
        TOKENS, headers=headers, json={"name": "agent", "policy": "read_only", **body}
    )
    assert response.status_code == 200, response.text
    made: dict[str, object] = response.json()
    return made


async def test_a_token_is_shown_once_and_kept_only_as_a_hash(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    made = await make(client, headers, policy="full", expires_in_days=30)
    token = str(made["token"])

    assert token.startswith(mcp_tokens.PREFIX)
    assert made["policy"] == "full"
    assert made["expires_at"] is not None
    assert token.startswith(str(made["shown"]))

    listed = (await client.get(TOKENS, headers=headers)).json()
    assert [one["id"] for one in listed] == [made["id"]]
    assert "token" not in listed[0]
    assert token not in str(listed)

    async with async_session_maker() as session:
        row = (await session.exec(select(McpToken).where(McpToken.name == "agent"))).first()
        rows = (await session.exec(select(McpToken))).all()
    assert row is not None
    assert all(token not in (one.digest, one.shown) for one in rows)


async def test_an_expiry_outside_the_offered_spans_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    response = await client.post(
        TOKENS,
        headers=headers,
        json={"name": "agent", "policy": "full", "expires_in_days": 3650},
    )
    assert response.status_code == 422
    response = await client.post(
        TOKENS, headers=headers, json={"name": "agent", "policy": "admin"}
    )
    assert response.status_code == 422


async def test_a_revoked_token_opens_nothing_and_only_its_owner_revokes_it(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    made = await make(client, owner)
    token = str(made["token"])

    foreign = await client.delete(f"{TOKENS}{made['id']}", headers=stranger)
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "ai.mcp_token_not_found"
    async with async_session_maker() as session:
        assert await mcp_tokens.verify(session, token) is not None

    revoked = await client.delete(f"{TOKENS}{made['id']}", headers=owner)
    assert revoked.status_code == 200, revoked.text
    async with async_session_maker() as session:
        assert await mcp_tokens.verify(session, token) is None
    assert (await client.get(TOKENS, headers=owner)).json() == []


async def test_verification_names_the_owner_and_the_policy_and_records_a_use(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    made = await make(client, headers, policy="full")
    async with async_session_maker() as session:
        caller = await mcp_tokens.verify(session, str(made["token"]))
    assert caller is not None
    assert caller.policy == "full"
    assert str(caller.token_id) == made["id"]
    listed = (await client.get(TOKENS, headers=headers)).json()
    assert listed[0]["last_used_at"] is not None


async def test_an_expired_token_an_unknown_one_and_an_inactive_owner_open_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    made = await make(client, headers)
    token = str(made["token"])

    async with async_session_maker() as session:
        assert await mcp_tokens.verify(session, mcp_tokens.PREFIX + "nothing") is None
        assert await mcp_tokens.verify(session, "not even ours") is None

        row = await session.get(McpToken, uuid.UUID(str(made["id"])))
        assert row is not None
        row.expires_at = get_datetime_utc() - timedelta(minutes=1)
        session.add(row)
        await session.commit()
        assert await mcp_tokens.verify(session, token) is None

        row.expires_at = None
        session.add(row)
        await session.commit()
        assert await mcp_tokens.verify(session, token) is not None

        user = await crud.get_user_by_email(session=session, email=email)
        assert user is not None
        user.is_active = False
        session.add(user)
        await session.commit()
        assert await mcp_tokens.verify(session, token) is None

"""Keys and choices: set, never shown, checked with a call (D140)."""

import uuid

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ai.models import AgentPreferences, ProviderKey
from tests.ai.conftest import (
    AI,
    KEY,
    MODEL_KEY,
    ProviderRefusedKey,
    Script,
    Turn,
    user_id_of,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email


async def test_a_key_is_said_to_be_set_and_never_sent_back(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    headers = normal_user_token_headers

    written = await client.put(f"{AI}/keys/gemini", headers=headers, json={"key": KEY})

    assert written.status_code == 200
    assert {"provider": "gemini", "set": True} in written.json()["keys"]
    read = await client.get(f"{AI}/settings", headers=headers)
    assert KEY not in written.text
    assert KEY not in read.text
    stored = await db.get(ProviderKey, (await user_id_of(client, headers), "gemini"))
    assert stored is not None
    assert KEY.encode() not in stored.secret

    removed = await client.delete(f"{AI}/keys/gemini", headers=headers)
    assert {"provider": "gemini", "set": False} in removed.json()["keys"]


async def test_a_provider_outside_the_four_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.put(
        f"{AI}/keys/mistral", headers=normal_user_token_headers, json={"key": KEY}
    )

    assert response.status_code == 422


async def test_keys_are_one_persons_own(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    await client.put(
        f"{AI}/keys/deepseek", headers=normal_user_token_headers, json={"key": KEY}
    )
    other = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )

    settings = (await client.get(f"{AI}/settings", headers=other)).json()

    assert {"provider": "deepseek", "set": False} in settings["keys"]


async def test_models_are_offered_by_whether_their_provider_has_a_key(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    before = (await client.get(f"{AI}/models", headers=headers)).json()
    await client.put(f"{AI}/keys/openai", headers=headers, json={"key": KEY})
    after = (await client.get(f"{AI}/models", headers=headers)).json()

    assert not any(model["available"] for model in before)
    assert {model["provider"] for model in after if model["available"]} == {"openai"}


async def test_a_model_is_chosen_only_from_the_list(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers

    refused = await client.patch(
        f"{AI}/settings", headers=headers, json={"model_key": "openai:gpt-invented"}
    )
    chosen = await client.patch(
        f"{AI}/settings", headers=headers, json={"model_key": MODEL_KEY}
    )

    assert refused.status_code == 422
    assert chosen.status_code == 200
    assert chosen.json()["model_key"] == MODEL_KEY
    assert chosen.json()["model_missing"] is False


async def test_a_stored_model_the_list_dropped_asks_for_another(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )
    db.add(
        AgentPreferences(
            user_id=await user_id_of(client, headers), model_key="openai:gpt-retired"
        )
    )
    await db.commit()

    settings = (await client.get(f"{AI}/settings", headers=headers)).json()

    assert settings["model_key"] is None
    assert settings["model_missing"] is True


async def test_allowing_every_change_is_a_setting_that_can_be_taken_back(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    headers = normal_user_token_headers

    allowed = await client.patch(
        f"{AI}/settings", headers=headers, json={"allow_all_changes": True}
    )
    withdrawn = await client.patch(
        f"{AI}/settings", headers=headers, json={"allow_all_changes": False}
    )

    assert allowed.json()["allow_all_changes"] is True
    assert withdrawn.json()["allow_all_changes"] is False


async def test_checking_a_key_calls_the_model_with_a_tool(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await client.put(f"{AI}/keys/anthropic", headers=headers, json={"key": KEY})
    await client.patch(f"{AI}/settings", headers=headers, json={"model_key": MODEL_KEY})
    script.turns.append(
        Turn(tool_calls=[{"name": "ping", "args": {}, "id": str(uuid.uuid4())}])
    )

    response = await client.post(f"{AI}/keys/anthropic/check", headers=headers)

    assert response.json() == {"ok": True, "message": "The key works with Claude Sonnet 5"}
    assert script.built[-1][:2] == (MODEL_KEY, KEY)


async def test_a_refused_key_is_said_in_the_applications_words(
    client: AsyncClient, normal_user_token_headers: dict[str, str], script: Script
) -> None:
    headers = normal_user_token_headers
    await client.put(f"{AI}/keys/anthropic", headers=headers, json={"key": KEY})
    script.turns.append(Turn(error=ProviderRefusedKey(f"invalid x-api-key {KEY}")))

    response = await client.post(f"{AI}/keys/anthropic/check", headers=headers)

    assert response.json() == {"ok": False, "message": "The provider refused the key"}
    assert KEY not in response.text


async def test_checking_without_a_key_calls_nobody(
    client: AsyncClient, db: AsyncSession, script: Script
) -> None:
    headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )

    response = await client.post(f"{AI}/keys/openai/check", headers=headers)

    assert response.json()["ok"] is False
    assert script.built == []

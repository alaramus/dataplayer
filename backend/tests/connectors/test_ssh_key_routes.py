"""A person's SSH keys through the API: write-only, owned, and asked for (D146, D147)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.protocol import AdapterError
from app.adapters.ssh import keys
from app.connectors.ssh_keys import OwnerKeys, SshKey
from app.core.config import settings
from app.users import crud
from tests.utils.user import create_random_user

BASE = f"{settings.API_V1_STR}/ssh-keys"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


async def _owner_id(db: AsyncSession) -> uuid.UUID:
    user = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert user is not None
    return user.id


async def _generate(
    client: AsyncClient, headers: dict[str, str], **body: object
) -> dict[str, object]:
    response = await client.post(
        f"{BASE}/generate", headers=headers, json={"name": "deploy"} | body
    )
    assert response.status_code == 200, response.text
    made: dict[str, object] = response.json()
    return made


async def test_a_key_made_here_shows_its_public_half_and_nothing_else(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/generate", headers=normal_user_token_headers, json={"name": "deploy"}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["algorithm"] == "ssh-ed25519"
    assert str(body["public_key"]).startswith("ssh-ed25519 ")
    assert body["passphrase_mode"] == "none"
    assert "PRIVATE KEY" not in response.text
    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    assert body["id"] in [key["id"] for key in listed.json()]
    assert "PRIVATE KEY" not in listed.text


async def test_the_private_half_is_kept_encrypted(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    made = await _generate(client, normal_user_token_headers)

    row = await db.get(SshKey, uuid.UUID(str(made["id"])))

    assert row is not None
    assert b"OPENSSH PRIVATE KEY" not in row.private_key


async def test_an_encrypted_key_is_imported_only_with_what_opens_it(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    made = keys.generate("ed25519", "opens it")
    body = {"name": "laptop", "private_key": made.private_key}

    without = await client.post(f"{BASE}/import", headers=normal_user_token_headers, json=body)
    wrong = await client.post(
        f"{BASE}/import",
        headers=normal_user_token_headers,
        json=body | {"passphrase": "does not"},
    )
    right = await client.post(
        f"{BASE}/import",
        headers=normal_user_token_headers,
        json=body | {"passphrase": "opens it", "passphrase_mode": "stored"},
    )

    assert without.status_code == 422
    assert "passphrase" in without.text
    assert wrong.status_code == 422
    assert made.private_key not in wrong.text
    assert right.status_code == 200
    assert right.json()["fingerprint"] == made.facts.fingerprint
    assert right.json()["passphrase_mode"] == "stored"


async def test_a_key_that_asks_opens_only_while_its_passphrase_is_held(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    made = await _generate(
        client, normal_user_token_headers, passphrase="held a while", passphrase_mode="ask"
    )
    key_id = uuid.UUID(str(made["id"]))
    owner = OwnerKeys(await _owner_id(db))

    assert made["unlocked_until"] is None
    with pytest.raises(AdapterError) as locked:
        await owner.signing_key(key_id)
    assert locked.value.error_kind == "locked"

    wrong = await client.post(
        f"{BASE}/{key_id}/unlock",
        headers=normal_user_token_headers,
        json={"passphrase": "not it", "minutes": 15},
    )
    opened = await client.post(
        f"{BASE}/{key_id}/unlock",
        headers=normal_user_token_headers,
        json={"passphrase": "held a while", "minutes": 60},
    )
    assert wrong.status_code == 422
    assert opened.status_code == 200
    assert opened.json()["unlocked_until"] is not None
    assert (await owner.signing_key(key_id)).passphrase == "held a while"

    closed = await client.post(f"{BASE}/{key_id}/lock", headers=normal_user_token_headers)
    assert closed.json()["unlocked_until"] is None
    with pytest.raises(AdapterError):
        await owner.signing_key(key_id)


async def test_the_passphrase_of_a_key_that_asks_is_never_written_down(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    made = await _generate(
        client, normal_user_token_headers, passphrase="only in memory", passphrase_mode="ask"
    )

    row = await db.get(SshKey, uuid.UUID(str(made["id"])))

    assert row is not None
    assert row.passphrase is None


async def test_a_key_in_use_is_not_deleted_and_the_answer_says_by_what(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    made = await _generate(client, normal_user_token_headers)
    name = f"server {uuid.uuid4().hex[:8]}"
    created = await client.post(
        f"{CONNECTORS}/",
        headers=normal_user_token_headers,
        json={
            "name": name,
            "adapter_type": "ssh",
            "options": {
                "auth_method": "key",
                "host": "example.invalid",
                "username": "deploy",
                "key_id": made["id"],
            },
        },
    )
    assert created.status_code == 200, created.text

    listed = await client.get(f"{BASE}/", headers=normal_user_token_headers)
    refused = await client.delete(f"{BASE}/{made['id']}", headers=normal_user_token_headers)

    uses = next(key["used_by"] for key in listed.json() if key["id"] == made["id"])
    assert [use["name"] for use in uses] == [name]
    assert refused.status_code == 409
    assert name in refused.text

    await client.delete(f"{CONNECTORS}/{created.json()['id']}", headers=normal_user_token_headers)
    deleted = await client.delete(f"{BASE}/{made['id']}", headers=normal_user_token_headers)
    assert deleted.status_code == 200


async def test_somebody_elses_key_is_not_found_and_signs_nothing_in(
    client: AsyncClient, normal_user_token_headers: dict[str, str], db: AsyncSession
) -> None:
    made = await _generate(client, normal_user_token_headers)
    stranger = await create_random_user(db)

    with pytest.raises(AdapterError) as refused:
        await OwnerKeys(stranger.id).signing_key(uuid.UUID(str(made["id"])))

    assert refused.value.error_kind == "config"


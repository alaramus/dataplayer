"""A person's copy history: kept, moved up, cut, searched, deleted (D460)."""

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import copies
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

COPIES = f"{settings.API_V1_STR}/copies/"


async def person(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(client=client, email=random_email(), db=db)


async def keep(
    client: AsyncClient, headers: dict[str, str], text: str, **body: object
) -> dict[str, object]:
    response = await client.post(
        COPIES, headers=headers, json={"text": text, "source": "grid", **body}
    )
    assert response.status_code == 200, response.text
    kept: dict[str, object] = response.json()
    return kept


async def listed(
    client: AsyncClient, headers: dict[str, str], q: str | None = None
) -> dict[str, object]:
    response = await client.get(
        COPIES, headers=headers, params={} if q is None else {"q": q}
    )
    assert response.status_code == 200, response.text
    page: dict[str, object] = response.json()
    return page


def previews(page: dict[str, object]) -> list[str]:
    items = page["items"]
    assert isinstance(items, list)
    return [str(item["preview"]) for item in items]


async def test_copies_are_listed_newest_first_and_only_to_their_owner(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    await keep(client, owner, "first")
    second = await keep(client, owner, "second", source="agent", detail="users")

    page = await listed(client, owner)
    assert previews(page) == ["second", "first"]
    assert page["total"] == 2
    assert second["source"] == "agent"
    assert second["detail"] == "users"
    assert (await listed(client, stranger))["items"] == []

    foreign = await client.get(f"{COPIES}{second['id']}", headers=stranger)
    assert foreign.status_code == 404
    assert foreign.json()["detail"]["code"] == "copies.not_found"
    own = await client.get(f"{COPIES}{second['id']}", headers=owner)
    assert own.json()["text"] == "second"


async def test_the_same_text_copied_again_moves_up_instead_of_standing_twice(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    first = await keep(client, headers, "again")
    await keep(client, headers, "between")
    moved = await keep(client, headers, "again", source="log")

    assert moved["id"] == first["id"]
    assert moved["source"] == "log"
    assert previews(await listed(client, headers)) == ["again", "between"]


async def test_a_long_copy_is_kept_cut_and_the_list_shows_its_start(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    kept = await keep(client, headers, "x" * (copies.MAX_CHARS + 1))

    assert kept["cut"] is True
    assert kept["length"] == copies.MAX_CHARS
    assert len(str(kept["preview"])) == copies.PREVIEW_CHARS
    whole = (await client.get(f"{COPIES}{kept['id']}", headers=headers)).json()
    assert len(whole["text"]) == copies.MAX_CHARS

    too_long = await client.post(
        COPIES,
        headers=headers,
        json={"text": "x" * (copies.MAX_CHARS + 2), "source": "grid"},
    )
    assert too_long.status_code == 422


async def test_a_source_outside_the_set_and_an_empty_text_are_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    for body in ({"text": "x", "source": "password"}, {"text": "", "source": "grid"}):
        response = await client.post(COPIES, headers=headers, json=body)
        assert response.status_code == 422, body


async def test_only_the_newest_copies_are_kept(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copies, "KEEP", 3)
    headers = await person(client, db)
    for text in ("a", "b", "c", "d", "e"):
        await keep(client, headers, text)

    page = await listed(client, headers)
    assert previews(page) == ["e", "d", "c"]
    assert page["total"] == 3


async def test_search_finds_the_text_and_treats_wildcards_as_letters(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await person(client, db)
    await keep(client, headers, "SELECT * FROM Users")
    await keep(client, headers, "100% done")
    await keep(client, headers, "nothing here")

    assert previews(await listed(client, headers, "users")) == ["SELECT * FROM Users"]
    assert previews(await listed(client, headers, "%")) == ["100% done"]
    page = await listed(client, headers, "_")
    assert page["items"] == []
    assert page["total"] == 3


async def test_copies_are_deleted_one_several_or_all_and_never_anothers(
    client: AsyncClient, db: AsyncSession
) -> None:
    owner = await person(client, db)
    stranger = await person(client, db)
    one = await keep(client, owner, "one")
    two = await keep(client, owner, "two")
    three = await keep(client, owner, "three")
    await keep(client, owner, "four")
    theirs = await keep(client, stranger, "theirs")

    response = await client.post(
        f"{COPIES}delete", headers=owner, json={"ids": [one["id"], theirs["id"]]}
    )
    assert response.json() == {"deleted": 1}
    response = await client.post(
        f"{COPIES}delete", headers=owner, json={"ids": [two["id"], three["id"]]}
    )
    assert response.json() == {"deleted": 2}
    assert previews(await listed(client, owner)) == ["four"]

    assert (await client.delete(COPIES, headers=owner)).json() == {"deleted": 1}
    assert (await listed(client, owner))["items"] == []
    assert previews(await listed(client, stranger)) == ["theirs"]

    empty = await client.post(f"{COPIES}delete", headers=owner, json={"ids": []})
    assert empty.status_code == 422

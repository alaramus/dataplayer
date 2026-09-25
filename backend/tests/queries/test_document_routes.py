"""The library, one console, its revisions and permanent deletion.

A file connection stands in for a source throughout: nothing in this slice
reaches one, because there is no execution yet (D63).
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.users import crud as user_crud
from app.users.models import User
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries/documents"
CONNECTORS = f"{settings.API_V1_STR}/connectors"


@pytest.fixture
async def colleague(
    client: AsyncClient, db: AsyncSession
) -> tuple[User, dict[str, str]]:
    """Somebody other than the owner, with a token of their own."""
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    user = await user_crud.get_user_by_email(session=db, email=email)
    assert user is not None
    return user, headers


async def _connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{CONNECTORS}/",
        headers=headers,
        json={
            "name": f"files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def _document(
    client: AsyncClient,
    headers: dict[str, str],
    connector_id: str,
    *,
    body: str = "select 1",
    title: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"connector_id": connector_id, "body": body}
    if title is not None:
        payload["title"] = title
    response = await client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    created: dict[str, Any] = response.json()
    return created


async def test_a_new_console_is_an_unnamed_document_bound_to_a_connection(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    document = await _document(
        client, normal_user_token_headers, connector_id, body="select 1"
    )

    assert document["title"] is None
    assert document["connector_id"] == connector_id
    assert document["body"] == "select 1"
    assert document["revision"] == 1
    # The name of the connection travels with it, so a library can say what a
    # document is about without asking per row.
    assert document["connector_label"] is not None


async def test_naming_a_document_changes_only_its_title(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """D63: one object in two stages, not a draft type and a saved type."""
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": document["revision"], "title": "  Daily counts  "},
    )

    assert response.status_code == 200, response.text
    named = response.json()
    assert named["id"] == document["id"]
    assert named["title"] == "Daily counts"
    assert named["body"] == document["body"]
    assert named["revision"] == document["revision"] + 1


async def test_a_title_of_spaces_is_not_a_name(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(
        client, normal_user_token_headers, connector_id, title="Report"
    )

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": document["revision"], "title": "   "},
    )

    assert response.status_code == 200, response.text
    assert response.json()["title"] is None


async def test_autosave_on_a_stale_revision_is_refused_and_writes_nothing(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """D63: a conflict is a question for a person, not a race the last writer wins."""
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)
    first = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": 1, "body": "select 2"},
    )
    assert first.status_code == 200, first.text

    late = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": 1, "body": "select 3"},
    )

    assert late.status_code == 409
    detail = late.json()["detail"]
    assert detail["revision"] == 2
    remote = await client.get(
        f"{BASE}/{document['id']}", headers=normal_user_token_headers
    )
    assert remote.json()["body"] == "select 2"


async def test_what_was_not_sent_does_not_change(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(
        client, normal_user_token_headers, connector_id, title="Kept"
    )

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": document["revision"], "body": "select 42"},
    )

    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["title"] == "Kept"
    assert saved["body"] == "select 42"


async def test_the_editor_layout_survives_a_round_trip(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={
            "revision": document["revision"],
            "layout": {"split_ratio": 0.35, "wrap": True},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["layout"] == {"split_ratio": 0.35, "wrap": True}


async def test_a_layout_outside_its_bounds_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": document["revision"], "layout": {"split_ratio": 9.0}},
    )

    assert response.status_code == 422


async def test_a_document_larger_than_the_ceiling_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """D64's exact boundary, counted in bytes rather than characters."""
    connector_id = await _connector(client, normal_user_token_headers)

    at_the_limit = await client.post(
        BASE,
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "body": "x" * settings.QUERY_DOCUMENT_MAX_BYTES,
        },
    )
    over = await client.post(
        BASE,
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "body": "x" * (settings.QUERY_DOCUMENT_MAX_BYTES + 1),
        },
    )

    assert at_the_limit.status_code == 200, at_the_limit.text
    assert over.status_code == 422


async def test_multibyte_text_is_measured_in_bytes(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A megabyte is a megabyte whatever alphabet the query is written in."""
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        BASE,
        headers=normal_user_token_headers,
        # Half the ceiling in characters, over it in bytes.
        json={
            "connector_id": connector_id,
            "body": "ы" * (settings.QUERY_DOCUMENT_MAX_BYTES // 2 + 1),
        },
    )

    assert response.status_code == 422


async def test_a_search_path_longer_than_the_bound_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        BASE,
        headers=normal_user_token_headers,
        json={
            "connector_id": connector_id,
            "search_path": [f"schema_{index}" for index in range(64)],
        },
    )

    assert response.status_code == 422


async def test_a_document_belonging_to_somebody_else_does_not_exist(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    """The same silence the connector routes keep: 404, not 403 (D33)."""
    _, their_headers = colleague
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)

    read = await client.get(f"{BASE}/{document['id']}", headers=their_headers)
    written = await client.patch(
        f"{BASE}/{document['id']}",
        headers=their_headers,
        json={"revision": 1, "body": "select 1"},
    )
    removed = await client.delete(f"{BASE}/{document['id']}", headers=their_headers)

    assert read.status_code == 404
    assert written.status_code == 404
    assert removed.status_code == 404


async def test_a_console_cannot_be_opened_on_a_connection_the_caller_cannot_see(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    colleague: tuple[User, dict[str, str]],
) -> None:
    _, their_headers = colleague
    connector_id = await _connector(client, normal_user_token_headers)

    response = await client.post(
        BASE, headers=their_headers, json={"connector_id": connector_id}
    )

    assert response.status_code == 404


async def test_a_document_whose_connection_went_is_still_readable(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """D63: losing the context does not lose the work."""
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(
        client, normal_user_token_headers, connector_id, body="select 7"
    )

    deleted = await client.delete(
        f"{CONNECTORS}/{connector_id}", headers=normal_user_token_headers
    )
    assert deleted.status_code == 200, deleted.text

    response = await client.get(
        f"{BASE}/{document['id']}", headers=normal_user_token_headers
    )

    assert response.status_code == 200
    orphan = response.json()
    assert orphan["body"] == "select 7"
    assert orphan["connector_id"] is None
    # Null is the whole statement that the context is unavailable.
    assert orphan["connector_label"] is None


async def test_the_library_lists_the_owner_s_documents_newest_first(
    client: AsyncClient, db: AsyncSession
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    connector_id = await _connector(client, headers)
    first = await _document(client, headers, connector_id, body="select 1")
    second = await _document(client, headers, connector_id, body="select 2")

    response = await client.get(BASE, headers=headers)

    assert response.status_code == 200
    listed = response.json()
    assert listed["count"] == 2
    assert [row["id"] for row in listed["data"]] == [second["id"], first["id"]]
    # A draft nobody has named is recognised by its first line, built per
    # response rather than stored.
    assert listed["data"][0]["preview"] == "select 2"
    assert "body" not in listed["data"][0]


async def test_the_library_filters_by_connection(
    client: AsyncClient, db: AsyncSession
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    one = await _connector(client, headers)
    other = await _connector(client, headers)
    mine = await _document(client, headers, one)
    await _document(client, headers, other)

    response = await client.get(BASE, headers=headers, params={"connector_id": one})

    assert response.status_code == 200
    listed = response.json()
    assert [row["id"] for row in listed["data"]] == [mine["id"]]
    assert listed["count"] == 1


async def test_search_reads_titles_and_bodies_and_nobody_else_s(
    client: AsyncClient, db: AsyncSession, colleague: tuple[User, dict[str, str]]
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    _, their_headers = colleague
    connector_id = await _connector(client, headers)
    theirs = await _connector(client, their_headers)
    by_body = await _document(
        client, headers, connector_id, body="select * from invoices"
    )
    by_title = await _document(
        client, headers, connector_id, body="select 1", title="Invoices per month"
    )
    await _document(client, headers, connector_id, body="select * from users")
    await _document(client, their_headers, theirs, body="select * from invoices")

    response = await client.get(BASE, headers=headers, params={"search": "INVOICES"})

    assert response.status_code == 200
    listed = response.json()
    assert {row["id"] for row in listed["data"]} == {by_body["id"], by_title["id"]}
    assert listed["count"] == 2


async def test_deleting_a_document_removes_it_without_a_trash_stage(
    client: AsyncClient, db: AsyncSession
) -> None:
    email = random_email()
    headers = await authentication_token_from_email(client=client, email=email, db=db)
    connector_id = await _connector(client, headers)
    document = await _document(client, headers, connector_id, body="select 9")

    removed = await client.delete(f"{BASE}/{document['id']}", headers=headers)
    assert removed.status_code == 200, removed.text

    library = await client.get(BASE, headers=headers)
    assert [row["id"] for row in library.json()["data"]] == []
    assert (await client.get(f"{BASE}/{document['id']}", headers=headers)).status_code == 404
    assert (await client.post(f"{BASE}/{document['id']}/restore", headers=headers)).status_code == 404


async def test_a_deleted_document_cannot_be_edited(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)
    await client.delete(f"{BASE}/{document['id']}", headers=normal_user_token_headers)

    response = await client.patch(
        f"{BASE}/{document['id']}",
        headers=normal_user_token_headers,
        json={"revision": document["revision"], "body": "select 5"},
    )

    assert response.status_code == 404


async def test_deletion_is_owned_and_has_no_second_purge_route(
    client: AsyncClient, db: AsyncSession, normal_user_token_headers: dict[str, str]
) -> None:
    """Only the owner can delete, and there is no later purge step."""
    connector_id = await _connector(client, normal_user_token_headers)
    document = await _document(client, normal_user_token_headers, connector_id)
    other_headers = await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )

    no_purge = await client.delete(
        f"{BASE}/{document['id']}/purge", headers=normal_user_token_headers
    )
    refused = await client.delete(
        f"{BASE}/{document['id']}", headers=other_headers
    )
    removed = await client.delete(
        f"{BASE}/{document['id']}", headers=normal_user_token_headers
    )
    gone = await client.get(
        f"{BASE}/{document['id']}", headers=normal_user_token_headers
    )

    assert no_purge.status_code == 404
    assert refused.status_code == 404
    assert removed.status_code == 200, removed.text
    assert gone.status_code == 404

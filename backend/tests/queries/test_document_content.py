"""Encrypted document content and immediate deletion.

The route tests prove behaviour through the API; these storage details cannot
be seen there. D63 requires the body to be unreadable in the database.
"""

import uuid

from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.queries.content import body_of, encrypted, preview_of
from app.queries.models import QueryDocument
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/queries/documents"
CONNECTORS = f"{settings.API_V1_STR}/connectors"

SECRET_SQL = "select * from salaries where person = 'a-very-recognisable-name'"


async def _headers(client: AsyncClient, db: AsyncSession) -> dict[str, str]:
    return await authentication_token_from_email(
        client=client, email=random_email(), db=db
    )


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
    client: AsyncClient, headers: dict[str, str], connector_id: str, body: str
) -> uuid.UUID:
    response = await client.post(
        BASE, headers=headers, json={"connector_id": connector_id, "body": body}
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


async def test_the_stored_body_is_not_plaintext(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Read straight out of the column, the way somebody with a backup would."""
    headers = await _headers(client, db)
    connector_id = await _connector(client, headers)
    document_id = await _document(client, headers, connector_id, SECRET_SQL)

    stored = await db.get(QueryDocument, document_id)

    assert stored is not None
    assert isinstance(stored.body, bytes)
    assert SECRET_SQL.encode() not in stored.body
    assert b"salaries" not in stored.body
    # And the same bytes read back through the one place that holds the key.
    assert body_of(stored) == SECRET_SQL


def test_two_documents_with_the_same_text_do_not_share_ciphertext() -> None:
    """A fresh nonce per write, so equal queries are not equal blobs."""
    assert encrypted("select 1") != encrypted("select 1")


async def test_deleting_a_document_removes_its_stored_body_immediately(
    client: AsyncClient, db: AsyncSession
) -> None:
    headers = await _headers(client, db)
    connector_id = await _connector(client, headers)
    document_id = await _document(client, headers, connector_id, "select 2")
    assert await db.get(QueryDocument, document_id) is not None

    removed = await client.delete(f"{BASE}/{document_id}", headers=headers)

    assert removed.status_code == 200, removed.text
    db.expire_all()
    assert await db.get(QueryDocument, document_id) is None


def test_a_preview_is_the_first_line_with_anything_on_it() -> None:
    assert preview_of("\n\n  select 1  \nfrom t") == "select 1"
    assert preview_of("") == ""
    assert preview_of("\n \n") == ""


def test_a_preview_does_not_grow_with_the_query() -> None:
    assert len(preview_of("select " + "x" * 1000)) == 120

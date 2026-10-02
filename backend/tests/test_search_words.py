"""The words somebody searches for are written down nowhere (D63).

Every route that takes words is asked with a marker, and every record logged
meanwhile — and the access line the server would write for each address — is
read for it.
"""

import logging
import uuid

import pytest
from httpx import AsyncClient

from app.core import logs
from app.core.config import settings

MARKER = f"quokka{uuid.uuid4().hex[:8]}"


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{settings.API_V1_STR}/connectors/",
        headers=headers,
        json={
            "name": f"words {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "/"},
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _access_line(path: str) -> str:
    """What the server's access log would hold for this address."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", path, "1.1", 200),
        None,
    )
    assert logs.DropQueryStrings().filter(record)
    return logs.JsonLines("backend").format(record)


async def test_the_words_of_every_search_reach_no_log_line(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    connector_id = await _file_connector(client, normal_user_token_headers)
    api = settings.API_V1_STR
    addresses = [
        f"{api}/queries/documents?search={MARKER}",
        f"{api}/queries/runs?search={MARKER}",
        f"{api}/connectors/{connector_id}/catalog/search?query={MARKER}",
        f"{api}/connectors/{connector_id}/catalog/search-contents?query={MARKER}",
    ]
    caplog.set_level(logging.DEBUG)

    for address in addresses:
        response = await client.get(address, headers=normal_user_token_headers)
        assert response.status_code == 200, response.text

    # Less the test's own client, which logs every address it asks for.
    written = [
        record.getMessage() for record in caplog.records if record.name != "httpx"
    ]
    written += [_access_line(address) for address in addresses]
    assert written
    assert not [line for line in written if MARKER in line]

"""A mailbox through the routes its tab calls (D366, D367, D370, D371).

The driver is tested on its own in tests/adapters/test_mail.py; this is the
same mailbox reached the way a screen reaches it, and the rules only the
routes hold: who may open it, and where a kept attachment goes.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.mailbox import MessageQuery, MessageRef
from app.core.config import settings
from app.users import crud, storage
from app.users.models import User
from tests.adapters.mail_fixture import (
    ALICE,
    BOB,
    adapter,
    deliver,
    empty,
    make_folder,
    options,
)
from tests.utils.socket import authenticated_socket
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import random_email

BASE = f"{settings.API_V1_STR}/connectors"


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    empty(ALICE)
    empty(BOB)
    yield


@pytest.fixture
async def mailbox(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> AsyncIterator[str]:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={"name": f"mail {uuid.uuid4()}", "adapter_type": "mail", "options": options()},
    )
    assert response.status_code == 200, response.text
    connector = str(response.json()["id"])
    yield connector
    await client.delete(f"{BASE}/{connector}", headers=normal_user_token_headers)


async def _call(
    client: AsyncClient, headers: dict[str, str], method: str, url: str, **kwargs: Any
) -> Any:
    response = await client.request(method, url, headers=headers, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_type_says_it_opens_as_a_mailbox(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/adapter-types/", headers=normal_user_token_headers
    )
    assert response.status_code == 200
    (mail,) = [one for one in response.json() if one["name"] == "mail"]
    assert mail["catalog_shape"] == "mailbox"
    assert mail["category"] == "mail"


async def test_the_password_never_comes_back(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mailbox: str
) -> None:
    body = await _call(client, normal_user_token_headers, "GET", f"{BASE}/{mailbox}")
    assert "dataplayer" not in json.dumps(body)


async def test_a_mailbox_is_read_written_and_put_away(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mailbox: str
) -> None:
    headers = normal_user_token_headers
    url = f"{BASE}/{mailbox}/mail"
    assert (await _call(client, headers, "POST", f"{BASE}/{mailbox}/check", json={}))["ok"]

    deliver(ALICE, "Hello", "Body", files=[("a.csv", "text/csv", b"1,2\n")])
    folders = await _call(client, headers, "GET", f"{url}/folders")
    assert any(one["role"] == "inbox" and one["unseen"] == 1 for one in folders)

    page = await _call(client, headers, "GET", f"{url}/messages", params={"folder": "INBOX"})
    (heading,) = page["messages"]
    ref = {"folder": "INBOX", "uid": heading["uid"]}
    message = await _call(client, headers, "GET", f"{url}/message", params=ref)
    assert message["subject"] == "Hello"
    (attachment,) = message["attachments"]

    downloaded = await client.get(
        f"{url}/attachment", headers=headers, params={**ref, "part": attachment["part"]}
    )
    assert downloaded.status_code == 200
    assert downloaded.content == b"1,2\n"
    assert 'filename="a.csv"' in downloaded.headers["content-disposition"]

    marked = await client.post(
        f"{url}/seen", headers=headers, json={"folder": "INBOX", "uids": [heading["uid"]], "seen": False}
    )
    assert marked.status_code == 204

    deleted = await _call(
        client, headers, "POST", f"{url}/delete", json={"folder": "INBOX", "uids": [heading["uid"]]}
    )
    assert deleted["moved_to"] == "Trash"


async def test_a_letter_is_sent_with_an_uploaded_file(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mailbox: str
) -> None:
    response = await client.post(
        f"{BASE}/{mailbox}/mail/send",
        headers=normal_user_token_headers,
        data={"message": json.dumps({"to": [BOB], "subject": "With a file", "text": "hi"})},
        files=[("files", ("отчёт.txt", b"numbers", "text/plain"))],
    )
    assert response.status_code == 200, response.text
    bob = adapter(BOB)
    (heading,) = (await bob.mail_messages(MessageQuery(folder="INBOX"))).messages
    letter = await bob.mail_message(MessageRef(folder="INBOX", uid=heading.uid))
    assert [one.filename for one in letter.attachments] == ["отчёт.txt"]


async def test_a_letter_without_a_recipient_is_refused(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mailbox: str
) -> None:
    response = await client.post(
        f"{BASE}/{mailbox}/mail/send",
        headers=normal_user_token_headers,
        data={"message": json.dumps({"to": [], "subject": "x"})},
    )
    assert response.status_code == 422


async def test_an_attachment_is_kept_in_the_owners_mail_folder(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    mailbox: str,
    db: AsyncSession,
) -> None:
    deliver(ALICE, "Keep", files=[("../report.csv", "text/csv", b"x,y\n")])
    headers = normal_user_token_headers
    url = f"{BASE}/{mailbox}/mail"
    (heading,) = (await _call(client, headers, "GET", f"{url}/messages", params={"folder": "INBOX"}))["messages"]
    ref = {"folder": "INBOX", "uid": heading["uid"]}
    (attachment,) = (await _call(client, headers, "GET", f"{url}/message", params=ref))["attachments"]
    kept = await _call(
        client, headers, "POST", f"{url}/attachment/keep", json={**ref, "part": attachment["part"]}
    )
    assert kept["path"].startswith(f"Mail/{ALICE}/")
    # The name a stranger chose is one plain name inside that folder.
    assert kept["path"].count("/") == 2
    owner = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert owner is not None
    assert (storage.home_dir(owner.id) / kept["path"]).read_bytes() == b"x,y\n"


async def test_a_grantee_cannot_open_somebody_elses_mailbox(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    mailbox: str,
    db: AsyncSession,
) -> None:
    """A grantee reads with the owner's credentials; for mail that is their letters (D367)."""
    email = random_email()
    colleague_headers = await authentication_token_from_email(client=client, email=email, db=db)
    colleague = await crud.get_user_by_email(session=db, email=email)
    assert isinstance(colleague, User)
    granted = await client.put(
        f"{BASE}/{mailbox}/grants",
        headers=normal_user_token_headers,
        json={"user_id": str(colleague.id), "access": "structure"},
    )
    assert granted.status_code == 200, granted.text
    for method, path, kwargs in [
        ("GET", "folders", {}),
        ("GET", "messages", {"params": {"folder": "INBOX"}}),
        ("POST", "delete", {"json": {"folder": "INBOX", "uids": [1]}}),
    ]:
        response = await client.request(
            method, f"{BASE}/{mailbox}/mail/{path}", headers=colleague_headers, **kwargs
        )
        assert response.status_code == 403, (path, response.text)


async def test_a_source_that_is_not_a_mailbox_answers_501(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.post(
        f"{BASE}/",
        headers=normal_user_token_headers,
        json={"name": f"files {uuid.uuid4()}", "adapter_type": "file", "options": {"path": "/"}},
    )
    assert response.status_code == 200
    connector = response.json()["id"]
    folders = await client.get(f"{BASE}/{connector}/mail/folders", headers=normal_user_token_headers)
    assert folders.status_code == 501
    assert folders.json()["detail"]["code"] == "mail.not_a_mailbox"


async def test_a_mailbox_has_no_catalog(
    client: AsyncClient, normal_user_token_headers: dict[str, str], mailbox: str
) -> None:
    response = await client.get(f"{BASE}/{mailbox}/catalog", headers=normal_user_token_headers)
    assert response.status_code == 501


async def test_the_type_shows_a_gmail_card_with_its_servers(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = await client.get(
        f"{settings.API_V1_STR}/adapter-types/", headers=normal_user_token_headers
    )
    (mail,) = [one for one in response.json() if one["name"] == "mail"]
    faces = {face["key"]: face for face in mail["faces"]}
    assert list(faces) == ["mail", "gmail"]
    assert faces["mail"]["options"] == {}
    assert faces["gmail"]["options"]["imap_host"] == "imap.gmail.com"
    assert faces["gmail"]["options"]["save_sent"] is False


async def test_a_letter_is_moved_drafted_and_sent_with_a_file_of_ones_folder(
    client: AsyncClient,
    normal_user_token_headers: dict[str, str],
    mailbox: str,
    db: AsyncSession,
) -> None:
    headers = normal_user_token_headers
    url = f"{BASE}/{mailbox}/mail"
    owner = await crud.get_user_by_email(session=db, email=settings.EMAIL_TEST_USER)
    assert owner is not None
    home = storage.home_dir(owner.id)
    (home / "MailTest").mkdir(parents=True, exist_ok=True)
    (home / "MailTest" / "plan.txt").write_bytes(b"the plan")

    listed = await _call(client, headers, "GET", f"{url}/my-files", params={"path": "MailTest"})
    assert [one["path"] for one in listed["entries"]] == ["MailTest/plan.txt"]
    outside = await client.get(f"{url}/my-files", headers=headers, params={"path": ".."})
    assert outside.status_code == 422

    make_folder("Projects")
    deliver(ALICE, "Move me")
    target = "Projects"
    (heading,) = (await _call(client, headers, "GET", f"{url}/messages", params={"folder": "INBOX"}))["messages"]
    moved = await _call(
        client, headers, "POST", f"{url}/move",
        json={"folder": "INBOX", "uids": [heading["uid"]], "target": target},
    )
    assert moved["moved_to"] == target

    letter = {"to": [BOB], "subject": "With my plan", "stored_files": ["MailTest/plan.txt"]}
    drafted = await client.post(f"{url}/draft", headers=headers, data={"message": json.dumps(letter)})
    assert drafted.status_code == 200, drafted.text
    sent = await client.post(
        f"{url}/send", headers=headers, data={"message": json.dumps(letter)}
    )
    assert sent.status_code == 200, sent.text
    bob = adapter(BOB)
    (got,) = (await bob.mail_messages(MessageQuery(folder="INBOX"))).messages
    received = await bob.mail_message(MessageRef(folder="INBOX", uid=got.uid))
    assert [one.filename for one in received.attachments] == ["plan.txt"]

    escaping = {"to": [BOB], "stored_files": ["../../etc/passwd"]}
    refused = await client.post(f"{url}/send", headers=headers, data={"message": json.dumps(escaping)})
    assert refused.status_code == 422


async def test_a_watcher_is_told_of_a_new_letter(
    normal_user_token_headers: dict[str, str],
    mailbox: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first round only learns the inbox; the letter after it is announced (D372)."""
    monkeypatch.setattr(settings, "MAIL_ARRIVALS_INTERVAL_SECONDS", 0.3)
    monkeypatch.setattr(settings, "HEALTH_GRACE_SECONDS", 0.0)
    async with authenticated_socket(normal_user_token_headers) as ws:
        await ws.send_json({"type": "subscribe", "topic": "mail.arrivals"})
        await asyncio.sleep(1.5)
        deliver(ALICE, "Fresh news")
        for _ in range(50):
            frame: dict[str, Any] = await ws.receive_json(timeout=15)
            if frame.get("topic") != "mail.arrivals":
                continue
            payload = frame["payload"]
            if payload["connector_id"] == mailbox and payload["count"] > 0:
                assert payload["count"] == 1
                assert payload["newest"][0]["subject"] == "Fresh news"
                assert payload["unseen"] >= 1
                return
        raise AssertionError("no arrival was announced")

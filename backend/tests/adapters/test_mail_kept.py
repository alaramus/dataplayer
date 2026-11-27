"""A mailbox's IMAP sessions kept between requests, and folders counted at once (D368)."""

import imaplib
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from pydantic import TypeAdapter

from app.adapters.mail import folders
from app.adapters.mail.adapter import MailAdapter
from app.adapters.mail.options import MailOptions
from app.adapters.mail.pool import KeptImap, key_for
from app.adapters.mail.session import MailSession
from app.adapters.mailbox import MessageQuery, MessageSelection
from app.adapters.resources import BorrowingStore, Pooling, ResourceStore
from tests.adapters.mail_fixture import ALICE, deliver, empty, make_folder, options


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    empty(ALICE)
    yield


@pytest.fixture
async def store() -> AsyncIterator[ResourceStore]:
    kept = ResourceStore(max_entries=4, max_idle_seconds=300)
    yield kept
    await kept.aclose()


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How many times a session was signed in."""
    count: list[int] = []
    real = MailSession.open_imap

    def counted(self: MailSession) -> imaplib.IMAP4:
        count.append(1)
        return real(self)

    monkeypatch.setattr(MailSession, "open_imap", counted)
    return count


def _kept_adapter(store: ResourceStore, connector_id: uuid.UUID) -> MailAdapter:
    model = TypeAdapter(MailOptions).validate_python(options())
    return MailAdapter(model, Pooling(store=store, connector_id=connector_id))


async def _kept_sessions(store: ResourceStore, connector_id: uuid.UUID) -> KeptImap:
    # The key ends in a hash of the password; it is found by how it starts.
    prefix = key_for(connector_id, "").rsplit(":", 1)[0]
    matching = [key for key in store._entries if key.startswith(prefix)]  # noqa: SLF001 - the store lists nothing
    assert len(matching) == 1
    found = await store.existing(matching[0], KeptImap)
    assert found is not None
    return found


async def _break_kept(store: ResourceStore, connector_id: uuid.UUID) -> None:
    """The kept session's socket shut under it, as a server dropping it would."""
    kept = await _kept_sessions(store, connector_id)
    lent = kept.take()
    assert lent is not None
    lent.conn.sock.shutdown(socket.SHUT_RDWR)
    kept.give(lent.conn)


async def test_requests_of_one_connection_sign_in_once(
    store: ResourceStore, opened: list[int]
) -> None:
    deliver(ALICE, "one")
    connector_id = uuid.uuid4()
    await _kept_adapter(store, connector_id).mail_folders()
    page = await _kept_adapter(store, connector_id).mail_messages(MessageQuery(folder="INBOX"))
    assert [one.subject for one in page.messages] == ["one"]
    assert len(opened) == 1


async def test_a_kept_session_still_sees_a_folder_made_elsewhere(
    store: ResourceStore,
) -> None:
    connector_id = uuid.uuid4()
    mail = _kept_adapter(store, connector_id)
    # Folders outlive a test on the server; this one is new every run.
    name = f"Made elsewhere {uuid.uuid4().hex[:8]}"
    before = {folder.name for folder in await mail.mail_folders()}
    make_folder(name)
    after = {folder.name for folder in await mail.mail_folders()}
    assert name not in before
    assert name in after


async def test_a_read_on_a_session_found_gone_is_read_again_on_a_new_one(
    store: ResourceStore, opened: list[int]
) -> None:
    deliver(ALICE, "one")
    connector_id = uuid.uuid4()
    mail = _kept_adapter(store, connector_id)
    await mail.mail_folders()
    await _break_kept(store, connector_id)
    page = await mail.mail_messages(MessageQuery(folder="INBOX"))
    assert [one.subject for one in page.messages] == ["one"]
    assert len(opened) == 2


async def test_a_change_asks_a_kept_session_first_and_is_not_run_twice(
    store: ResourceStore, opened: list[int]
) -> None:
    deliver(ALICE, "one")
    connector_id = uuid.uuid4()
    mail = _kept_adapter(store, connector_id)
    (heading,) = (await mail.mail_messages(MessageQuery(folder="INBOX"))).messages
    await _break_kept(store, connector_id)
    deleted = await mail.delete_messages(MessageSelection(folder="INBOX", uids=[heading.uid]))
    assert deleted.count == 1
    assert len(opened) == 2
    assert (await mail.mail_messages(MessageQuery(folder="INBOX"))).messages == []


async def test_a_store_that_keeps_nothing_signs_in_every_time(opened: list[int]) -> None:
    model = TypeAdapter(MailOptions).validate_python(options())
    mail = MailAdapter(model, Pooling(store=BorrowingStore(None), connector_id=uuid.uuid4()))
    await mail.mail_folders()
    await mail.mail_folders()
    assert len(opened) == 2


async def test_inbox_is_named_in_any_case() -> None:
    deliver(ALICE, "one")
    model = TypeAdapter(MailOptions).validate_python(options())
    page = await MailAdapter(model).mail_messages(MessageQuery(folder="inbox"))
    assert [one.subject for one in page.messages] == ["one"]


# --- counting at once ---------------------------------------------------------


def test_status_answers_are_read_by_folder_whatever_the_name_looks_like() -> None:
    counts = folders.statuses_of(
        [
            b'"Sent Items" (MESSAGES 12 UNSEEN 3)',
            b"INBOX (UNSEEN 1 MESSAGES 5)",
            (b'{14}', b"MESSAGES 9 (x)"),
            b" (MESSAGES 2 UNSEEN 0)",
            b'"Only one" (MESSAGES 4)',
            b"not a status line",
        ]
    )
    assert counts == {
        "Sent Items": (12, 3),
        "INBOX": (5, 1),
        "MESSAGES 9 (x)": (2, 0),
        "Only one": (4, None),
    }


class _ListStatusServer:
    """Just enough of imaplib.IMAP4 for a server that offers LIST-STATUS."""

    def __init__(self, *, refuse: bool = False) -> None:
        self.capabilities = ("IMAP4REV1", "LIST-STATUS", "SPECIAL-USE")
        self.untagged_responses: dict[str, list[Any]] = {}
        self.sent: list[tuple[str, ...]] = []
        self.refuse = refuse

    def xatom(self, name: str, *args: str) -> tuple[str, list[bytes]]:
        self.sent.append((name, *args))
        if self.refuse:
            raise imaplib.IMAP4.error("BAD")
        self.untagged_responses["LIST"] = [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\HasNoChildren \\Sent) "/" "Sent Items"',
            b'(\\Noselect \\HasChildren) "/" "[Gmail]"',
        ]
        self.untagged_responses["STATUS"] = [
            b'"INBOX" (MESSAGES 5 UNSEEN 2)',
            b'"Sent Items" (MESSAGES 7 UNSEEN 0)',
        ]
        return "OK", [b"LIST done"]

    def list(self) -> tuple[str, list[bytes]]:
        self.sent.append(("LIST",))
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

    def _command(self, name: str, *args: str) -> bytes:
        self.sent.append((name, *args))
        self.untagged_responses.setdefault("STATUS", []).append(
            f"{args[0]} (MESSAGES 1 UNSEEN 1)".encode()
        )
        return b"T1"

    def _command_complete(self, name: str, tag: bytes) -> tuple[str, list[bytes]]:
        return "OK", []


def test_list_status_counts_every_folder_in_one_command() -> None:
    server = _ListStatusServer()
    found = {one.name: one for one in folders.folders(server)}  # type: ignore[arg-type]  # a stand-in for imaplib.IMAP4
    assert len(server.sent) == 1
    assert server.sent[0][-1] == "(SPECIAL-USE STATUS (MESSAGES UNSEEN))"
    assert (found["INBOX"].messages, found["INBOX"].unseen) == (5, 2)
    assert found["Sent Items"].role == "sent"
    assert found["Sent Items"].messages == 7
    assert found["[Gmail]"].messages is None
    # What LIST said is kept for the rest of the operation.
    folders.checked(server, "Sent Items")  # type: ignore[arg-type]  # a stand-in for imaplib.IMAP4
    assert len(server.sent) == 1


def test_a_server_refusing_list_status_is_counted_the_other_way() -> None:
    server = _ListStatusServer(refuse=True)
    found = {one.name: one for one in folders.folders(server)}  # type: ignore[arg-type]  # a stand-in for imaplib.IMAP4
    assert [one[0] for one in server.sent] == ["LIST", "LIST", "STATUS"]
    assert found["INBOX"].messages == 1

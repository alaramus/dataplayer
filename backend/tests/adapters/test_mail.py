"""A mailbox over IMAP and SMTP, against the development mail server (D366–D370)."""

from collections.abc import Iterator
from email import message_from_bytes, policy

import pytest
from pydantic import ValidationError

from app.adapters.mail import messages as mail_messages
from app.adapters.mailbox import (
    MailboxRefused,
    MarkRequest,
    MessageQuery,
    MessageRef,
    MessageSelection,
    OutgoingFile,
    OutgoingMessage,
)
from tests.adapters.mail_fixture import (
    ALICE,
    BOB,
    DAVE,
    adapter,
    deliver,
    empty,
    make_folder,
)


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    empty(ALICE)
    empty(BOB)
    yield


async def _inbox_uids(address: str = ALICE) -> list[int]:
    page = await adapter(address).mail_messages(MessageQuery(folder="INBOX"))
    return [one.uid for one in page.messages]


# --- reaching it --------------------------------------------------------------


async def test_both_servers_are_checked() -> None:
    result = await adapter().check_connection()
    assert result.ok, result.message


async def test_a_wrong_password_names_the_imap_login() -> None:
    result = await adapter(password="wrong").check_connection()
    assert not result.ok
    assert result.error_kind == "auth"
    assert result.message == "The IMAP server refused the login or password"
    assert "wrong" not in result.message


async def test_an_unreachable_smtp_server_is_named_as_such() -> None:
    result = await adapter(smtp_port=1).check_connection()
    assert not result.ok
    assert result.error_kind == "network"
    assert result.message == "Could not reach the SMTP server"


async def test_starttls_is_refused_rather_than_skipped() -> None:
    """The test server offers no STARTTLS, so nothing is signed in to in plain text."""
    result = await adapter(imap_security="starttls").check_connection()
    assert not result.ok
    assert result.error_kind == "config"
    assert "STARTTLS" in result.message


# --- folders and pages --------------------------------------------------------


async def test_folders_carry_their_role_and_counts() -> None:
    deliver(ALICE, "one")
    deliver(ALICE, "two")
    make_folder("Sent")
    make_folder("Отчёты")
    folders = {folder.name: folder for folder in await adapter().mail_folders()}
    assert folders["INBOX"].role == "inbox"
    assert folders["INBOX"].messages == 2
    assert folders["INBOX"].unseen == 2
    assert folders["Sent"].role == "sent"
    # Named on the server in modified UTF-7, shown readable, asked for by id.
    assert folders["Отчёты"].id != "Отчёты"
    assert folders["Отчёты"].messages == 0


async def test_a_page_is_newest_first_and_counts_the_folder() -> None:
    for number in range(5):
        deliver(ALICE, f"letter {number}")
    mail = adapter()
    first = await mail.mail_messages(MessageQuery(folder="INBOX", limit=2))
    assert first.total == 5
    assert [one.subject for one in first.messages] == ["letter 4", "letter 3"]
    last = await mail.mail_messages(MessageQuery(folder="INBOX", offset=4, limit=2))
    assert [one.subject for one in last.messages] == ["letter 0"]
    beyond = await mail.mail_messages(MessageQuery(folder="INBOX", offset=10))
    assert beyond.messages == []


async def test_a_heading_says_who_what_and_whether_it_carries_a_file() -> None:
    deliver(ALICE, "Отчёт за ноябрь", files=[("отчёт.csv", "text/csv", b"a,b\n")])
    (heading,) = (await adapter().mail_messages(MessageQuery(folder="INBOX"))).messages
    assert heading.subject == "Отчёт за ноябрь"
    assert heading.sender is not None
    assert heading.sender.name == "Carol"
    assert heading.sender.address == "carol@example.com"
    assert [one.address for one in heading.to] == [ALICE]
    assert heading.has_attachments
    assert not heading.seen
    assert heading.size > 0


async def test_an_unknown_folder_is_refused_before_it_is_selected() -> None:
    with pytest.raises(MailboxRefused) as refused:
        await adapter().mail_messages(MessageQuery(folder='INBOX" (\\Deleted'))
    assert refused.value.status == 404


# --- searching ----------------------------------------------------------------


async def test_search_finds_words_in_the_subject_and_the_text() -> None:
    deliver(ALICE, "Квартальный отчёт", "ничего")
    deliver(ALICE, "Other", "the invoice is attached")
    deliver(ALICE, "Unrelated", "nothing here")
    mail = adapter()
    by_subject = await mail.mail_messages(MessageQuery(folder="INBOX", search="Квартальный"))
    assert [one.subject for one in by_subject.messages] == ["Квартальный отчёт"]
    by_text = await mail.mail_messages(MessageQuery(folder="INBOX", search="invoice"))
    assert by_text.total == 1


async def test_search_words_are_a_value_and_never_syntax() -> None:
    deliver(ALICE, "anything")
    found = await adapter().mail_messages(MessageQuery(folder="INBOX", search='x" OR ALL "'))
    assert found.total == 0


# --- one message --------------------------------------------------------------


async def test_reading_a_message_marks_it_read_and_parses_it() -> None:
    deliver(
        ALICE,
        "Report",
        "Plain\r\nlines",
        html="<p>Rich <img src='cid:logo'></p>",
        files=[("data.json", "application/json", b'{"a": 1}')],
    )
    mail = adapter()
    (uid,) = await _inbox_uids()
    message = await mail.mail_message(MessageRef(folder="INBOX", uid=uid))
    assert message.subject == "Report"
    assert message.text == "Plain\nlines\n"
    assert message.html is not None and "Rich" in message.html
    (attachment,) = message.attachments
    assert attachment.filename == "data.json"
    assert attachment.media_type == "application/json"
    assert attachment.size == 8
    page = await mail.mail_messages(MessageQuery(folder="INBOX"))
    assert page.messages[0].seen

    body = await mail.mail_attachment(MessageRef(folder="INBOX", uid=uid), attachment.part)
    assert body.body == b'{"a": 1}'


async def test_an_attachment_that_is_not_there_is_404() -> None:
    deliver(ALICE, "plain")
    (uid,) = await _inbox_uids()
    with pytest.raises(MailboxRefused) as refused:
        await adapter().mail_attachment(MessageRef(folder="INBOX", uid=uid), "7")
    assert refused.value.status == 404


async def test_a_message_gone_is_404() -> None:
    with pytest.raises(MailboxRefused) as refused:
        await adapter().mail_message(MessageRef(folder="INBOX", uid=999))
    assert refused.value.status == 404


async def test_a_message_over_the_ceiling_is_refused_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deliver(ALICE, "large", "x" * 2000)
    monkeypatch.setattr(mail_messages, "MAX_MESSAGE_BYTES", 100)
    (uid,) = await _inbox_uids()
    with pytest.raises(MailboxRefused) as refused:
        await adapter().mail_message(MessageRef(folder="INBOX", uid=uid))
    assert refused.value.status == 413
    monkeypatch.undo()
    page = await adapter().mail_messages(MessageQuery(folder="INBOX"))
    assert not page.messages[0].seen


# --- marking and deleting -----------------------------------------------------


async def test_read_and_unread_are_set_and_cleared() -> None:
    deliver(ALICE, "one")
    mail = adapter()
    (uid,) = await _inbox_uids()
    await mail.mark_messages(MarkRequest(folder="INBOX", uids=[uid], seen=True))
    assert (await mail.mail_messages(MessageQuery(folder="INBOX"))).messages[0].seen
    await mail.mark_messages(MarkRequest(folder="INBOX", uids=[uid], seen=False))
    assert not (await mail.mail_messages(MessageQuery(folder="INBOX"))).messages[0].seen


async def test_delete_moves_to_a_trash_made_for_it_then_deletes_for_good() -> None:
    deliver(ALICE, "keep")
    deliver(ALICE, "throw")
    mail = adapter()
    page = await mail.mail_messages(MessageQuery(folder="INBOX"))
    throw = next(one.uid for one in page.messages if one.subject == "throw")

    moved = await mail.delete_messages(MessageSelection(folder="INBOX", uids=[throw]))
    assert moved.moved_to == "Trash"  # made by the first test that deletes
    inbox = await mail.mail_messages(MessageQuery(folder="INBOX"))
    assert [one.subject for one in inbox.messages] == ["keep"]
    trash = await mail.mail_messages(MessageQuery(folder="Trash"))
    assert [one.subject for one in trash.messages] == ["throw"]

    gone = await mail.delete_messages(
        MessageSelection(folder="Trash", uids=[trash.messages[0].uid])
    )
    assert gone.moved_to is None
    assert (await mail.mail_messages(MessageQuery(folder="Trash"))).total == 0
    assert (await mail.mail_messages(MessageQuery(folder="INBOX"))).total == 1


# --- sending ------------------------------------------------------------------


async def test_a_letter_is_sent_with_its_files_and_a_copy_kept_in_sent() -> None:
    make_folder("Sent")
    sent = await adapter(display_name="Alice A").send_message(
        OutgoingMessage(to=[BOB], subject="Цифры", text="see the file"),
        [OutgoingFile("numbers.csv", "text/csv", b"1,2\n")],
    )
    assert sent.kept_copy
    bob = adapter(BOB)
    (heading,) = (await bob.mail_messages(MessageQuery(folder="INBOX"))).messages
    assert heading.subject == "Цифры"
    assert heading.sender is not None
    assert heading.sender.name == "Alice A"
    letter = await bob.mail_message(MessageRef(folder="INBOX", uid=heading.uid))
    assert [one.filename for one in letter.attachments] == ["numbers.csv"]
    copy = await adapter().mail_messages(MessageQuery(folder="Sent"))
    assert copy.total == 1
    assert copy.messages[0].seen


async def test_no_sent_folder_is_not_a_failure() -> None:
    sent = await adapter(DAVE).send_message(OutgoingMessage(to=[BOB], subject="hi"), [])
    assert not sent.kept_copy
    assert (await adapter(BOB).mail_messages(MessageQuery(folder="INBOX"))).total == 1


async def test_bcc_is_delivered_and_not_written_into_the_letter() -> None:
    await adapter().send_message(
        OutgoingMessage(to=[ALICE], bcc=[BOB], subject="quiet"), []
    )
    (uid,) = await _inbox_uids(BOB)
    raw, _ = await adapter(BOB)._session.imap(
        lambda conn: mail_messages.raw_message(
            conn, MessageRef(folder="INBOX", uid=uid), mark_seen=False
        )
    )
    assert "Bcc" not in message_from_bytes(raw, policy=policy.default)


async def test_a_reply_threads_and_marks_the_original_answered() -> None:
    deliver(ALICE, "Question", message_id="<question@example.com>")
    mail = adapter()
    (uid,) = await _inbox_uids()
    await mail.send_message(
        OutgoingMessage(
            to=[BOB], subject="Re: Question", reply_to=MessageRef(folder="INBOX", uid=uid)
        ),
        [],
    )
    (bob_uid,) = await _inbox_uids(BOB)
    raw, _ = await adapter(BOB)._session.imap(
        lambda conn: mail_messages.raw_message(
            conn, MessageRef(folder="INBOX", uid=bob_uid), mark_seen=False
        )
    )
    reply = message_from_bytes(raw, policy=policy.default)
    assert reply["In-Reply-To"] == "<question@example.com>"
    assert "<question@example.com>" in reply["References"]
    original = (await mail.mail_messages(MessageQuery(folder="INBOX"))).messages[0]
    assert original.answered


async def test_a_forward_takes_the_originals_files_along() -> None:
    deliver(ALICE, "With file", files=[("a.txt", "text/plain", b"abc")])
    (uid,) = await _inbox_uids()
    await adapter().send_message(
        OutgoingMessage(
            to=[BOB], subject="Fwd: With file", forward_of=MessageRef(folder="INBOX", uid=uid)
        ),
        [OutgoingFile("b.txt", "text/plain", b"def")],
    )
    (bob_uid,) = await _inbox_uids(BOB)
    letter = await adapter(BOB).mail_message(MessageRef(folder="INBOX", uid=bob_uid))
    assert sorted(one.filename for one in letter.attachments) == ["a.txt", "b.txt"]


def test_an_address_inside_a_network_is_taken_and_a_broken_one_is_not() -> None:
    """Not pydantic's EmailStr, which refuses `.local` domains."""
    assert OutgoingMessage(to=["ivan@corp.local"]).to == ["ivan@corp.local"]
    with pytest.raises(ValidationError):
        OutgoingMessage(to=["nobody@"])
    with pytest.raises(ValidationError):
        OutgoingMessage(to=["a@b, c@d"])

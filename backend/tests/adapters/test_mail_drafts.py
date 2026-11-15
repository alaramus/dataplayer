"""Moving letters, drafts, carried parts and what arrived (D372, D375, D376)."""

from collections.abc import Iterator

import pytest

from app.adapters.mailbox import (
    InboxMark,
    MailboxRefused,
    MessageQuery,
    MessageRef,
    MoveRequest,
    OutgoingFile,
    OutgoingMessage,
)
from tests.adapters.mail_fixture import ALICE, BOB, adapter, deliver, empty, make_folder


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    empty(ALICE)
    empty(BOB)
    yield


async def _uids(folder: str = "INBOX", address: str = ALICE) -> list[int]:
    page = await adapter(address).mail_messages(MessageQuery(folder=folder))
    return [one.uid for one in page.messages]


# --- moving (D376) ------------------------------------------------------------


async def test_a_letter_moves_to_a_folder_the_mailbox_has() -> None:
    make_folder("Projects")
    deliver(ALICE, "Plan")
    (uid,) = await _uids()
    moved = await adapter().move_messages(MoveRequest(folder="INBOX", uids=[uid], target="Projects"))
    assert moved.moved_to == "Projects"
    assert moved.count == 1
    assert await _uids() == []
    page = await adapter().mail_messages(MessageQuery(folder="Projects"))
    assert [one.subject for one in page.messages] == ["Plan"]


async def test_a_target_that_is_not_a_folder_is_refused_and_nothing_moves() -> None:
    deliver(ALICE, "Stay")
    (uid,) = await _uids()
    with pytest.raises(MailboxRefused) as refused:
        await adapter().move_messages(MoveRequest(folder="INBOX", uids=[uid], target="Nowhere"))
    assert refused.value.status == 404
    assert len(await _uids()) == 1


# --- drafts (D375) ------------------------------------------------------------


async def test_a_draft_is_kept_in_drafts_with_its_bcc_and_without_recipients() -> None:
    saved = await adapter().save_draft(
        OutgoingMessage(bcc=[BOB], subject="Unfinished", text="half a thought"),
        [OutgoingFile("a.txt", "text/plain", b"a")],
    )
    assert saved.folder == "Drafts"
    page = await adapter().mail_messages(MessageQuery(folder="Drafts"))
    (heading,) = page.messages
    assert heading.subject == "Unfinished"
    assert heading.seen
    draft = await adapter().mail_message(MessageRef(folder="Drafts", uid=heading.uid))
    assert draft.draft
    assert [one.address for one in draft.bcc] == [BOB]
    assert draft.text == "half a thought\n"
    assert [one.filename for one in draft.attachments] == ["a.txt"]


async def test_saving_a_draft_again_replaces_it_and_drops_a_part() -> None:
    mail = adapter()
    await mail.save_draft(
        OutgoingMessage(subject="v1"),
        [OutgoingFile("keep.txt", "text/plain", b"k"), OutgoingFile("drop.txt", "text/plain", b"d")],
    )
    (first,) = await _uids("Drafts")
    old = await mail.mail_message(MessageRef(folder="Drafts", uid=first))
    keep = [one.part for one in old.attachments if one.filename == "keep.txt"]
    await mail.save_draft(
        OutgoingMessage(
            subject="v2", draft_of=MessageRef(folder="Drafts", uid=first), keep_parts=keep
        ),
        [],
    )
    (second,) = await _uids("Drafts")
    assert second != first
    new = await mail.mail_message(MessageRef(folder="Drafts", uid=second))
    assert new.subject == "v2"
    assert [one.filename for one in new.attachments] == ["keep.txt"]


async def test_sending_a_draft_sends_its_files_and_removes_it() -> None:
    mail = adapter()
    await mail.save_draft(
        OutgoingMessage(to=[BOB], subject="Ready"), [OutgoingFile("r.csv", "text/csv", b"1")]
    )
    (draft,) = await _uids("Drafts")
    await mail.send_message(
        OutgoingMessage(to=[BOB], subject="Ready", draft_of=MessageRef(folder="Drafts", uid=draft)),
        [],
    )
    assert await _uids("Drafts") == []
    (got,) = await _uids(address=BOB)
    letter = await adapter(BOB).mail_message(MessageRef(folder="INBOX", uid=got))
    assert [one.filename for one in letter.attachments] == ["r.csv"]
    assert not letter.draft


async def test_a_letter_without_any_recipient_is_not_sent() -> None:
    with pytest.raises(MailboxRefused):
        await adapter().send_message(OutgoingMessage(subject="nobody"), [])


async def test_a_forward_drops_the_parts_it_is_told_to() -> None:
    deliver(ALICE, "Two files", files=[("a.txt", "text/plain", b"a"), ("b.txt", "text/plain", b"b")])
    (uid,) = await _uids()
    original = await adapter().mail_message(MessageRef(folder="INBOX", uid=uid))
    keep = [one.part for one in original.attachments if one.filename == "b.txt"]
    await adapter().send_message(
        OutgoingMessage(
            to=[BOB], subject="Fwd", forward_of=MessageRef(folder="INBOX", uid=uid), keep_parts=keep
        ),
        [],
    )
    (got,) = await _uids(address=BOB)
    letter = await adapter(BOB).mail_message(MessageRef(folder="INBOX", uid=got))
    assert [one.filename for one in letter.attachments] == ["b.txt"]


# --- what arrived (D372) ------------------------------------------------------


async def test_the_first_look_only_learns_where_the_inbox_is() -> None:
    deliver(ALICE, "old")
    first = await adapter().inbox_arrivals(None)
    assert first.count == 0
    assert first.newest == []
    assert first.unseen == 1
    assert first.mark.uidnext > 0


async def test_letters_after_the_mark_are_counted_and_the_newest_named() -> None:
    mail = adapter()
    mark = (await mail.inbox_arrivals(None)).mark
    for number in range(5):
        deliver(ALICE, f"new {number}")
    found = await mail.inbox_arrivals(mark)
    assert found.count == 5
    assert [one.subject for one in found.newest] == ["new 4", "new 3", "new 2"]
    again = await mail.inbox_arrivals(found.mark)
    assert again.count == 0


async def test_a_changed_uidvalidity_is_learnt_again_not_called_new() -> None:
    deliver(ALICE, "any")
    mark = (await adapter().inbox_arrivals(None)).mark
    stale = InboxMark(uidvalidity=mark.uidvalidity + 1, uidnext=1)
    found = await adapter().inbox_arrivals(stale)
    assert found.count == 0
    assert found.mark == mark

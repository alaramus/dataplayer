"""Messages in a folder: pages of headings, one message, marking and putting away.

A message is a UID in a folder (D368). Pages are read newest first by
sequence number, which every server keeps without SORT; a search pages its
UIDs the same way. Headings only for a list: a whole body brings every
attachment along with it.
"""

import base64
import email
import email.policy
import imaplib
import re
from datetime import datetime
from email.headerregistry import Address as HeaderAddress
from email.message import EmailMessage, Message
from email.utils import getaddresses, parsedate_to_datetime

from app.adapters.mail.folders import checked, ok, quoted, role_of, select, trash
from app.adapters.mailbox import (
    MAX_INLINE_BYTES,
    MAX_MESSAGE_BYTES,
    Arrivals,
    AttachmentBytes,
    InboxMark,
    MailAddress,
    MailAttachment,
    MailboxRefused,
    MailMessage,
    MessageHeading,
    MessagePage,
    MessageQuery,
    MessageRef,
    MessagesDeleted,
    MessageSelection,
    MessagesMoved,
    MoveRequest,
)
from app.core.translation import say

_HEADING_FIELDS = "FROM TO SUBJECT DATE CONTENT-TYPE"
_UID = re.compile(rb"\bUID\s+(\d+)", re.IGNORECASE)
_SIZE = re.compile(rb"\bRFC822\.SIZE\s+(\d+)", re.IGNORECASE)
_FLAGS = re.compile(rb"\bFLAGS\s+\(([^)]*)\)", re.IGNORECASE)


# --- pages of headings --------------------------------------------------------


def page(conn: imaplib.IMAP4, query: MessageQuery) -> MessagePage:
    exists = select(conn, query.folder, readonly=True)
    if query.search:
        uids = _search(conn, query.search)
        total = len(uids)
        newest_first = list(reversed(uids))
        chosen = newest_first[query.offset : query.offset + query.limit]
        headings = _headings(conn, ",".join(str(uid) for uid in chosen), by_uid=True) if chosen else []
    else:
        total = exists
        # Sequence numbers run 1..exists, oldest first: the page is a range
        # counted back from the end.
        last = exists - query.offset
        first = max(1, last - query.limit + 1)
        headings = _headings(conn, f"{first}:{last}", by_uid=False) if last >= 1 else []
    headings.sort(key=lambda heading: heading.uid, reverse=True)
    return MessagePage(folder=query.folder, total=total, offset=query.offset, messages=headings)


def _search(conn: imaplib.IMAP4, words: str) -> list[int]:
    """UIDs whose sender, subject or text holds the words, oldest first.

    The words go as a literal, so they are a value and never syntax (D2c), and
    any language is sent as it is.
    """
    conn.literal = words.strip().encode("utf-8")  # type: ignore[assignment]  # imaplib sends its one-shot literal as bytes; typeshed says str
    status, data = conn.uid("SEARCH", "CHARSET", "UTF-8", "TEXT")
    ok(status, say("The mail server would not search"))
    found = data[0] if data and isinstance(data[0], bytes) else b""
    return sorted(int(uid) for uid in found.split() if uid.isdigit())


def _headings(conn: imaplib.IMAP4, which: str, *, by_uid: bool) -> list[MessageHeading]:
    items = f"(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS ({_HEADING_FIELDS})])"
    if by_uid:
        status, data = conn.uid("FETCH", which, items)
    else:
        status, data = conn.fetch(which, items)
    ok(status, say("The mail server would not read the messages"))
    return [heading for heading in (_heading(meta, header) for meta, header in _fetched(data)) if heading]


def _fetched(data: list[object]) -> list[tuple[bytes, bytes]]:
    """Each message's FETCH line and its literal.

    A server may send FLAGS after the literal rather than before it, so what
    follows a literal up to the next one is part of the same line.
    """
    pairs: list[tuple[bytes, bytes]] = []
    for item in data:
        if isinstance(item, tuple) and len(item) == 2:
            meta, literal = item
            if isinstance(meta, bytes) and isinstance(literal, bytes):
                pairs.append((meta, literal))
        elif isinstance(item, bytes) and pairs:
            meta, literal = pairs[-1]
            pairs[-1] = (meta + b" " + item, literal)
    return pairs


def _heading(meta: bytes, header: bytes) -> MessageHeading | None:
    uid = _UID.search(meta)
    if uid is None:
        return None
    parsed = email.message_from_bytes(header, policy=email.policy.default)
    flags = _flags(meta)
    size = _SIZE.search(meta)
    senders = _addresses(parsed, "From")
    return MessageHeading(
        uid=int(uid.group(1)),
        subject=_text(parsed, "Subject"),
        sender=senders[0] if senders else None,
        to=_addresses(parsed, "To"),
        date=_date(parsed),
        seen="\\seen" in flags,
        flagged="\\flagged" in flags,
        answered="\\answered" in flags,
        size=int(size.group(1)) if size else 0,
        has_attachments=parsed.get_content_type() == "multipart/mixed",
    )


def _flags(meta: bytes) -> set[str]:
    found = _FLAGS.search(meta)
    if found is None:
        return set()
    return {flag.lower() for flag in found.group(1).decode("ascii", "replace").split()}


# --- headers, read forgivingly ------------------------------------------------


def _text(message: Message, name: str) -> str:
    try:
        value = message.get(name)
    except (ValueError, IndexError):
        return ""
    return "" if value is None else str(value).strip()


def _addresses(message: Message, name: str) -> list[MailAddress]:
    try:
        header = message.get(name)
    except (ValueError, IndexError):
        header = None
    if header is None:
        return []
    found: list[MailAddress] = []
    addresses = getattr(header, "addresses", None)
    if addresses is not None:
        for one in addresses:
            if isinstance(one, HeaderAddress) and one.addr_spec:
                found.append(MailAddress(name=one.display_name, address=one.addr_spec))
        return found
    for display, address in getaddresses([str(header)]):
        if address:
            found.append(MailAddress(name=display, address=address))
    return found


def _date(message: Message) -> datetime | None:
    raw = _text(message, "Date")
    if raw == "":
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None


# --- one message --------------------------------------------------------------


def raw_message(conn: imaplib.IMAP4, ref: MessageRef, *, mark_seen: bool) -> tuple[bytes, set[str]]:
    """The whole message, refused above the ceiling (D368).

    `BODY[]` rather than `BODY.PEEK[]` where it is being read: opening a
    letter marks it read, as every client does.
    """
    select(conn, ref.folder, readonly=not mark_seen)
    status, data = conn.uid("FETCH", str(ref.uid), "(RFC822.SIZE)")
    ok(status, say("The mail server would not read the message"))
    sizes = [_SIZE.search(item) for item in data if isinstance(item, bytes)]
    size = next((int(found.group(1)) for found in sizes if found), None)
    if size is None:
        raise MailboxRefused(say("The message is no longer in this folder"), status=404)
    if size > MAX_MESSAGE_BYTES:
        raise MailboxRefused(
            say("The message is larger than {mb} MB and is not opened here", mb=MAX_MESSAGE_BYTES // (1024 * 1024)),
            status=413,
        )
    body = "BODY[]" if mark_seen else "BODY.PEEK[]"
    status, data = conn.uid("FETCH", str(ref.uid), f"(FLAGS {body})")
    ok(status, say("The mail server would not read the message"))
    pairs = _fetched(data)
    if not pairs:
        raise MailboxRefused(say("The message is no longer in this folder"), status=404)
    meta, raw = pairs[0]
    return raw, _flags(meta)


def parsed(raw: bytes) -> EmailMessage:
    message = email.message_from_bytes(raw, policy=email.policy.default)
    assert isinstance(message, EmailMessage)  # policy.default makes one
    return message


def read(conn: imaplib.IMAP4, ref: MessageRef) -> MailMessage:
    raw, flags = raw_message(conn, ref, mark_seen=True)
    message = parsed(raw)
    senders = _addresses(message, "From")
    html = _body(message, "html")
    attachments, inline = _parts(message)
    return MailMessage(
        folder=ref.folder,
        uid=ref.uid,
        subject=_text(message, "Subject"),
        sender=senders[0] if senders else None,
        to=_addresses(message, "To"),
        cc=_addresses(message, "Cc"),
        bcc=_addresses(message, "Bcc"),
        reply_to=_addresses(message, "Reply-To"),
        date=_date(message),
        message_id=_text(message, "Message-ID") or None,
        flagged="\\flagged" in flags,
        answered="\\answered" in flags,
        draft="\\draft" in flags or role_of_folder(conn, ref.folder) == "drafts",
        text=_body(message, "plain"),
        html=html,
        inline_images=inline if html else {},
        attachments=attachments,
    )


def _body(message: EmailMessage, kind: str) -> str | None:
    try:
        part = message.get_body(preferencelist=(kind,))
    except (KeyError, LookupError):
        return None
    if part is None:
        return None
    try:
        content = part.get_content()
    except (LookupError, ValueError, UnicodeError):
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes):
            return None
        content = payload.decode("utf-8", "replace")
    # Mail's line ends are CRLF on the wire; a screen wants one kind.
    return content.replace("\r\n", "\n") if isinstance(content, str) else None


def _numbered(message: EmailMessage) -> list[tuple[str, Message]]:
    """Every part with its place in the walk, which names it in a request."""
    return [(str(index), part) for index, part in enumerate(message.walk())]


def _is_attachment(part: Message) -> bool:
    if part.is_multipart():
        return False
    disposition = part.get_content_disposition()
    if disposition == "attachment":
        return True
    if part.get_filename():
        return True
    # A part that is neither of the bodies and is not an image the HTML shows.
    return disposition != "inline" and part.get_content_maintype() not in {"text", "multipart"}


def _content_id(part: Message) -> str | None:
    raw = part.get("Content-ID")
    if raw is None:
        return None
    return str(raw).strip().strip("<>") or None


def _parts(message: EmailMessage) -> tuple[list[MailAttachment], dict[str, str]]:
    attachments: list[MailAttachment] = []
    inline: dict[str, str] = {}
    inline_bytes = 0
    for number, part in _numbered(message):
        if part.is_multipart() or not isinstance(part, Message):
            continue
        content_id = _content_id(part)
        payload = part.get_payload(decode=True)
        size = len(payload) if isinstance(payload, bytes) else 0
        if (
            content_id is not None
            and part.get_content_maintype() == "image"
            and isinstance(payload, bytes)
            and inline_bytes + size <= MAX_INLINE_BYTES
        ):
            inline[content_id] = f"data:{part.get_content_type()};base64,{base64.b64encode(payload).decode('ascii')}"
            inline_bytes += size
            if part.get_content_disposition() != "attachment":
                continue
        if not _is_attachment(part):
            continue
        attachments.append(
            MailAttachment(
                part=number,
                filename=part.get_filename() or say("attachment"),
                media_type=part.get_content_type(),
                size=size,
                content_id=content_id,
            )
        )
    return attachments, inline


def attachment(conn: imaplib.IMAP4, ref: MessageRef, part: str) -> AttachmentBytes:
    raw, _ = raw_message(conn, ref, mark_seen=False)
    return attachment_of(parsed(raw), part)


def attachment_of(message: EmailMessage, part: str) -> AttachmentBytes:
    for number, one in _numbered(message):
        if number != part or one.is_multipart():
            continue
        payload = one.get_payload(decode=True)
        if not isinstance(payload, bytes):
            break
        return AttachmentBytes(
            filename=one.get_filename() or say("attachment"),
            media_type=one.get_content_type(),
            body=payload,
        )
    raise MailboxRefused(say("The message has no such attachment"), status=404)


def attachments_of(message: EmailMessage) -> list[tuple[str, AttachmentBytes]]:
    """Every attachment by its part, for a forward or a draft to take along (D370)."""
    found: list[tuple[str, AttachmentBytes]] = []
    for number, part in _numbered(message):
        if part.is_multipart() or not _is_attachment(part):
            continue
        found.append((number, attachment_of(message, number)))
    return found


# --- marking and putting away -------------------------------------------------


def _uid_set(uids: list[int]) -> str:
    return ",".join(str(uid) for uid in sorted(set(uids)))


def mark(conn: imaplib.IMAP4, selection: MessageSelection, flag: str, on: bool) -> None:
    select(conn, selection.folder, readonly=False)
    status, _ = conn.uid("STORE", _uid_set(selection.uids), "+FLAGS" if on else "-FLAGS", f"({flag})")
    ok(status, say("The mail server would not mark the messages"))


def delete(conn: imaplib.IMAP4, selection: MessageSelection) -> MessagesDeleted:
    """Into Trash, or for good when already there (D370)."""
    select(conn, selection.folder, readonly=False)
    capabilities = {str(one).upper() for one in conn.capabilities}
    uids = _uid_set(selection.uids)
    bin_name = trash(conn)
    # `trash` may list folders, which leaves the selection as it was.
    if bin_name == selection.folder:
        _expunge(conn, uids, capabilities)
        return MessagesDeleted(moved_to=None, count=len(set(selection.uids)))
    if "MOVE" in capabilities:
        status, _ = conn.uid("MOVE", uids, quoted(bin_name))
        ok(status, say("The mail server would not move the messages to Trash"))
    else:
        status, _ = conn.uid("COPY", uids, quoted(bin_name))
        ok(status, say("The mail server would not move the messages to Trash"))
        _expunge(conn, uids, capabilities)
    return MessagesDeleted(moved_to=bin_name, count=len(set(selection.uids)))


def move(conn: imaplib.IMAP4, request: MoveRequest) -> MessagesMoved:
    """To a folder the mailbox has, checked before anything moves (D376)."""
    target = checked(conn, request.target).id
    select(conn, request.folder, readonly=False)
    count = len(set(request.uids))
    if target == request.folder:
        return MessagesMoved(moved_to=target, count=0)
    capabilities = {str(one).upper() for one in conn.capabilities}
    uids = _uid_set(request.uids)
    if "MOVE" in capabilities:
        status, _ = conn.uid("MOVE", uids, quoted(target))
        ok(status, say("The mail server would not move the messages"))
    else:
        status, _ = conn.uid("COPY", uids, quoted(target))
        ok(status, say("The mail server would not move the messages"))
        _expunge(conn, uids, capabilities)
    return MessagesMoved(moved_to=target, count=count)


def remove_for_good(conn: imaplib.IMAP4, ref: MessageRef) -> None:
    """One letter gone, not through Trash: a draft replaced by its next (D375)."""
    select(conn, ref.folder, readonly=False)
    capabilities = {str(one).upper() for one in conn.capabilities}
    _expunge(conn, str(ref.uid), capabilities)


def role_of_folder(conn: imaplib.IMAP4, folder: str) -> str | None:
    return role_of(checked(conn, folder))


# --- what arrived (D372) ------------------------------------------------------

_STATUS_NUMBER = re.compile(rb"(UIDVALIDITY|UIDNEXT|UNSEEN)\s+(\d+)", re.IGNORECASE)
NEWEST = 3


def arrivals(conn: imaplib.IMAP4, since: InboxMark | None) -> Arrivals:
    """The inbox's place and what came after `since`, with one STATUS when nothing did."""
    status, data = conn.status("INBOX", "(UIDVALIDITY UIDNEXT UNSEEN)")
    ok(status, say("The mail server would not open the folder"))
    line = data[0] if data and isinstance(data[0], bytes) else b""
    numbers = {key.upper(): int(value) for key, value in _STATUS_NUMBER.findall(line)}
    mark_now = InboxMark(
        uidvalidity=numbers.get(b"UIDVALIDITY", 0), uidnext=numbers.get(b"UIDNEXT", 0)
    )
    unseen = numbers.get(b"UNSEEN", 0)
    if (
        since is None
        or since.uidvalidity != mark_now.uidvalidity
        or mark_now.uidnext <= since.uidnext
    ):
        return Arrivals(mark=mark_now, unseen=unseen, count=0, newest=[])
    conn.select("INBOX", readonly=True)
    status, data = conn.uid("SEARCH", f"UID {since.uidnext}:*")
    ok(status, say("The mail server would not search"))
    found = data[0] if data and isinstance(data[0], bytes) else b""
    # `n:*` always names the last message, even one older than n.
    new = sorted(uid for uid in (int(one) for one in found.split() if one.isdigit()) if uid >= since.uidnext)
    newest = new[-NEWEST:]
    headings = (
        _headings(conn, ",".join(str(uid) for uid in newest), by_uid=True) if newest else []
    )
    headings.sort(key=lambda heading: heading.uid, reverse=True)
    return Arrivals(mark=mark_now, unseen=unseen, count=len(new), newest=headings)


def _expunge(conn: imaplib.IMAP4, uids: str, capabilities: set[str]) -> None:
    status, _ = conn.uid("STORE", uids, "+FLAGS.SILENT", "(\\Deleted)")
    ok(status, say("The mail server would not delete the messages"))
    if "UIDPLUS" in capabilities:
        status, _ = conn.uid("EXPUNGE", uids)
    else:
        # Without UIDPLUS a plain EXPUNGE also removes what other clients
        # marked deleted here; there is no narrower command (D370).
        status, _ = conn.expunge()
    ok(status, say("The mail server would not delete the messages"))

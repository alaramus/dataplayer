"""Writing a letter: composed here, sent through SMTP, a copy kept in Sent (D370),
or appended to Drafts to be finished later (D375)."""

import imaplib
import re
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.adapters.mail.folders import drafts, ok, quoted, select, with_role
from app.adapters.mail.messages import attachments_of, parsed, raw_message
from app.adapters.mail.options import MailOptions
from app.adapters.mailbox import (
    MAX_OUTGOING_BYTES,
    AttachmentBytes,
    MailboxRefused,
    MessageRef,
    OutgoingFile,
    OutgoingMessage,
)
from app.core.translation import say

# `[APPENDUID <validity> <uid>]`, which a server with UIDPLUS answers APPEND with.
_APPENDUID = re.compile(rb"APPENDUID\s+\d+\s+(\d+)", re.IGNORECASE)


class Original:
    """What an answer, a forward or a draft being finished takes from a letter."""

    def __init__(self, message: EmailMessage) -> None:
        self.message_id = str(message.get("Message-ID") or "").strip()
        self.references = " ".join(str(message.get("References") or "").split())
        self.in_reply_to = str(message.get("In-Reply-To") or "").strip()
        self.attachments: list[tuple[str, AttachmentBytes]] = attachments_of(message)


def original(conn: imaplib.IMAP4, ref: MessageRef) -> Original:
    raw, _ = raw_message(conn, ref, mark_seen=False)
    return Original(parsed(raw))


def compose(
    options: MailOptions,
    outgoing: OutgoingMessage,
    files: list[OutgoingFile],
    *,
    answered: Original | None,
    carried_from: Original | None,
    as_draft: bool = False,
) -> EmailMessage:
    """The letter, with the parts of `carried_from` it keeps (D375).

    `carried_from` is the letter forwarded or the draft being finished.
    """
    message = EmailMessage()
    sender = options.address
    message["From"] = formataddr((options.display_name, sender)) if options.display_name else sender
    if outgoing.to:
        message["To"] = ", ".join(outgoing.to)
    if outgoing.cc:
        message["Cc"] = ", ".join(outgoing.cc)
    # A draft is read back by whoever finishes it, so its Bcc is kept; a sent
    # letter never names one (D370).
    if as_draft and outgoing.bcc:
        message["Bcc"] = ", ".join(outgoing.bcc)
    message["Subject"] = outgoing.subject
    message["Date"] = formatdate(localtime=True)
    domain = sender.rsplit("@", 1)[-1]
    message["Message-ID"] = make_msgid(domain=domain)
    if answered is not None and answered.message_id:
        # Read by the server from the original, never sent by the client (D370).
        message["In-Reply-To"] = answered.message_id
        message["References"] = " ".join(
            part for part in (answered.references, answered.message_id) if part
        )
    elif carried_from is not None and carried_from.in_reply_to and outgoing.draft_of is not None:
        # A draft of an answer stays an answer once it is finished.
        message["In-Reply-To"] = carried_from.in_reply_to
        if carried_from.references:
            message["References"] = carried_from.references
    message.set_content(outgoing.text)

    keep = None if outgoing.keep_parts is None else set(outgoing.keep_parts)
    carried: list[AttachmentBytes] = (
        []
        if carried_from is None
        else [one for part, one in carried_from.attachments if keep is None or part in keep]
    )
    carried.extend(AttachmentBytes(one.filename, one.media_type, one.body) for one in files)
    total = sum(len(one.body) for one in carried)
    if total > MAX_OUTGOING_BYTES:
        raise MailboxRefused(
            say(
                "Attachments come to more than {mb} MB, which is more than a letter may carry",
                mb=MAX_OUTGOING_BYTES // (1024 * 1024),
            ),
            status=413,
        )
    for one in carried:
        maintype, _, subtype = one.media_type.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(one.body, maintype=maintype, subtype=subtype, filename=one.filename)
    if as_draft:
        # A draft is a letter yet to be sent, and has no date of sending.
        del message["Date"]
    return message


def recipients(outgoing: OutgoingMessage) -> list[str]:
    # Bcc is a list of addresses to send to and never a header of the letter.
    return list(dict.fromkeys([*outgoing.to, *outgoing.cc, *outgoing.bcc]))


def keep_copy(conn: imaplib.IMAP4, message: EmailMessage) -> bool:
    """Appended to Sent, read; no Sent folder is not an error (D370)."""
    sent = with_role(conn, "sent")
    if sent is None:
        return False
    status, _ = conn.append(
        quoted(sent), "(\\Seen)", imaplib.Time2Internaldate(time.time()), message.as_bytes()
    )
    ok(status, say("The mail server would not keep a copy in Sent"))
    return True


def append_draft(conn: imaplib.IMAP4, message: EmailMessage) -> tuple[str, int | None]:
    """Into Drafts, made if missing; the folder and the new UID where told (D375)."""
    folder = drafts(conn)
    status, data = conn.append(
        quoted(folder),
        "(\\Draft \\Seen)",
        imaplib.Time2Internaldate(time.time()),
        message.as_bytes(),
    )
    ok(status, say("The mail server would not keep the draft"))
    said = b" ".join(one for one in data if isinstance(one, bytes))
    found = _APPENDUID.search(said)
    return folder, int(found.group(1)) if found else None


def mark_answered(conn: imaplib.IMAP4, ref: MessageRef) -> None:
    select(conn, ref.folder, readonly=False)
    conn.uid("STORE", str(ref.uid), "+FLAGS", "(\\Answered)")

"""Writing a letter: composed here, sent through SMTP, a copy kept in Sent (D370)."""

import imaplib
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.adapters.mail.folders import ok, quoted, select, with_role
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


class Original:
    """What a reply or a forward takes from the letter it answers."""

    def __init__(self, message: EmailMessage) -> None:
        self.message_id = str(message.get("Message-ID") or "").strip()
        self.references = " ".join(str(message.get("References") or "").split())
        self.attachments: list[AttachmentBytes] = attachments_of(message)


def original(conn: imaplib.IMAP4, ref: MessageRef) -> Original:
    raw, _ = raw_message(conn, ref, mark_seen=False)
    return Original(parsed(raw))


def compose(
    options: MailOptions,
    outgoing: OutgoingMessage,
    files: list[OutgoingFile],
    *,
    answered: Original | None,
    forwarded: Original | None,
) -> EmailMessage:
    message = EmailMessage()
    sender = options.address
    message["From"] = formataddr((options.display_name, sender)) if options.display_name else sender
    message["To"] = ", ".join(outgoing.to)
    if outgoing.cc:
        message["Cc"] = ", ".join(outgoing.cc)
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
    message.set_content(outgoing.text)

    carried: list[AttachmentBytes] = [] if forwarded is None else list(forwarded.attachments)
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


def mark_answered(conn: imaplib.IMAP4, ref: MessageRef) -> None:
    select(conn, ref.folder, readonly=False)
    conn.uid("STORE", str(ref.uid), "+FLAGS", "(\\Answered)")

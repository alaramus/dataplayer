"""A mailbox as a source: read over IMAP, written over SMTP, opened as a mailbox (D366).

`imaplib` and `smtplib` are imported by this package and by nothing else, the
rule every driver follows.
"""

import imaplib
import logging
import smtplib
from email.message import EmailMessage

from app.adapters.mail import folders, messages, sending
from app.adapters.mail.options import MailOptions
from app.adapters.mail.session import MailSession
from app.adapters.mailbox import (
    Arrivals,
    AttachmentBytes,
    DraftSaved,
    InboxMark,
    MailboxRefused,
    MailFolder,
    MailMessage,
    MarkRequest,
    MessagePage,
    MessageQuery,
    MessageRef,
    MessagesDeleted,
    MessageSelection,
    MessageSent,
    MessagesMoved,
    MoveRequest,
    OutgoingFile,
    OutgoingMessage,
)
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.registry import AdapterContext, CatalogFace, register
from app.adapters.resources import Pooling
from app.core.translation import N_, say

logger = logging.getLogger(__name__)


class MailAdapter:
    """Facade over one session's way to the two servers (D2b)."""

    def __init__(self, options: MailOptions, pooling: Pooling | None = None) -> None:
        self._session = MailSession(options, pooling)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    def mailbox_address(self) -> str:
        return self._session.options.address

    async def mail_folders(self) -> list[MailFolder]:
        return await self._session.imap(folders.folders, repeatable=True)

    async def mail_messages(self, query: MessageQuery) -> MessagePage:
        return await self._session.imap(lambda conn: messages.page(conn, query), repeatable=True)

    async def mail_message(self, ref: MessageRef) -> MailMessage:
        # Read twice, it is marked read twice: nothing a second run changes.
        return await self._session.imap(lambda conn: messages.read(conn, ref), repeatable=True)

    async def mail_attachment(self, ref: MessageRef, part: str) -> AttachmentBytes:
        return await self._session.imap(
            lambda conn: messages.attachment(conn, ref, part), repeatable=True
        )

    async def mark_messages(self, request: MarkRequest) -> None:
        await self._session.imap(
            lambda conn: messages.mark(conn, request, "\\Seen", request.seen), repeatable=True
        )

    async def delete_messages(self, selection: MessageSelection) -> MessagesDeleted:
        return await self._session.imap(lambda conn: messages.delete(conn, selection))

    async def move_messages(self, request: MoveRequest) -> MessagesMoved:
        return await self._session.imap(lambda conn: messages.move(conn, request))

    async def inbox_arrivals(self, since: InboxMark | None) -> Arrivals:
        return await self._session.imap(
            lambda conn: messages.arrivals(conn, since), repeatable=True
        )

    async def _originals(
        self, message: OutgoingMessage
    ) -> tuple[sending.Original | None, sending.Original | None]:
        """The letter answered, and the one whose attachments are carried.

        A forward carries the forwarded letter's; a draft being finished
        carries its own (D375).
        """
        reply_to = message.reply_to
        carried = message.draft_of or message.forward_of
        if reply_to is None and carried is None:
            return None, None

        def read(conn: imaplib.IMAP4) -> tuple[sending.Original | None, sending.Original | None]:
            return (
                None if reply_to is None else sending.original(conn, reply_to),
                None if carried is None else sending.original(conn, carried),
            )

        return await self._session.imap(read, repeatable=True)

    async def send_message(
        self, message: OutgoingMessage, files: list[OutgoingFile]
    ) -> MessageSent:
        if not message.to and not message.cc and not message.bcc:
            raise MailboxRefused(say("Name at least one recipient"))
        answered, carried = await self._originals(message)
        options = self._session.options
        letter = sending.compose(options, message, files, answered=answered, carried_from=carried)
        to = sending.recipients(message)

        def send(conn: smtplib.SMTP) -> None:
            try:
                conn.send_message(letter, from_addr=options.address, to_addrs=to)
            except smtplib.SMTPRecipientsRefused:
                raise MailboxRefused(say("The mail server refused the recipients")) from None
            except smtplib.SMTPSenderRefused:
                raise MailboxRefused(
                    say("The mail server refused to send from {address}", address=options.address)
                ) from None
            except smtplib.SMTPDataError:
                raise MailboxRefused(say("The mail server refused the letter")) from None

        await self._session.smtp(send)
        return MessageSent(
            kept_copy=await self._after_sending(letter, message.reply_to, message.draft_of)
        )

    async def save_draft(
        self, message: OutgoingMessage, files: list[OutgoingFile]
    ) -> DraftSaved:
        """Appended to Drafts; the draft it replaces goes for good (D375)."""
        answered, carried = await self._originals(message)
        letter = sending.compose(
            self._session.options,
            message,
            files,
            answered=answered,
            carried_from=carried,
            as_draft=True,
        )
        replaced = message.draft_of

        def keep(conn: imaplib.IMAP4) -> DraftSaved:
            folder, uid = sending.append_draft(conn, letter)
            if replaced is not None:
                messages.remove_for_good(conn, replaced)
            return DraftSaved(folder=folder, uid=uid)

        return await self._session.imap(keep)

    async def _after_sending(
        self, letter: EmailMessage, reply_to: MessageRef | None, draft_of: MessageRef | None
    ) -> bool:
        """The copy, the original's mark and the finished draft gone.

        The letter is gone either way, so a failure here is said as no copy
        kept rather than as an error a person would answer by sending again.
        """
        keep = self._session.options.save_sent

        def finish(conn: imaplib.IMAP4) -> bool:
            kept = sending.keep_copy(conn, letter) if keep else False
            if reply_to is not None:
                sending.mark_answered(conn, reply_to)
            if draft_of is not None:
                messages.remove_for_good(conn, draft_of)
            return kept

        try:
            return await self._session.imap(finish)
        except (AdapterError, MailboxRefused) as failure:
            logger.warning("Sent, but not finished afterwards: %s", failure)
            return False


@register(
    name="mail",
    title=N_("Email"),
    category="mail",
    catalog_shape="mailbox",
    description=N_(
        "A mailbox over IMAP and SMTP. Read the folders and letters, write, "
        "answer and forward, delete to Trash, and take an attachment to the "
        "computer or into your folder. Only its owner opens it."
    ),
    options_schema=MailOptions,
    adapter_class=MailAdapter,
    # One type and one form; the Gmail card only fills in its servers (D373).
    # No Outlook card: Microsoft refuses a password over IMAP without OAuth.
    faces=(
        CatalogFace(key="mail", title=N_("Email")),
        CatalogFace(
            key="gmail",
            title=N_("Gmail"),
            options={
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "imap_security": "tls",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 465,
                "smtp_security": "tls",
                # Gmail files what it sends by itself; a copy would be a second.
                "save_sent": False,
            },
            note=N_(
                "Gmail needs an app password, not your account's: make one at "
                "myaccount.google.com/apppasswords."
            ),
            note_link="https://myaccount.google.com/apppasswords",
        ),
    ),
)
def _build(options: MailOptions, context: AdapterContext) -> MailAdapter:
    return MailAdapter(options, context.pooling)

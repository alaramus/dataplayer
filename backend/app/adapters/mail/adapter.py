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
    AttachmentBytes,
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
    OutgoingFile,
    OutgoingMessage,
)
from app.adapters.protocol import AdapterError, ConnectionCheckResult
from app.adapters.registry import AdapterContext, register
from app.core.translation import N_, say

logger = logging.getLogger(__name__)


class MailAdapter:
    """Facade over one session's way to the two servers (D2b)."""

    def __init__(self, options: MailOptions) -> None:
        self._session = MailSession(options)

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    def mailbox_address(self) -> str:
        return self._session.options.address

    async def mail_folders(self) -> list[MailFolder]:
        return await self._session.imap(folders.folders)

    async def mail_messages(self, query: MessageQuery) -> MessagePage:
        return await self._session.imap(lambda conn: messages.page(conn, query))

    async def mail_message(self, ref: MessageRef) -> MailMessage:
        return await self._session.imap(lambda conn: messages.read(conn, ref))

    async def mail_attachment(self, ref: MessageRef, part: str) -> AttachmentBytes:
        return await self._session.imap(lambda conn: messages.attachment(conn, ref, part))

    async def mark_messages(self, request: MarkRequest) -> None:
        await self._session.imap(lambda conn: messages.mark(conn, request, "\\Seen", request.seen))

    async def delete_messages(self, selection: MessageSelection) -> MessagesDeleted:
        return await self._session.imap(lambda conn: messages.delete(conn, selection))

    async def send_message(
        self, message: OutgoingMessage, files: list[OutgoingFile]
    ) -> MessageSent:
        answered = forwarded = None
        if message.reply_to is not None or message.forward_of is not None:
            reply_to, forward_of = message.reply_to, message.forward_of

            def originals(
                conn: imaplib.IMAP4,
            ) -> tuple[sending.Original | None, sending.Original | None]:
                return (
                    None if reply_to is None else sending.original(conn, reply_to),
                    None if forward_of is None else sending.original(conn, forward_of),
                )

            answered, forwarded = await self._session.imap(originals)
        options = self._session.options
        letter = sending.compose(options, message, files, answered=answered, forwarded=forwarded)
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
        return MessageSent(kept_copy=await self._after_sending(letter, message.reply_to))

    async def _after_sending(
        self, letter: EmailMessage, reply_to: MessageRef | None
    ) -> bool:
        """The copy and the original's mark; the letter is gone either way.

        A failure here is not a failure to send, so it is said as no copy kept
        rather than as an error a person would answer by sending again.
        """
        keep = self._session.options.save_sent

        def finish(conn: imaplib.IMAP4) -> bool:
            kept = sending.keep_copy(conn, letter) if keep else False
            if reply_to is not None:
                sending.mark_answered(conn, reply_to)
            return kept

        try:
            return await self._session.imap(finish)
        except (AdapterError, MailboxRefused) as failure:
            logger.warning("Sent, but not kept in Sent: %s", failure)
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
)
def _build(options: MailOptions, context: AdapterContext) -> MailAdapter:
    del context
    return MailAdapter(options)

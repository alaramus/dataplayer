"""The development mail server, as the mail tests use it (D368).

GreenMail holds two mailboxes, alice@ and bob@example.com, with the password
`dataplayer`, no TLS. Letters are put in over its SMTP directly, so a test of
reading does not depend on the source's own sending.
"""

import imaplib
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib.parse import parse_qs, urlsplit

from pydantic import TypeAdapter

from app.adapters.mail import utf7
from app.adapters.mail.adapter import MailAdapter
from app.adapters.mail.folders import listed, quoted
from app.adapters.mail.options import MailOptions
from tests.utils.services import MAIL

PASSWORD = "dataplayer"
ALICE = "alice@example.com"
BOB = "bob@example.com"
# Never given a Sent folder.
DAVE = "dave@example.com"
DELETED = r"(\Deleted)"


def _where() -> tuple[str, int, int]:
    parts = urlsplit(MAIL.require())
    smtp = int(parse_qs(parts.query).get("smtp", ["3025"])[0])
    return parts.hostname or "127.0.0.1", parts.port or 3143, smtp


def options(address: str = ALICE, **changes: Any) -> dict[str, Any]:
    host, imap_port, smtp_port = _where()
    return {
        "address": address,
        "password": PASSWORD,
        "imap_host": host,
        "imap_port": imap_port,
        "imap_security": "none",
        "smtp_host": host,
        "smtp_port": smtp_port,
        "smtp_security": "none",
        "smtp_auth": "same",
        **changes,
    }


def adapter(address: str = ALICE, **changes: Any) -> MailAdapter:
    return MailAdapter(TypeAdapter(MailOptions).validate_python(options(address, **changes)))


def deliver(
    to: str,
    subject: str,
    text: str = "Hello",
    *,
    html: str | None = None,
    files: list[tuple[str, str, bytes]] | None = None,
    message_id: str | None = None,
) -> None:
    host, _, smtp_port = _where()
    letter = EmailMessage()
    letter["From"] = "Carol <carol@example.com>"
    letter["To"] = to
    letter["Subject"] = subject
    if message_id is not None:
        letter["Message-ID"] = message_id
    letter.set_content(text)
    if html is not None:
        letter.add_alternative(html, subtype="html")
    for name, media_type, body in files or []:
        maintype, _, subtype = media_type.partition("/")
        letter.add_attachment(body, maintype=maintype, subtype=subtype, filename=name)
    with smtplib.SMTP(host, smtp_port, timeout=10) as smtp:
        smtp.send_message(letter)


def empty(address: str = ALICE) -> None:
    """Every letter gone from every folder.

    Folders are left: GreenMail drops the session that deletes one.
    """
    host, imap_port, _ = _where()
    conn = imaplib.IMAP4(host, imap_port, timeout=10)
    try:
        conn.login(address, PASSWORD)
        for one in listed(conn):
            status, data = conn.select(quoted(one.id))
            if status == "OK" and data and data[0] not in (b"0", None):
                conn.store("1:*", "+FLAGS.SILENT", DELETED)
                conn.expunge()
    finally:
        conn.logout()


def make_folder(name: str, address: str = ALICE) -> None:
    host, imap_port, _ = _where()
    conn = imaplib.IMAP4(host, imap_port, timeout=10)
    try:
        conn.login(address, PASSWORD)
        conn.create(quoted(utf7.encode(name)))
    finally:
        conn.logout()

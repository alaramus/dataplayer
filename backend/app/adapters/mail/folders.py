"""A mailbox's folders: what LIST says, what each is for, and its counts (D368)."""

import imaplib
import re
from dataclasses import dataclass

from app.adapters.mail import utf7
from app.adapters.mailbox import FolderRole, MailboxRefused, MailFolder
from app.core.translation import say

# `(\HasNoChildren \Sent) "/" "Sent Items"`; the name may also be an atom, or
# arrive apart as a literal.
_LIST_LINE = re.compile(
    rb'^\((?P<flags>[^)]*)\)\s+(?P<delimiter>"(?:[^"\\]|\\.)*"|NIL)\s*(?P<name>.*)$',
    re.IGNORECASE,
)
_STATUS = re.compile(rb"(MESSAGES|UNSEEN)\s+(\d+)", re.IGNORECASE)

# SPECIAL-USE (RFC 6154), and Gmail's older XLIST names for the same.
_ROLE_FLAGS: dict[str, FolderRole] = {
    "\\sent": "sent",
    "\\trash": "trash",
    "\\drafts": "drafts",
    "\\junk": "junk",
    "\\archive": "archive",
    "\\all": "all",
    "\\flagged": "flagged",
}
# Where a server sends no attributes, the names clients have settled on.
_ROLE_NAMES: dict[str, FolderRole] = {
    "sent": "sent",
    "sent items": "sent",
    "sent mail": "sent",
    "sent messages": "sent",
    "отправленные": "sent",
    "trash": "trash",
    "deleted": "trash",
    "deleted items": "trash",
    "deleted messages": "trash",
    "bin": "trash",
    "корзина": "trash",
    "удаленные": "trash",
    "удалённые": "trash",
    "drafts": "drafts",
    "черновики": "drafts",
    "junk": "junk",
    "spam": "junk",
    "junk e-mail": "junk",
    "спам": "junk",
    "archive": "archive",
    "архив": "archive",
}

# A Trash made where the server has none (D370).
NEW_TRASH = "Trash"
NEW_DRAFTS = "Drafts"


@dataclass(frozen=True)
class Listed:
    id: str
    flags: frozenset[str]
    delimiter: str | None


def quoted(name: str) -> str:
    """A name as an IMAP quoted string, whatever is in it."""
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ok(status: str, refusal: str) -> None:
    """A command the server said NO or BAD to, as a refusal a person reads."""
    if status != "OK":
        raise MailboxRefused(refusal)


def listed(conn: imaplib.IMAP4) -> list[Listed]:
    status, lines = conn.list()
    ok(status, say("The mail server would not list the folders"))
    found: list[Listed] = []
    pending: bytes | None = None
    for line in lines or []:
        if isinstance(line, tuple):
            # The name came as a literal: the line before it, then the name.
            head, literal = line[0], line[1]
            found.extend(_parsed(head, literal))
            continue
        if not isinstance(line, bytes) or line == b")":
            continue
        pending = line
        found.extend(_parsed(pending, None))
    return found


def _parsed(line: bytes, literal: bytes | None) -> list[Listed]:
    match = _LIST_LINE.match(line.strip())
    if match is None:
        return []
    flags = frozenset(flag.lower() for flag in match.group("flags").decode("ascii", "replace").split())
    raw_delimiter = match.group("delimiter")
    delimiter = None if raw_delimiter.upper() == b"NIL" else _unquoted(raw_delimiter)
    if literal is not None:
        name = literal.decode("utf-8", "replace")
    else:
        raw = match.group("name").strip()
        if raw == b"" or raw.startswith(b"{"):
            return []
        name = _unquoted(raw)
    return [Listed(id=name, flags=flags, delimiter=delimiter)]


def _unquoted(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return re.sub(r"\\(.)", r"\1", text[1:-1])
    return text


def role_of(one: Listed) -> FolderRole | None:
    if one.id.upper() == "INBOX":
        return "inbox"
    for flag in one.flags:
        if flag in _ROLE_FLAGS:
            return _ROLE_FLAGS[flag]
    leaf = utf7.decode(one.id)
    if one.delimiter:
        leaf = leaf.rsplit(one.delimiter, 1)[-1]
    return _ROLE_NAMES.get(leaf.strip().lower())


def selectable(one: Listed) -> bool:
    return "\\noselect" not in one.flags and "\\nonexistent" not in one.flags


def folders(conn: imaplib.IMAP4) -> list[MailFolder]:
    """Every folder with its counts, read in the session that listed them."""
    result: list[MailFolder] = []
    for one in listed(conn):
        messages: int | None = None
        unseen: int | None = None
        if selectable(one):
            status, data = conn.status(quoted(one.id), "(MESSAGES UNSEEN)")
            if status == "OK" and data and isinstance(data[0], bytes):
                counts = {key.upper(): int(value) for key, value in _STATUS.findall(data[0])}
                messages = counts.get(b"MESSAGES")
                unseen = counts.get(b"UNSEEN")
        result.append(
            MailFolder(
                id=one.id,
                name="INBOX" if one.id.upper() == "INBOX" else utf7.decode(one.id),
                delimiter=one.delimiter,
                role=role_of(one),
                selectable=selectable(one),
                messages=messages,
                unseen=unseen,
            )
        )
    return sorted(result, key=_order)


_ROLE_ORDER: dict[FolderRole | None, int] = {
    "inbox": 0,
    "drafts": 1,
    "sent": 2,
    "archive": 3,
    "junk": 4,
    "trash": 5,
}


def _order(folder: MailFolder) -> tuple[int, str]:
    return (_ROLE_ORDER.get(folder.role, 6), folder.name.lower())


def checked(conn: imaplib.IMAP4, folder: str) -> Listed:
    """A folder named by a client, as the server lists it, or a refusal.

    Checked before it is selected, as a column name is checked against the
    relation's columns (ENGINEERING.md).
    """
    for one in listed(conn):
        if one.id == folder and selectable(one):
            return one
    raise MailboxRefused(say("There is no folder {folder} in this mailbox", folder=folder), status=404)


def with_role(conn: imaplib.IMAP4, role: FolderRole) -> str | None:
    for one in listed(conn):
        if selectable(one) and role_of(one) == role:
            return one.id
    return None


def select(conn: imaplib.IMAP4, folder: str, *, readonly: bool) -> int:
    """Open a checked folder; how many messages it holds."""
    checked(conn, folder)
    status, data = conn.select(quoted(folder), readonly=readonly)
    ok(status, say("The mail server would not open the folder"))
    try:
        return int(data[0]) if data and isinstance(data[0], bytes) else 0
    except ValueError:
        return 0


def trash(conn: imaplib.IMAP4) -> str:
    """The Trash, made if the server has none, as other clients do (D370)."""
    found = with_role(conn, "trash")
    if found is not None:
        return found
    status, _ = conn.create(quoted(NEW_TRASH))
    ok(status, say("The mail server would not make a Trash folder"))
    return NEW_TRASH


def drafts(conn: imaplib.IMAP4) -> str:
    """Drafts, made if the server has none, as Trash is (D375)."""
    found = with_role(conn, "drafts")
    if found is not None:
        return found
    status, _ = conn.create(quoted(NEW_DRAFTS))
    ok(status, say("The mail server would not make a Drafts folder"))
    return NEW_DRAFTS

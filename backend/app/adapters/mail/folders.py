"""A mailbox's folders: what LIST says, what each is for, and its counts (D368)."""

import imaplib
import re
import weakref
from dataclasses import dataclass
from typing import Any, Protocol, cast

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
# `"Sent Items" (MESSAGES 12 UNSEEN 3)`; the name may also be an atom.
_STATUS_LINE = re.compile(rb'^\s*(?P<name>"(?:[^"\\]|\\.)*"|[^\s(]+)\s*\((?P<items>[^)]*)\)')

# What LIST said, kept for the rest of one operation and forgotten at the start
# of the next (D368): a session is kept between requests, a folder list is not,
# so one made or removed by another client is seen on the next request.
_LISTED: weakref.WeakKeyDictionary[imaplib.IMAP4, list[Listed]] = weakref.WeakKeyDictionary()

Counts = dict[str, tuple[int | None, int | None]]

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


def forget(conn: imaplib.IMAP4) -> None:
    """The next `listed` asks the server again."""
    _LISTED.pop(conn, None)


def listed(conn: imaplib.IMAP4) -> list[Listed]:
    known = _LISTED.get(conn)
    if known is not None:
        return known
    status, lines = conn.list()
    ok(status, say("The mail server would not list the folders"))
    found = _list_lines(lines)
    _LISTED[conn] = found
    return found


def _list_lines(lines: list[Any] | None) -> list[Listed]:
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
    """Every folder with its counts, in one round trip or two rather than one a folder.

    A STATUS waited for in turn costs a round trip a folder: fifteen of Gmail's
    took three seconds of four (D368).
    """
    counted = _listed_with_counts(conn)
    if counted is None:
        found = listed(conn)
        counts = _pipelined_status(conn, [one.id for one in found if selectable(one)])
    else:
        found, counts = counted
    result: list[MailFolder] = []
    for one in found:
        messages, unseen = counts.get(one.id, (None, None)) if selectable(one) else (None, None)
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


def _capabilities(conn: imaplib.IMAP4) -> set[str]:
    return {str(one).upper() for one in conn.capabilities}


def _listed_with_counts(conn: imaplib.IMAP4) -> tuple[list[Listed], Counts] | None:
    """LIST-STATUS (RFC 5819): the folders and their counts in one command.

    None where the server does not offer it or turns the command down.
    """
    capabilities = _capabilities(conn)
    if "LIST-STATUS" not in capabilities:
        return None
    # A server may send SPECIAL-USE attributes only when asked (RFC 6154).
    returns = (
        "(SPECIAL-USE STATUS (MESSAGES UNSEEN))"
        if "SPECIAL-USE" in capabilities
        else "(STATUS (MESSAGES UNSEEN))"
    )
    conn.untagged_responses.pop("LIST", None)
    conn.untagged_responses.pop("STATUS", None)
    try:
        status, _ = conn.xatom("LIST", '""', '"*"', "RETURN", returns)
    except imaplib.IMAP4.abort:
        raise
    except imaplib.IMAP4.error:
        return None
    lines = conn.untagged_responses.pop("LIST", [])
    statuses = conn.untagged_responses.pop("STATUS", [])
    if status != "OK":
        return None
    found = _list_lines(lines)
    _LISTED[conn] = found
    return found, statuses_of(statuses)


class _Pipelined(Protocol):
    def _command(self, name: str, *args: str) -> bytes: ...
    def _command_complete(self, name: str, tag: bytes) -> tuple[str, list[Any]]: ...


def _pipelined_status(conn: imaplib.IMAP4, ids: list[str]) -> Counts:
    """Every STATUS sent before the first answer is read (RFC 3501, 5.5).

    imaplib waits for each command's answer and has no public way not to, so
    its own two halves of a command are called apart.
    """
    if not ids:
        return {}
    raw = cast(_Pipelined, conn)
    conn.untagged_responses.pop("STATUS", None)
    tags = [raw._command("STATUS", quoted(one), "(MESSAGES UNSEEN)") for one in ids]
    for tag in tags:
        try:
            raw._command_complete("STATUS", tag)
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            # BAD for one folder leaves its counts unknown and the rest read.
            continue
    return statuses_of(conn.untagged_responses.pop("STATUS", []))


def statuses_of(items: list[Any]) -> Counts:
    """Untagged STATUS answers by folder; a name may come as a literal."""
    counts: Counts = {}
    pending: str | None = None
    for item in items:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
            pending = item[1].decode("utf-8", "replace")
            continue
        if not isinstance(item, bytes):
            continue
        if pending is not None:
            name, numbers, pending = pending, item, None
        else:
            match = _STATUS_LINE.match(item)
            if match is None:
                continue
            name, numbers = _unquoted(match.group("name")), match.group("items")
        found = {key.upper(): int(value) for key, value in _STATUS.findall(numbers)}
        counts[name] = (found.get(b"MESSAGES"), found.get(b"UNSEEN"))
    return counts


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
    inbox = folder.upper() == "INBOX"
    for one in listed(conn):
        # INBOX is the one name IMAP compares without case (RFC 3501, 5.1).
        named = one.id == folder or (inbox and one.id.upper() == "INBOX")
        if named and selectable(one):
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
    forget(conn)
    ok(status, say("The mail server would not make a Trash folder"))
    return NEW_TRASH


def drafts(conn: imaplib.IMAP4) -> str:
    """Drafts, made if the server has none, as Trash is (D375)."""
    found = with_role(conn, "drafts")
    if found is not None:
        return found
    status, _ = conn.create(quoted(NEW_DRAFTS))
    forget(conn)
    ok(status, say("The mail server would not make a Drafts folder"))
    return NEW_DRAFTS

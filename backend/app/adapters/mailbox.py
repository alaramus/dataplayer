"""A mailbox, read and written as a mail client does (D366).

What a screen asks of a mailbox, and nothing about how it is reached: IMAP and
SMTP are one driver of this capability, and another way to a mailbox would be
another. A mailbox has no catalog and no rows, so nothing here borrows their
models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# What a folder is for, where the server or its name says so.
FolderRole = Literal["inbox", "sent", "drafts", "trash", "junk", "archive", "all", "flagged"]

# A page of headings is never longer than this (D368).
MAX_PAGE = 100
DEFAULT_PAGE = 50
# A message above this is refused rather than read whole (D368).
MAX_MESSAGE_BYTES = 32 * 1024 * 1024
# Inline images handed over with a message, together (D368).
MAX_INLINE_BYTES = 2 * 1024 * 1024
# What a new letter may carry in attachments, together (D370).
MAX_OUTGOING_BYTES = 25 * 1024 * 1024
MAX_RECIPIENTS = 100

# Not pydantic's EmailStr: it refuses special-use domains such as `.local`,
# which is what a mail server inside a company's network is often called.
Address = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=320, pattern=r"^[^@\s<>,;]+@[^@\s<>,;]+$")
]


class MailFolder(BaseModel):
    # The server's own name, which is what every request names it by.
    id: str
    # Readable, with the hierarchy's separator kept.
    name: str
    delimiter: str | None
    role: FolderRole | None
    # A folder that only holds others cannot be opened.
    selectable: bool
    messages: int | None
    unseen: int | None


class MailAddress(BaseModel):
    name: str
    address: str


class MessageHeading(BaseModel):
    uid: int
    subject: str
    sender: MailAddress | None
    to: list[MailAddress]
    date: datetime | None
    seen: bool
    flagged: bool
    answered: bool
    size: int
    # Read off the top part's type, without the structure: a letter in
    # multipart/mixed almost always carries a file.
    has_attachments: bool


class MessageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str = Field(min_length=1, max_length=1000)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=DEFAULT_PAGE, ge=1, le=MAX_PAGE)
    # Words looked for in the sender, the subject and the text; never syntax.
    search: str | None = Field(default=None, max_length=200)


class MessagePage(BaseModel):
    folder: str
    # Every message the page is a part of: the folder, or what was found.
    total: int
    offset: int
    messages: list[MessageHeading]


class MailAttachment(BaseModel):
    # Where it is in the message, which is how its bytes are asked for.
    part: str
    filename: str
    media_type: str
    size: int
    content_id: str | None


class MailMessage(BaseModel):
    folder: str
    uid: int
    subject: str
    sender: MailAddress | None
    to: list[MailAddress]
    cc: list[MailAddress]
    # Only a draft carries one: a sent letter never names its Bcc (D375).
    bcc: list[MailAddress] = Field(default_factory=list)
    reply_to: list[MailAddress]
    date: datetime | None
    message_id: str | None
    flagged: bool
    answered: bool
    # Flagged `\Draft`, or lying in Drafts: it opens to be finished (D375).
    draft: bool = False
    text: str | None
    # As the sender wrote it; sanitised where it is drawn (D369).
    html: str | None
    # `data:` URIs by Content-ID, for the `cid:` references of the HTML.
    inline_images: dict[str, str]
    attachments: list[MailAttachment]


class MessageRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str = Field(min_length=1, max_length=1000)
    uid: int = Field(ge=1)


class MessageSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str = Field(min_length=1, max_length=1000)
    uids: list[int] = Field(min_length=1, max_length=MAX_PAGE)


class MarkRequest(MessageSelection):
    seen: bool


class MessagesDeleted(BaseModel):
    # The folder they went to, or None when they are gone for good.
    moved_to: str | None
    count: int


class MoveRequest(MessageSelection):
    target: str = Field(min_length=1, max_length=1000)


class MessagesMoved(BaseModel):
    moved_to: str
    count: int


# The most files from the owner's folder one letter names (D374).
MAX_STORED_FILES = 20


class OutgoingMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Empty for a draft; a letter being sent needs one (D375).
    to: list[Address] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    cc: list[Address] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    bcc: list[Address] = Field(default_factory=list, max_length=MAX_RECIPIENTS)
    subject: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=1_000_000)
    # The letter this one answers or forwards; its headers and, for a
    # forward, its attachments are read by the server (D370).
    reply_to: MessageRef | None = None
    forward_of: MessageRef | None = None
    # The draft this letter replaces: its attachments are carried, and it is
    # deleted once this one is sent or saved (D375).
    draft_of: MessageRef | None = None
    # Which parts of `forward_of` or `draft_of` go along; None is all of them.
    keep_parts: list[str] | None = Field(default=None, max_length=100)
    # Files of the owner's own folder, by their path in it (D374).
    stored_files: list[str] = Field(default_factory=list, max_length=MAX_STORED_FILES)


@dataclass(frozen=True)
class OutgoingFile:
    filename: str
    media_type: str
    body: bytes


class MessageSent(BaseModel):
    # Whether a copy went into the Sent folder (D370).
    kept_copy: bool


class DraftSaved(BaseModel):
    folder: str
    # The new draft's UID, where the server says it (UIDPLUS).
    uid: int | None


class InboxMark(BaseModel):
    """Where an inbox was: a UID means nothing once UIDVALIDITY changes (D372)."""

    uidvalidity: int
    uidnext: int


class Arrivals(BaseModel):
    mark: InboxMark
    unseen: int
    # Letters that arrived since the mark asked about; none on a first look.
    count: int
    newest: list[MessageHeading]


@dataclass(frozen=True)
class AttachmentBytes:
    filename: str
    media_type: str
    body: bytes


class MailboxRefused(Exception):
    """The server's answer to a request it will not do, worded for a person.

    Not an `AdapterError`: the mailbox was reached and said no — a folder that
    is not there, a message gone, a letter too large — and that is a 4xx.
    """

    def __init__(self, message: str, *, status: Literal[404, 409, 413, 422] = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@runtime_checkable
class SupportsMailbox(Protocol):
    """A mailbox: its folders, its messages, writing one and putting one away."""

    def mailbox_address(self) -> str: ...

    async def mail_folders(self) -> list[MailFolder]: ...

    async def mail_messages(self, query: MessageQuery) -> MessagePage: ...

    async def mail_message(self, ref: MessageRef) -> MailMessage: ...

    async def mail_attachment(self, ref: MessageRef, part: str) -> AttachmentBytes: ...

    async def mark_messages(self, request: MarkRequest) -> None: ...

    async def delete_messages(self, selection: MessageSelection) -> MessagesDeleted: ...

    async def send_message(
        self, message: OutgoingMessage, files: list[OutgoingFile]
    ) -> MessageSent: ...

    async def save_draft(
        self, message: OutgoingMessage, files: list[OutgoingFile]
    ) -> DraftSaved: ...

    async def move_messages(self, request: MoveRequest) -> MessagesMoved: ...

    async def inbox_arrivals(self, since: InboxMark | None) -> Arrivals: ...

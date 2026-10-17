"""Files a person sends with a message: what is taken, and how the model sees it (D142).

Two kinds only. An image is told by its first bytes, never by the type the
browser claims or the name it was given; anything else must read as UTF-8
text. What is neither is refused in words, before a run exists.
"""

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from fastapi import UploadFile

from app.ai.models import AttachmentKind, AttachmentRules
from app.core.translation import say

MAX_FILES = 5
# The strictest provider's ceiling for one image (Anthropic's); a larger one
# would be accepted here and refused by the model mid-run.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# About sixty thousand tokens of text, room left in the smallest window.
MAX_TEXT_BYTES = 256 * 1024
# Every file of one message together; a request larger than this is refused
# by some providers whole.
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_NAME_CHARS = 255

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")

RULES = AttachmentRules(
    max_files=MAX_FILES,
    max_image_bytes=MAX_IMAGE_BYTES,
    max_text_bytes=MAX_TEXT_BYTES,
    max_total_bytes=MAX_TOTAL_BYTES,
    image_types=list(IMAGE_TYPES),
)


class AttachmentRefused(Exception):
    """A file this chat does not take, and the sentence that says why."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class NewAttachment:
    name: str
    kind: AttachmentKind
    media_type: str
    content: bytes


def image_type(data: bytes) -> str | None:
    """The image a file is, by its signature, or None."""
    for signature, media_type in _SIGNATURES:
        if data.startswith(signature):
            return media_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def file_name(raw: str | None) -> str:
    """The last segment of the name the browser sent, by the rules of both
    platforms: a name is shown and sent to the model, never used as a path."""
    name = PureWindowsPath(PurePosixPath(raw or "").name).name.strip()
    return name[:MAX_NAME_CHARS] or "attachment"


def _reads_as_text(data: bytes) -> bool:
    # A NUL decodes as UTF-8 and marks a binary file all the same.
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return True


def _size(count: int) -> str:
    if count >= 1024 * 1024:
        return say("{count} MB", count=count // (1024 * 1024))
    return say("{count} KB", count=count // 1024)


def accept(raw_name: str | None, data: bytes) -> NewAttachment:
    """One file as this chat takes it, or the sentence refusing it."""
    name = file_name(raw_name)
    media_type = image_type(data)
    if media_type is not None:
        if len(data) > MAX_IMAGE_BYTES:
            raise AttachmentRefused(
                say("{name} is larger than {size}", name=name, size=_size(MAX_IMAGE_BYTES))
            )
        return NewAttachment(name, "image", media_type, data)
    if len(data) > MAX_TEXT_BYTES:
        raise AttachmentRefused(
            say("{name} is larger than {size} of text", name=name, size=_size(MAX_TEXT_BYTES))
        )
    if not _reads_as_text(data):
        raise AttachmentRefused(
            say("{name} is neither text nor a PNG, JPEG, WebP or GIF image", name=name)
        )
    return NewAttachment(name, "text", "text/plain", data)


async def read_uploads(files: Sequence[UploadFile]) -> list[NewAttachment]:
    """Every file of one message, each read no further than the largest a file
    may be, so a huge one is refused without being held whole."""
    if len(files) > MAX_FILES:
        raise AttachmentRefused(say("A message carries at most {count} files", count=MAX_FILES))
    accepted: list[NewAttachment] = []
    total = 0
    for upload in files:
        data = await upload.read(max(MAX_IMAGE_BYTES, MAX_TEXT_BYTES) + 1)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise AttachmentRefused(
                say(
                    "The files of one message come to more than {size}",
                    size=_size(MAX_TOTAL_BYTES),
                )
            )
        accepted.append(accept(upload.filename, data))
    return accepted


def model_content(text: str, attachments: Sequence[NewAttachment]) -> str | list[Any]:
    """The message as the model is given it.

    A text file travels inside the text, fenced and named, so every provider
    reads it the same way; an image travels beside it as the standard image
    block each provider's integration translates. With nothing attached the
    message stays the plain string it always was.
    """
    if not attachments:
        return text
    parts = [text] if text else []
    for one in attachments:
        if one.kind == "text":
            body = one.content.decode("utf-8-sig")
            parts.append(f"Attached file {json.dumps(one.name, ensure_ascii=False)}:\n<file>\n{body}\n</file>")
    blocks: list[Any] = [{"type": "text", "text": "\n\n".join(parts)}] if parts else []
    blocks += [
        {
            "type": "image",
            "base64": base64.b64encode(one.content).decode(),
            "mime_type": one.media_type,
        }
        for one in attachments
        if one.kind == "image"
    ]
    return blocks

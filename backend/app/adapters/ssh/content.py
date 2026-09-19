"""Reading a remote file as the text it is made of, and writing it back (D48).

A viewer's page and an editor's document are two reads with two ceilings, as
the file source has them. Writing back is the editor's contract: the document
is replaced only while it is still the version that was read, so two people
editing one file on a server cannot silently undo each other.
"""

import hashlib
import posixpath

import asyncssh

from app.adapters.content import (
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    MarkdownContent,
    TextContent,
    UpdateContentRequest,
)
from app.adapters.file.formats import format_of
from app.adapters.ssh.catalog import representations_of
from app.adapters.ssh.session import Remote, SshSession

# The ceilings the file source reads text, documents and editable source
# under, for the same reasons: a viewer is for reading, and a log of a
# gigabyte is downloaded.
MAX_TEXT_BYTES = 256 * 1024
MAX_MARKDOWN_BYTES = 1024 * 1024
MAX_EDITOR_BYTES = 4 * 1024 * 1024

# How much of the start is looked at to tell text from something that is not.
_SNIFF_BYTES = 8192


class SshContent:
    def __init__(self, session: SshSession) -> None:
        self._session = session

    async def read_content(self, request: ContentRequest) -> ContentResult:
        name = _named(request.node_id)
        offered = {representation.kind for representation in representations_of(name)}
        if request.representation not in offered:
            raise ValueError(f"{name} cannot be opened as {request.representation}")
        ceiling = MAX_MARKDOWN_BYTES if request.representation == "markdown" else MAX_TEXT_BYTES
        async with self._session.remote() as remote:
            data = await _read(remote, request.node_id, ceiling + 1)
        truncated = len(data) > ceiling
        text = data[:ceiling].decode("utf-8", errors="replace")
        notice = (
            "This file does not look like text; what could not be read as text is replaced"
            if _binary(data)
            else None
        )
        if request.representation == "markdown":
            return MarkdownContent(text=text, truncated=truncated, notice=notice)
        return TextContent(text=text, truncated=truncated, notice=notice)

    async def read_editor_content(self, request: EditorContentRequest) -> EditorContent:
        """The source of one file and the version a save must still match.

        Shown and not saved when it cannot be written back whole: past the
        ceiling, not UTF-8, or binary — the file source's three refusals.
        """
        name = _named(request.node_id)
        if not representations_of(name):
            raise ValueError(f"{name} cannot be opened as text")
        async with self._session.remote() as remote:
            data = await _read(remote, request.node_id, MAX_EDITOR_BYTES + 1)
        language = _language(name)
        if len(data) > MAX_EDITOR_BYTES:
            return EditorContent(
                text=data[:MAX_EDITOR_BYTES].decode("utf-8", errors="replace"),
                filename=name,
                language_hint=language,
                writable=False,
                truncated=True,
                reason=(
                    f"Files larger than {MAX_EDITOR_BYTES // (1024 * 1024)} MB "
                    "are shown as a preview and cannot be edited here."
                ),
            )
        if _binary(data):
            return EditorContent(
                text=data.decode("utf-8", errors="replace"),
                filename=name,
                language_hint=language,
                writable=False,
                reason="This file contains binary data and cannot be edited as text.",
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as failure:
            return EditorContent(
                text=data.decode("utf-8", errors="replace"),
                filename=name,
                language_hint=language,
                writable=False,
                reason=f"This file is not valid UTF-8 at byte {failure.start + 1}.",
            )
        return EditorContent(
            text=text,
            filename=name,
            language_hint=language,
            version=_version(data),
            writable=True,
        )

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        """Replace the file while it is still the version that was read.

        Written beside it and moved into place, with the file's own permissions
        carried over first, so a script keeps being executable and nobody
        reading the folder sees half a file.
        """
        replacement = request.text.encode("utf-8")
        if len(replacement) > MAX_EDITOR_BYTES:
            raise ValueError(
                f"The edited content is larger than {MAX_EDITOR_BYTES // (1024 * 1024)} MB"
            )
        async with self._session.remote() as remote:
            path = remote.path_of(request.node_id)
            current = await _read(remote, request.node_id, MAX_EDITOR_BYTES + 1)
            if len(current) > MAX_EDITOR_BYTES or _binary(current):
                raise ValueError("This file cannot be edited as text")
            if _version(current) != request.version:
                raise ContentConflict
            attrs = await remote.sftp.stat(path)
            temporary = posixpath.join(
                posixpath.dirname(path), f".edit-{posixpath.basename(path)}"
            )
            try:
                async with remote.sftp.open(temporary, "wb", encoding=None) as handle:
                    await handle.write(replacement)
                if attrs.permissions is not None:
                    await remote.sftp.chmod(temporary, attrs.permissions & 0o7777)
                await remote.sftp.posix_rename(temporary, path)
            except BaseException:
                try:
                    await remote.sftp.remove(temporary)
                except asyncssh.SFTPError:
                    pass
                raise
        return ContentUpdated(version=_version(replacement))


async def _read(remote: Remote, node_id: str, size: int) -> bytes:
    try:
        async with remote.sftp.open(remote.path_of(node_id), "rb", encoding=None) as handle:
            raw = await handle.read(size)
    except asyncssh.SFTPNoSuchFile:
        raise ValueError(f"No such file: {node_id}") from None
    return raw if isinstance(raw, bytes) else raw.encode()


def _named(node_id: str) -> str:
    return node_id.rsplit("/", 1)[-1]


def _binary(data: bytes) -> bool:
    return b"\x00" in data[:_SNIFF_BYTES]


def _version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _language(name: str) -> str | None:
    """What the editor highlights, by the name. Nothing is validated on a
    server this application does not own."""
    return {"json": "json", "jsonl": "json", "markdown": "markdown"}.get(format_of(name))

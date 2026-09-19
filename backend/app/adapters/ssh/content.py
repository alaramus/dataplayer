"""Reading a remote file as the text it is made of, a bounded page of it."""

import asyncssh

from app.adapters.content import ContentRequest, ContentResult, MarkdownContent, TextContent
from app.adapters.ssh.catalog import representations_of
from app.adapters.ssh.session import SshSession

# The ceilings the file source reads text and documents under, for the same
# reasons: a viewer is for reading, and a log of a gigabyte is downloaded.
MAX_TEXT_BYTES = 256 * 1024
MAX_MARKDOWN_BYTES = 1024 * 1024

# How much of the start is looked at to tell text from something that is not.
_SNIFF_BYTES = 8192


class SshContent:
    def __init__(self, session: SshSession) -> None:
        self._session = session

    async def read_content(self, request: ContentRequest) -> ContentResult:
        name = request.node_id.rsplit("/", 1)[-1]
        offered = {representation.kind for representation in representations_of(name)}
        if request.representation not in offered:
            raise ValueError(f"{name} cannot be opened as {request.representation}")
        ceiling = MAX_MARKDOWN_BYTES if request.representation == "markdown" else MAX_TEXT_BYTES
        async with self._session.remote() as remote:
            path = remote.path_of(request.node_id)
            try:
                async with remote.sftp.open(path, "rb", encoding=None) as handle:
                    # One byte past the ceiling says whether there was more.
                    raw = await handle.read(ceiling + 1)
            except asyncssh.SFTPNoSuchFile:
                raise ValueError(f"No such file: {request.node_id}") from None
        data = raw if isinstance(raw, bytes) else raw.encode()
        truncated = len(data) > ceiling
        text = data[:ceiling].decode("utf-8", errors="replace")
        notice = (
            "This file does not look like text; what could not be read as text is replaced"
            if b"\x00" in data[:_SNIFF_BYTES]
            else None
        )
        if request.representation == "markdown":
            return MarkdownContent(text=text, truncated=truncated, notice=notice)
        return TextContent(text=text, truncated=truncated, notice=notice)

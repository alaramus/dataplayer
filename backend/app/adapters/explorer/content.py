"""Bounded native content viewers for files.

Every viewer here decides from a header or a bounded prefix, so each reads the
file through the storage's own ranged `open` rather than a local copy: a
recording, a picture or a log on a remote storage is asked for what is read
and no more, whatever it weighs (D152). Only an archive entry is read from a
file on this machine, because the archive it is expanded out of is (D53).
"""

import hashlib
import io
import os
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from functools import partial
from json import JSONDecodeError
from pathlib import Path
from typing import BinaryIO, assert_never

from anyio import to_thread
from PIL import Image, UnidentifiedImageError

from app.adapters import jsontext
from app.adapters.content import (
    AudioContent,
    BoundedContentPreview,
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentStream,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    EditorValidationKind,
    ImageContent,
    ImageMediaType,
    JsonContent,
    JsonLine,
    JsonLinesContent,
    MarkdownContent,
    PdfContent,
    TextContent,
    UpdateContentRequest,
    VideoContent,
    database_reader,
    json_tree,
)
from app.adapters.explorer import archive
from app.adapters.explorer.binary import bytes_look_binary
from app.adapters.explorer.formats import (
    format_of,
    offers_source,
    representations_inside_archive,
    representations_of,
)
from app.adapters.explorer.media import audio_facts, pdf_facts, video_facts
from app.adapters.explorer.members import ResolvedNode, resolve_node
from app.adapters.explorer.storage import Place, Storage
from app.core.translation import N_, say

# A text viewer is a preview, not a download. Keeping the source path separate
# lets a later download stream the original bytes without raising this bound.
MAX_TEXT_BYTES = 256 * 1024

# A whole JSON document has no honest partial tree, so it is parsed only below
# this ceiling. Above it the JSON viewer keeps its identity and shows a bounded
# source preview with the reason instead.
MAX_JSON_BYTES = 4 * 1024 * 1024

# JSONL is independently readable by line. One pathological line must not turn
# that property back into an unbounded allocation.
MAX_JSON_LINE_BYTES = 1024 * 1024

# A record count alone does not bound a page when every record may be large.
MAX_JSON_LINES_PAGE_BYTES = 4 * 1024 * 1024

# Editing is a whole-document operation: both the source shown to the user and
# the replacement have to fit this ceiling. Larger files keep their bounded
# viewer and name why the editor cannot write them.
MAX_EDITOR_BYTES = 4 * 1024 * 1024

# Preview is allowed to hold its verified bytes, but only below this independent
# transport bound. Pixel count separately bounds browser decode memory.
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# Between the text preview and the editor: a rendered document is parsed,
# tokenised and turned into DOM in the browser, which neither of those is.
MAX_MARKDOWN_BYTES = 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

# What a ranged read hands over at a time. A stream has no size ceiling — it is
# ranged and chunked, so what is held is one of these (D52).
STREAM_CHUNK_BYTES = 256 * 1024

IMAGE_MEDIA_TYPES: dict[str, ImageMediaType] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}


@dataclass(frozen=True)
class _Source:
    """A file's bytes wherever they are, and what is known without reading them."""

    name: str
    exists: bool
    is_directory: bool
    size_bytes: int
    opened: Callable[[], BinaryIO]


def _in_storage(storage: Storage, place: Place) -> _Source:
    found = storage.entry(place)
    return _Source(
        name=place.name,
        exists=found is not None,
        is_directory=found is not None and found.is_directory,
        size_bytes=0 if found is None else found.size_bytes,
        opened=partial(storage.open, place),
    )


def _on_disk(path: Path, name: str) -> _Source:
    """An archive entry, expanded into a temporary file whose own name says
    nothing about it (D53)."""
    return _Source(
        name=name,
        exists=path.exists(),
        is_directory=path.is_dir(),
        size_bytes=path.stat().st_size if path.is_file() else 0,
        opened=lambda: path.open("rb"),
    )


class ExplorerContent:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def read_content(self, request: ContentRequest) -> ContentResult:
        return await to_thread.run_sync(self._read_node, request)

    def _read_node(self, request: ContentRequest) -> ContentResult:
        """One representation, whether the node is a file or inside one."""
        entry = _archive_entry(self._storage, request.node_id)
        if entry is None:
            place = self._file_place(request.node_id)
            if request.representation == "database":
                return self._read_database(place, request)
            return self._read(_in_storage(self._storage, place), request)
        # An entry is expanded into a bounded temporary file and read by the
        # ordinary viewer, which is what lets every one of them work inside an
        # archive without a second implementation (D53).
        name = entry.member or ""
        if request.representation not in {
            item.kind for item in representations_inside_archive(name)
        }:
            raise ValueError(
                say(
                    'This entry does not offer the "{representation}" representation',
                    representation=request.representation,
                )
            )
        with (
            self._storage.local_file(entry.place) as container,
            archive.expanded(container, name) as expanded,
        ):
            return self._read(_on_disk(expanded, _entry_name(name)), request)

    def _read_database(self, place: Place, request: ContentRequest) -> ContentResult:
        """A database file's tables, read from a path SQLite can open: the
        file itself, or the bounded local copy of a remote one (D152, D262)."""
        source = _in_storage(self._storage, place)
        if not source.exists or source.is_directory:
            raise ValueError(say("No such file: {node_id}", node_id=request.node_id))
        if "database" not in {item.kind for item in representations_of(source.name)}:
            raise ValueError(
                say('This file does not offer the "{representation}" representation', representation="database")
            )
        reader = database_reader("sqlite")
        if reader is None:
            raise ValueError(say("This server cannot read database files"))
        with self._storage.local_file(place) as local:
            return reader(local)

    def _file_place(self, node_id: str) -> Place:
        """The place of a node that is a file or a folder, never a member.

        A sheet of a workbook has no bytes of its own to open, and is no file.
        """
        resolved = resolve_node(self._storage, node_id)
        if resolved.member is not None:
            raise ValueError(say("No such file: {node_id}", node_id=node_id))
        return resolved.place

    async def read_editor_content(
        self, request: EditorContentRequest
    ) -> EditorContent:
        return await to_thread.run_sync(self._editor_for, request)

    def _editor_for(self, request: EditorContentRequest) -> EditorContent:
        """The source of one document, whether it is a file or inside one.

        An entry is shown and never saved: the document is read, and the same
        `writable` flag that carries "this file is too large" or "you may only
        read this connection" carries the reason (D48, D53). Refusing to show
        it at all would take the reading away with the writing.
        """
        entry = _archive_entry(self._storage, request.node_id)
        if entry is None:
            place = self._file_place(request.node_id)
            return self._read_editor(_in_storage(self._storage, place), request)
        member = entry.member or ""
        with (
            self._storage.local_file(entry.place) as container,
            archive.expanded(container, member) as expanded,
        ):
            document = self._read_editor(
                _on_disk(expanded, _entry_name(member)), request
            )
        return document.model_copy(
            update={
                "writable": False,
                "version": None,
                "reason": say("A file inside an archive cannot be edited here"),
            }
        )

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        return await to_thread.run_sync(self._update, request)

    async def preview_content(
        self, request: ContentRequest
    ) -> BoundedContentPreview:
        return await to_thread.run_sync(self._preview, request)

    def _preview(self, request: ContentRequest) -> BoundedContentPreview:
        entry = _archive_entry(self._storage, request.node_id)
        if entry is None:
            place = self._file_place(request.node_id)
            return self._read_image_preview(_in_storage(self._storage, place), request)
        name = entry.member or ""
        with (
            self._storage.local_file(entry.place) as container,
            archive.expanded(container, name) as expanded,
        ):
            return self._read_image_preview(
                _on_disk(expanded, _entry_name(name)), request
            )

    def _read(self, source: _Source, request: ContentRequest) -> ContentResult:
        if not source.exists:
            raise ValueError(say("No such file: {node_id}", node_id=request.node_id))
        if source.is_directory:
            raise ValueError(
                say("A directory has no content viewer: {node_id}", node_id=request.node_id)
            )

        # The name decides the viewer, never the bytes.
        available = {item.kind for item in representations_of(source.name)}
        if request.representation not in available:
            raise ValueError(
                say(
                    'This file does not offer the "{representation}" representation',
                    representation=request.representation,
                )
            )

        match request.representation:
            case "text":
                return _read_text(source)
            case "json":
                return _read_json(source)
            case "jsonl":
                return _read_json_lines(source, request.limit, request.offset)
            case "markdown":
                return _read_markdown(source)
            case "image":
                return _image_content(source)
            case "audio":
                return _audio_content(source)
            case "video":
                return _video_content(source)
            case "pdf":
                return _pdf_content(source)
            case "database":
                # Read by `_read_database`, which needs a path rather than a
                # stream; an archive entry offers no database (D53).
                raise ValueError(say('This file does not offer the "{representation}" representation', representation="database"))
            case "sql" | "tree":
                # The catalog guard above makes this unreachable for a file,
                # but the closed content vocabulary includes what sources issue.
                raise ValueError(
                    say(
                        'This file does not offer the "{representation}" representation',
                        representation=request.representation,
                    )
                )
            case unreachable:
                assert_never(unreachable)

    async def open_content_stream(self, request: ContentRequest) -> ContentStream:
        """Bytes a player or a reader takes part of, verified first (D52)."""
        return await to_thread.run_sync(self._open_stream, request)

    def _open_stream(self, request: ContentRequest) -> ContentStream:
        _refuse_inside_archive(
            self._storage,
            request.node_id,
            N_("A file inside an archive cannot be streamed"),
        )
        place = self._file_place(request.node_id)
        # Asked again on every range a player requests: a header costs a few
        # blocks, and the file may have changed since the last one.
        result = self._read(_in_storage(self._storage, place), request)
        if not isinstance(result, AudioContent | VideoContent | PdfContent):
            raise ValueError(
                say(
                    'The "{representation}" representation is not streamed',
                    representation=request.representation,
                )
            )
        return ContentStream(
            media_type=result.media_type,
            filename=result.filename,
            size_bytes=result.size_bytes,
            read=partial(_range_chunks, self._storage, place),
        )

    def _read_image_preview(
        self, source: _Source, request: ContentRequest
    ) -> BoundedContentPreview:
        if not source.exists:
            raise ValueError(say("No such file: {node_id}", node_id=request.node_id))
        if source.is_directory:
            raise ValueError(
                say("A directory has no image viewer: {node_id}", node_id=request.node_id)
            )
        if request.representation != "image" or "image" not in {
            item.kind for item in representations_of(source.name)
        }:
            raise ValueError(say('This file does not offer the "image" representation'))
        _refuse_large_image(source.size_bytes)
        # The whole of it, because the bytes verified are the bytes returned:
        # a file cannot change between checking and rendering (D49).
        raw, truncated = _byte_prefix(source, MAX_IMAGE_BYTES)
        if truncated:
            _refuse_large_image(MAX_IMAGE_BYTES + 1)
        media_type, width, height = _image_facts(io.BytesIO(raw), verify=True)
        return BoundedContentPreview(
            body=raw,
            media_type=media_type,
            filename=source.name,
            width=width,
            height=height,
        )

    def _read_editor(
        self, source: _Source, request: EditorContentRequest
    ) -> EditorContent:
        named = source.name
        _require_editable_file(source, request.node_id)
        language_hint, validation = _editor_language(named)
        raw, truncated = _byte_prefix(source, MAX_EDITOR_BYTES)
        _refuse_binary(
            raw, N_("This file contains binary data and cannot be edited as text")
        )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return EditorContent(
                text=raw.decode("utf-8", errors="replace"),
                filename=named,
                writable=False,
                truncated=truncated,
                reason=say(
                    "This file is not valid UTF-8 at byte {byte}.", byte=exc.start + 1
                ),
                language_hint=language_hint,
                validation=validation,
            )
        if truncated:
            return EditorContent(
                text=text,
                filename=named,
                writable=False,
                truncated=True,
                reason=say(
                    "Files larger than {megabytes} MB "
                    "are shown as a preview and cannot be edited here.",
                    megabytes=MAX_EDITOR_BYTES // (1024 * 1024),
                ),
                language_hint=language_hint,
                validation=validation,
            )
        return EditorContent(
            text=text,
            filename=named,
            version=_version(raw),
            writable=True,
            language_hint=language_hint,
            validation=validation,
        )

    def _update(self, request: UpdateContentRequest) -> ContentUpdated:
        _refuse_inside_archive(
            self._storage,
            request.node_id,
            N_("A file inside an archive cannot be written"),
        )
        place = self._file_place(request.node_id)
        source = _in_storage(self._storage, place)
        _require_editable_file(source, request.node_id)
        current, truncated = (
            (b"", True)
            if source.size_bytes > MAX_EDITOR_BYTES
            else _byte_prefix(source, MAX_EDITOR_BYTES)
        )
        if truncated:
            raise ValueError(
                say(
                    "Files larger than {megabytes} MB cannot be edited here",
                    megabytes=MAX_EDITOR_BYTES // (1024 * 1024),
                )
            )
        _refuse_binary(
            current, N_("This file contains binary data and cannot be edited as text")
        )
        if _version(current) != request.version:
            raise ContentConflict
        try:
            current.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(say("This file is not valid UTF-8 and cannot be edited")) from None

        replacement = request.text.encode("utf-8")
        if len(replacement) > MAX_EDITOR_BYTES:
            raise ValueError(
                say(
                    "The edited content is larger than {megabytes} MB",
                    megabytes=MAX_EDITOR_BYTES // (1024 * 1024),
                )
            )
        _validate_replacement(place.name, request.text)
        with self._storage.staged(place, prefix=".edit-") as staged:
            with staged.open("wb") as handle:
                handle.write(replacement)
                handle.flush()
                os.fsync(handle.fileno())
            # Replaced in one step, keeping the file's own permissions.
            self._storage.publish(staged, place, replace=True)
        return ContentUpdated(version=_version(replacement))


def _audio_content(source: _Source) -> AudioContent:
    with source.opened() as handle:
        facts = audio_facts(source.name, handle)
    return AudioContent(
        filename=source.name,
        media_type=facts.media_type,
        size_bytes=source.size_bytes,
        duration_seconds=facts.duration_seconds,
        channels=facts.channels,
        sample_rate=facts.sample_rate,
    )


def _video_content(source: _Source) -> VideoContent:
    with source.opened() as handle:
        facts = video_facts(source.name, handle)
    return VideoContent(
        filename=source.name,
        media_type=facts.media_type,
        size_bytes=source.size_bytes,
        duration_seconds=facts.duration_seconds,
        width=facts.width,
        height=facts.height,
    )


def _pdf_content(source: _Source) -> PdfContent:
    with source.opened() as handle:
        facts = pdf_facts(source.name, handle)
    return PdfContent(
        filename=source.name,
        size_bytes=source.size_bytes,
        version=facts.version,
    )


async def _range_chunks(
    storage: Storage, place: Place, start: int, end: int
) -> AsyncIterator[bytes]:
    """The inclusive range, in chunks, and never a byte past it.

    Opened per request rather than held open between them: a player asks for
    the end of a file, then the beginning, then a piece in the middle, and each
    of those is its own HTTP request.
    """
    remaining = end - start + 1
    handle = await to_thread.run_sync(storage.open, place)
    try:
        await to_thread.run_sync(handle.seek, start)
        while remaining > 0:
            chunk = await to_thread.run_sync(
                handle.read, min(STREAM_CHUNK_BYTES, remaining)
            )
            if not chunk:
                return
            remaining -= len(chunk)
            yield chunk
    finally:
        await to_thread.run_sync(handle.close)


def _archive_entry(storage: Storage, node_id: str) -> ResolvedNode | None:
    """The node as a member of an archive, or None when it is a file."""
    resolved = resolve_node(storage, node_id)
    if resolved.member is None or format_of(resolved.name) != "archive":
        return None
    return resolved


def _refuse_inside_archive(storage: Storage, node_id: str, refusal: str) -> None:
    """What an archive does not admit, said before anything is opened.

    Editing writes and streaming seeks, and an entry is neither writable nor
    seekable: it is expanded whole or not read at all (D53).
    """
    if _archive_entry(storage, node_id) is not None:
        raise ValueError(say(refusal))


def _entry_name(member: str) -> str:
    return member.rsplit("/", 1)[-1]


def _read_text(source: _Source) -> TextContent:
    raw, truncated = _byte_prefix(source, MAX_TEXT_BYTES)
    _refuse_binary(raw, N_("This file contains binary data and cannot be shown as text"))
    text, notice = _decoded(raw)
    return TextContent(text=text, truncated=truncated, notice=notice)


def _read_markdown(source: _Source) -> MarkdownContent:
    raw, truncated = _byte_prefix(source, MAX_MARKDOWN_BYTES)
    _refuse_binary(raw, N_("This file contains binary data and is not a document"))
    text, notice = _decoded(raw)
    return MarkdownContent(text=text, truncated=truncated, notice=notice)


def _refuse_binary(raw: bytes, refusal: str) -> None:
    if bytes_look_binary(raw):
        raise ValueError(say(refusal))


def _refuse_large_image(size_bytes: int) -> None:
    if size_bytes > MAX_IMAGE_BYTES:
        raise ValueError(
            say(
                "Images larger than {megabytes} MB cannot be previewed",
                megabytes=MAX_IMAGE_BYTES // (1024 * 1024),
            )
        )


def _image_facts(
    stream: BinaryIO, *, verify: bool
) -> tuple[ImageMediaType, int, int]:
    """What an image's header states, and with `verify` that its bytes hold.

    Pillow reads the header on `open` and the rest only when asked, so without
    `verify` this costs a few kilobytes whatever the image weighs.
    """
    try:
        with Image.open(stream) as image:
            media_type = IMAGE_MEDIA_TYPES.get(image.format or "")
            if media_type is None:
                raise ValueError(say("Only PNG and JPEG images can be previewed"))
            width, height = image.size
            if width < 1 or height < 1:
                raise ValueError(say("This image has invalid dimensions"))
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError(say("Animated images are not supported by this viewer yet"))
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    say(
                        "Images larger than {pixels:,} pixels cannot be previewed",
                        pixels=MAX_IMAGE_PIXELS,
                    )
                )
            if verify:
                image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise ValueError(say("This file is not a valid PNG or JPEG image")) from None
    return media_type, width, height


def _image_content(source: _Source) -> ImageContent:
    """What the picture is, from its header: the bytes themselves are verified
    by the preview that returns them (D49)."""
    _refuse_large_image(source.size_bytes)
    with source.opened() as handle:
        media_type, width, height = _image_facts(handle, verify=False)
    return ImageContent(
        filename=source.name,
        media_type=media_type,
        size_bytes=source.size_bytes,
        width=width,
        height=height,
    )


def _read_json(source: _Source) -> JsonContent:
    raw, truncated = (
        (b"", True)
        if source.size_bytes > MAX_JSON_BYTES
        else _byte_prefix(source, MAX_JSON_BYTES)
    )
    if truncated:
        head, head_truncated = _byte_prefix(source, MAX_TEXT_BYTES)
        text, decode_notice = _decoded(head)
        notice = say(
            "This file is larger than {megabytes} MB, "
            "so it was not parsed as one JSON document.",
            megabytes=MAX_JSON_BYTES // (1024 * 1024),
        )
        if decode_notice is not None:
            notice = f"{notice} {decode_notice}"
        return JsonContent(
            source_text=text,
            truncated=head_truncated,
            notice=notice,
        )

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return JsonContent(
            source_text=raw.decode("utf-8", errors="replace"),
            notice=say(
                "This file is not valid UTF-8 at byte {byte}.", byte=exc.start + 1
            ),
        )

    try:
        parsed = jsontext.load(text)
    except JSONDecodeError as exc:
        return JsonContent(
            source_text=text,
            notice=say(
                "This file is not valid JSON ({problem}, line {line} column {column}).",
                problem=exc.msg,
                line=exc.lineno,
                column=exc.colno,
            ),
        )
    except jsontext.NonStandardJson as exc:
        return JsonContent(
            source_text=text,
            notice=say("This file is not valid JSON ({problem}).", problem=exc),
        )
    try:
        return JsonContent(value=json_tree(parsed))
    except RecursionError:
        return JsonContent(
            source_text=text,
            notice=say("This JSON document is too deeply nested to show safely."),
        )


def _read_json_lines(source: _Source, limit: int, offset: int) -> JsonLinesContent:
    items: list[JsonLine] = []
    seen = 0
    page_bytes = 0
    has_more = False
    for line_number, raw, truncated in _bounded_lines(source):
        if not raw.strip():
            continue
        if seen < offset:
            seen += 1
            continue
        if len(items) == limit or (
            items and page_bytes + len(raw) > MAX_JSON_LINES_PAGE_BYTES
        ):
            has_more = True
            break
        items.append(_json_line(line_number, raw, truncated))
        page_bytes += len(raw)
        seen += 1
    return JsonLinesContent(items=items, has_more=has_more, offset=offset)


def _json_line(line_number: int, raw: bytes, truncated: bool) -> JsonLine:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return JsonLine(
            line_number=line_number,
            source_text=raw.decode("utf-8", errors="replace"),
            truncated=truncated,
            notice=say(
                "Line {line} is not valid UTF-8 at byte {byte}.",
                line=line_number,
                byte=exc.start + 1,
            ),
        )
    if truncated:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            truncated=True,
            notice=say(
                "Line {line} is larger than {megabytes} MB and was not parsed.",
                line=line_number,
                megabytes=MAX_JSON_LINE_BYTES // (1024 * 1024),
            ),
        )
    try:
        return JsonLine(line_number=line_number, value=json_tree(jsontext.load(text)))
    except JSONDecodeError as exc:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=say(
                "Line {line} is not valid JSON ({problem}, column {column}).",
                line=line_number,
                problem=exc.msg,
                column=exc.colno,
            ),
        )
    except jsontext.NonStandardJson as exc:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=say(
                "Line {line} is not valid JSON ({problem}).", line=line_number, problem=exc
            ),
        )
    except RecursionError:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=say(
                "Line {line} is too deeply nested to show safely.", line=line_number
            ),
        )


def _bounded_lines(source: _Source) -> Iterator[tuple[int, bytes, bool]]:
    """Physical lines without an unbounded ``readline`` allocation."""
    with source.opened() as handle:
        line_number = 0
        while True:
            first = handle.readline(MAX_JSON_LINE_BYTES + 1)
            if first == b"":
                return
            line_number += 1
            truncated = len(first) > MAX_JSON_LINE_BYTES and not first.endswith(b"\n")
            raw = first[:MAX_JSON_LINE_BYTES]
            if truncated:
                while True:
                    rest = handle.readline(MAX_JSON_LINE_BYTES + 1)
                    if rest == b"" or rest.endswith(b"\n"):
                        break
            yield line_number, raw.rstrip(b"\r\n"), truncated


def _decoded(raw: bytes) -> tuple[str, str | None]:
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return (
            raw.decode("utf-8", errors="replace"),
            say("This file is not valid UTF-8 at byte {byte}.", byte=exc.start + 1),
        )


def _byte_prefix(source: _Source, ceiling: int) -> tuple[bytes, bool]:
    with source.opened() as handle:
        raw = handle.read(ceiling + 1)
    return raw[:ceiling], len(raw) > ceiling


def _require_editable_file(source: _Source, node_id: str) -> None:
    """That this node has text to show at all.

    Asked of the representations the format declares rather than of a list
    kept beside them: the two were separate, and they drifted the moment a log
    became a thing this source could open. Whether the text may also be
    written back is a different question, answered per document by
    `writable` — a file too large or not valid UTF-8 is still shown. Binary
    bytes are refused by whoever reads them, so the file is opened once.
    """
    if not source.exists:
        raise ValueError(say("No such file: {node_id}", node_id=node_id))
    if source.is_directory:
        raise ValueError(say("A directory has no source editor: {node_id}", node_id=node_id))
    if not offers_source(source.name):
        raise ValueError(say("This file has no text to show"))


def _editor_language(
    name: str,
) -> tuple[str | None, EditorValidationKind | None]:
    file_format = format_of(name)
    if file_format == "json":
        return "json", "json"
    if file_format == "jsonl":
        return "json", "jsonl"
    if file_format == "markdown":
        return "markdown", None
    return None, None


def _version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_replacement(name: str, text: str) -> None:
    file_format = format_of(name)
    if file_format == "json":
        try:
            jsontext.load(text)
        except JSONDecodeError as exc:
            raise ValueError(
                say(
                    "Invalid JSON ({problem}, line {line} column {column})",
                    problem=exc.msg,
                    line=exc.lineno,
                    column=exc.colno,
                )
            ) from None
        except jsontext.NonStandardJson as exc:
            raise ValueError(say("Invalid JSON ({problem})", problem=exc)) from None
        return
    if file_format == "jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                jsontext.load(line)
            except JSONDecodeError as exc:
                raise ValueError(
                    say(
                        "Invalid JSON on line {line} ({problem}, column {column})",
                        line=line_number,
                        problem=exc.msg,
                        column=exc.colno,
                    )
                ) from None
            except jsontext.NonStandardJson as exc:
                raise ValueError(
                    say(
                        "Invalid JSON on line {line} ({problem})",
                        line=line_number,
                        problem=exc,
                    )
                ) from None

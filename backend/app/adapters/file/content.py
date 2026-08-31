"""Bounded native content viewers for files."""

import hashlib
import io
import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from functools import partial
from json import JSONDecodeError
from pathlib import Path
from typing import Any, assert_never

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
    JsonArray,
    JsonContent,
    JsonLine,
    JsonLinesContent,
    JsonObject,
    JsonObjectEntry,
    JsonScalar,
    JsonValue,
    MarkdownContent,
    PdfContent,
    TextContent,
    UpdateContentRequest,
    VideoContent,
)
from app.adapters.file.binary import looks_binary
from app.adapters.file.formats import format_of, representations_of
from app.adapters.file.media import audio_facts, pdf_facts, video_facts
from app.adapters.file.session import FileSession

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


class FileContent:
    def __init__(self, session: FileSession) -> None:
        self._session = session

    async def read_content(self, request: ContentRequest) -> ContentResult:
        path = self._session.resolve(request.node_id)
        return await to_thread.run_sync(self._read, path, request)

    async def read_editor_content(
        self, request: EditorContentRequest
    ) -> EditorContent:
        path = self._session.resolve(request.node_id)
        return await to_thread.run_sync(self._read_editor, path, request)

    async def update_content(self, request: UpdateContentRequest) -> ContentUpdated:
        path = self._session.resolve(request.node_id)
        return await to_thread.run_sync(self._update, path, request)

    async def preview_content(
        self, request: ContentRequest
    ) -> BoundedContentPreview:
        path = self._session.resolve(request.node_id)
        return await to_thread.run_sync(self._read_image_preview, path, request)

    def _read(self, path: Path, request: ContentRequest) -> ContentResult:
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if path.is_dir():
            raise ValueError(f"A directory has no content viewer: {request.node_id}")

        available = {item.kind for item in representations_of(path.name)}
        if request.representation not in available:
            raise ValueError(
                f'This file does not offer the "{request.representation}" representation'
            )

        match request.representation:
            case "text":
                return _read_text(path)
            case "json":
                return _read_json(path)
            case "jsonl":
                return _read_json_lines(path, request.limit, request.offset)
            case "markdown":
                return _read_markdown(path)
            case "image":
                preview = self._read_image_preview(path, request)
                return _image_content(preview)
            case "audio":
                return _audio_content(path)
            case "video":
                return _video_content(path)
            case "pdf":
                return _pdf_content(path)
            case unreachable:
                assert_never(unreachable)

    async def open_content_stream(self, request: ContentRequest) -> ContentStream:
        """Bytes a player or a reader takes part of, verified first (D52)."""
        path = self._session.resolve(request.node_id)
        return await to_thread.run_sync(self._open_stream, path, request)

    def _open_stream(self, path: Path, request: ContentRequest) -> ContentStream:
        result = self._read(path, request)
        if not isinstance(result, AudioContent | VideoContent | PdfContent):
            raise ValueError(
                f'The "{request.representation}" representation is not streamed'
            )
        return ContentStream(
            media_type=result.media_type,
            filename=result.filename,
            size_bytes=result.size_bytes,
            read=partial(_range_chunks, path),
        )

    def _read_image_preview(
        self, path: Path, request: ContentRequest
    ) -> BoundedContentPreview:
        if not path.exists():
            raise ValueError(f"No such file: {request.node_id}")
        if not path.is_file():
            raise ValueError(f"A directory has no image viewer: {request.node_id}")
        if request.representation != "image" or "image" not in {
            item.kind for item in representations_of(path.name)
        }:
            raise ValueError('This file does not offer the "image" representation')
        raw, truncated = _byte_prefix(path, MAX_IMAGE_BYTES)
        if truncated:
            raise ValueError(
                f"Images larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB "
                "cannot be previewed"
            )
        media_type, width, height = _verified_image(raw)
        return BoundedContentPreview(
            body=raw,
            media_type=media_type,
            filename=path.name,
            width=width,
            height=height,
        )

    def _read_editor(
        self, path: Path, request: EditorContentRequest
    ) -> EditorContent:
        _require_editable_file(path, request.node_id)
        language_hint, validation = _editor_language(path)
        raw, truncated = _byte_prefix(path, MAX_EDITOR_BYTES)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return EditorContent(
                text=raw.decode("utf-8", errors="replace"),
                filename=path.name,
                writable=False,
                truncated=truncated,
                reason=f"This file is not valid UTF-8 at byte {exc.start + 1}.",
                language_hint=language_hint,
                validation=validation,
            )
        if truncated:
            return EditorContent(
                text=text,
                filename=path.name,
                writable=False,
                truncated=True,
                reason=(
                    f"Files larger than {MAX_EDITOR_BYTES // (1024 * 1024)} MB "
                    "are shown as a preview and cannot be edited here."
                ),
                language_hint=language_hint,
                validation=validation,
            )
        return EditorContent(
            text=text,
            filename=path.name,
            version=_version(raw),
            writable=True,
            language_hint=language_hint,
            validation=validation,
        )

    def _update(self, path: Path, request: UpdateContentRequest) -> ContentUpdated:
        _require_editable_file(path, request.node_id)
        current = path.read_bytes()
        if len(current) > MAX_EDITOR_BYTES:
            raise ValueError(
                f"Files larger than {MAX_EDITOR_BYTES // (1024 * 1024)} MB "
                "cannot be edited here"
            )
        if _version(current) != request.version:
            raise ContentConflict
        try:
            current.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("This file is not valid UTF-8 and cannot be edited") from None

        replacement = request.text.encode("utf-8")
        if len(replacement) > MAX_EDITOR_BYTES:
            raise ValueError(
                f"The edited content is larger than "
                f"{MAX_EDITOR_BYTES // (1024 * 1024)} MB"
            )
        _validate_replacement(path, request.text)
        _replace_bytes(path, replacement)
        return ContentUpdated(version=_version(replacement))


def _audio_content(path: Path) -> AudioContent:
    facts = audio_facts(path)
    return AudioContent(
        filename=path.name,
        media_type=facts.media_type,
        size_bytes=path.stat().st_size,
        duration_seconds=facts.duration_seconds,
        channels=facts.channels,
        sample_rate=facts.sample_rate,
    )


def _video_content(path: Path) -> VideoContent:
    facts = video_facts(path)
    return VideoContent(
        filename=path.name,
        media_type=facts.media_type,
        size_bytes=path.stat().st_size,
        duration_seconds=facts.duration_seconds,
        width=facts.width,
        height=facts.height,
    )


def _pdf_content(path: Path) -> PdfContent:
    return PdfContent(
        filename=path.name,
        size_bytes=path.stat().st_size,
        version=pdf_facts(path).version,
    )


async def _range_chunks(path: Path, start: int, end: int) -> AsyncIterator[bytes]:
    """The inclusive range, in chunks, and never a byte past it.

    Opened per request rather than held open between them: a player asks for
    the end of a file, then the beginning, then a piece in the middle, and each
    of those is its own HTTP request.
    """
    remaining = end - start + 1
    handle = await to_thread.run_sync(path.open, "rb")
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


def _read_text(path: Path) -> TextContent:
    if looks_binary(path):
        raise ValueError("This file contains binary data and cannot be shown as text")
    text, truncated, notice = _text_prefix(path, MAX_TEXT_BYTES)
    return TextContent(text=text, truncated=truncated, notice=notice)


def _read_markdown(path: Path) -> MarkdownContent:
    if looks_binary(path):
        raise ValueError("This file contains binary data and is not a document")
    text, truncated, notice = _text_prefix(path, MAX_MARKDOWN_BYTES)
    return MarkdownContent(text=text, truncated=truncated, notice=notice)


def _verified_image(raw: bytes) -> tuple[ImageMediaType, int, int]:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            media_type = IMAGE_MEDIA_TYPES.get(image.format or "")
            if media_type is None:
                raise ValueError("Only PNG and JPEG images can be previewed")
            width, height = image.size
            if width < 1 or height < 1:
                raise ValueError("This image has invalid dimensions")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Animated images are not supported by this viewer yet")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    f"Images larger than {MAX_IMAGE_PIXELS:,} pixels cannot be previewed"
                )
            image.verify()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise ValueError("This file is not a valid PNG or JPEG image") from None
    return media_type, width, height


def _image_content(preview: BoundedContentPreview) -> ImageContent:
    media_type = preview.media_type
    if media_type not in {"image/png", "image/jpeg"}:
        raise ValueError("This file is not a supported image")
    return ImageContent(
        filename=preview.filename,
        media_type=media_type,
        size_bytes=len(preview.body),
        width=preview.width,
        height=preview.height,
    )


def _read_json(path: Path) -> JsonContent:
    size = path.stat().st_size
    if size > MAX_JSON_BYTES:
        text, truncated, decode_notice = _text_prefix(path, MAX_TEXT_BYTES)
        notice = (
            f"This file is larger than {MAX_JSON_BYTES // (1024 * 1024)} MB, "
            "so it was not parsed as one JSON document."
        )
        if decode_notice is not None:
            notice = f"{notice} {decode_notice}"
        return JsonContent(
            source_text=text,
            truncated=truncated,
            notice=notice,
        )

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return JsonContent(
            source_text=raw.decode("utf-8", errors="replace"),
            notice=f"This file is not valid UTF-8 at byte {exc.start + 1}.",
        )

    try:
        parsed = jsontext.load(text)
    except JSONDecodeError as exc:
        return JsonContent(
            source_text=text,
            notice=(
                f"This file is not valid JSON ({exc.msg}, line {exc.lineno} "
                f"column {exc.colno})."
            ),
        )
    except jsontext.NonStandardJson as exc:
        return JsonContent(
            source_text=text,
            notice=f"This file is not valid JSON ({exc}).",
        )
    try:
        return JsonContent(value=_json_value(parsed))
    except RecursionError:
        return JsonContent(
            source_text=text,
            notice="This JSON document is too deeply nested to show safely.",
        )


def _read_json_lines(path: Path, limit: int, offset: int) -> JsonLinesContent:
    items: list[JsonLine] = []
    seen = 0
    page_bytes = 0
    has_more = False
    for line_number, raw, truncated in _bounded_lines(path):
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
            notice=f"Line {line_number} is not valid UTF-8 at byte {exc.start + 1}.",
        )
    if truncated:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            truncated=True,
            notice=(
                f"Line {line_number} is larger than "
                f"{MAX_JSON_LINE_BYTES // (1024 * 1024)} MB and was not parsed."
            ),
        )
    try:
        return JsonLine(line_number=line_number, value=_json_value(jsontext.load(text)))
    except JSONDecodeError as exc:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=(
                f"Line {line_number} is not valid JSON ({exc.msg}, column {exc.colno})."
            ),
        )
    except jsontext.NonStandardJson as exc:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=f"Line {line_number} is not valid JSON ({exc}).",
        )
    except RecursionError:
        return JsonLine(
            line_number=line_number,
            source_text=text,
            notice=f"Line {line_number} is too deeply nested to show safely.",
        )


def _bounded_lines(path: Path) -> Iterator[tuple[int, bytes, bool]]:
    """Physical lines without an unbounded ``readline`` allocation."""
    with path.open("rb") as handle:
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


def _text_prefix(path: Path, ceiling: int) -> tuple[str, bool, str | None]:
    preview, truncated = _byte_prefix(path, ceiling)
    try:
        return preview.decode("utf-8"), truncated, None
    except UnicodeDecodeError as exc:
        return (
            preview.decode("utf-8", errors="replace"),
            truncated,
            f"This file is not valid UTF-8 at byte {exc.start + 1}.",
        )


def _byte_prefix(path: Path, ceiling: int) -> tuple[bytes, bool]:
    with path.open("rb") as handle:
        raw = handle.read(ceiling + 1)
    return raw[:ceiling], len(raw) > ceiling


def _require_editable_file(path: Path, node_id: str) -> None:
    if not path.exists():
        raise ValueError(f"No such file: {node_id}")
    if path.is_dir():
        raise ValueError(f"A directory has no source editor: {node_id}")
    if format_of(path.name) not in {"text", "markdown", "json", "jsonl"}:
        raise ValueError("This file does not offer source editing")
    if looks_binary(path):
        raise ValueError("This file contains binary data and cannot be edited as text")


def _editor_language(
    path: Path,
) -> tuple[str | None, EditorValidationKind | None]:
    file_format = format_of(path.name)
    if file_format == "json":
        return "json", "json"
    if file_format == "jsonl":
        return "json", "jsonl"
    if file_format == "markdown":
        return "markdown", None
    return None, None


def _version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_replacement(path: Path, text: str) -> None:
    file_format = format_of(path.name)
    if file_format == "json":
        try:
            jsontext.load(text)
        except JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON ({exc.msg}, line {exc.lineno} column {exc.colno})"
            ) from None
        except jsontext.NonStandardJson as exc:
            raise ValueError(f"Invalid JSON ({exc})") from None
        return
    if file_format == "jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                jsontext.load(line)
            except JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} ({exc.msg}, "
                    f"column {exc.colno})"
                ) from None
            except jsontext.NonStandardJson as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} ({exc})"
                ) from None


def _replace_bytes(path: Path, replacement: bytes) -> None:
    """Write beside the file, preserve its mode, then replace it in one step."""
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".edit-")
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(replacement)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, path.stat().st_mode)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _json_value(value: Any) -> JsonValue:
    if value is None:
        return JsonScalar(kind="null", value=None)
    if isinstance(value, jsontext.JsonNumber):
        return JsonScalar(kind="number", value=value.text)
    if isinstance(value, bool):
        return JsonScalar(kind="boolean", value="true" if value else "false")
    if isinstance(value, str):
        return JsonScalar(kind="string", value=value)
    if isinstance(value, list):
        return JsonArray(items=[_json_value(item) for item in value])
    if isinstance(value, dict):
        return JsonObject(
            entries=[
                JsonObjectEntry(name=name, value=_json_value(item))
                for name, item in value.items()
            ]
        )
    raise TypeError("Not a JSON value")

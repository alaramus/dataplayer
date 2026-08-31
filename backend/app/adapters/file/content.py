"""Bounded native content viewers for files."""

import hashlib
import os
import tempfile
from collections.abc import Iterator
from json import JSONDecodeError
from pathlib import Path
from typing import Any, assert_never

from anyio import to_thread

from app.adapters import jsontext
from app.adapters.content import (
    ContentConflict,
    ContentRequest,
    ContentResult,
    ContentUpdated,
    EditorContent,
    EditorContentRequest,
    EditorValidationKind,
    JsonArray,
    JsonContent,
    JsonLine,
    JsonLinesContent,
    JsonObject,
    JsonObjectEntry,
    JsonScalar,
    JsonValue,
    TextContent,
    UpdateContentRequest,
)
from app.adapters.file.binary import looks_binary
from app.adapters.file.formats import format_of, representations_of
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
            case unreachable:
                assert_never(unreachable)

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


def _read_text(path: Path) -> TextContent:
    if looks_binary(path):
        raise ValueError("This file contains binary data and cannot be shown as text")
    text, truncated, notice = _text_prefix(path, MAX_TEXT_BYTES)
    return TextContent(text=text, truncated=truncated, notice=notice)


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
    if format_of(path.name) not in {"text", "json", "jsonl"}:
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

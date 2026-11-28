"""A Word document read as the Markdown the document viewer renders (D462).

Only the standard library: a `.docx` is a ZIP of XML parts, and what is read
of it is text, headings, lists, tables, emphasis and links. Elements are
matched by local name, so the strict variant of the format, whose namespaces
differ, reads the same way.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO
from xml.etree import ElementTree

# What one part of the package may unpack to. `word/document.xml` of a book
# is a few megabytes; a part claiming more is not read, whatever the ZIP says.
MAX_PART_BYTES = 32 * 1024 * 1024
MAX_STYLE_DEPTH = 16
MAX_HEADING_LEVEL = 6
LINK_SCHEMES = ("http://", "https://", "mailto:")
# What Markdown, or an extension of the renderer of D50, gives a meaning to
# anywhere in a line: `$` is maths there and `|` a cell. Few, because the
# escapes are read aloud from this text as well.
_SPECIAL = re.compile(r"([\\`*_\[\]<>|~$&])")
# And what means something only where a line starts: a heading, a quote, an
# item of a list, a rule.
_LINE_START = re.compile(r"^(\d{1,9})([.)])|^([#>+\-=])")
_OFF = {"0", "false", "off", "none"}
_BREAK = "\x00"
_BLANK = " \t\r\n" + _BREAK
_ENDS = re.compile(r"^([\s\x00]*)(.*?)([\s\x00]*)$", re.DOTALL)
_DOCTYPE = re.compile(rb"<!doctype", re.IGNORECASE)


class NotADocument(ValueError):
    """The bytes are not a Word document this reader can open."""


@dataclass
class DocxText:
    markdown: str
    pictures: int
    truncated: bool


@dataclass(frozen=True)
class _Style:
    heading: int | None
    numbering: tuple[str, int] | None
    based_on: str | None


@dataclass
class _Package:
    styles: dict[str, _Style] = field(default_factory=dict)
    # numId → ilvl → whether that level is a bulleted one.
    bullets: dict[str, dict[int, bool]] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    pictures: int = 0


def read_docx(handle: BinaryIO, ceiling: int) -> DocxText:
    """The document's body as Markdown of at most `ceiling` UTF-8 bytes."""
    try:
        with zipfile.ZipFile(handle) as package:
            return _read_package(package, ceiling)
    except (
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        ElementTree.ParseError,
        KeyError,
        EOFError,
        zlib.error,
        # Encrypted, or compressed by a method this Python does not have.
        NotImplementedError,
        RuntimeError,
    ):
        raise NotADocument from None


def _read_package(package: zipfile.ZipFile, ceiling: int) -> DocxText:
    main = _target(_relations(package, "_rels/.rels"), "/officeDocument", "")
    main = main or "word/document.xml"
    relations = _relations(package, _relations_part(main))
    state = _Package(
        links={
            key: target
            for key, (kind, target, external) in relations.items()
            if kind.endswith("/hyperlink") and external
        }
    )
    styles_part = _target(relations, "/styles", main)
    if styles_part is not None and styles_part in package.NameToInfo:
        state.styles = _styles(_parse(package, styles_part))
    numbering_part = _target(relations, "/numbering", main)
    if numbering_part is not None and numbering_part in package.NameToInfo:
        state.bullets = _numbering(_parse(package, numbering_part))
    body = _child(_parse(package, main), "body")
    if body is None:
        raise NotADocument

    blocks: list[str] = []
    size = 0
    truncated = False
    previous_list = False
    for block, is_list in _blocks(body, state):
        separator = "\n" if previous_list and is_list else "\n\n"
        piece = (separator if blocks else "") + block
        cost = len(piece.encode("utf-8"))
        if size + cost > ceiling:
            truncated = True
            break
        blocks.append(piece)
        size += cost
        previous_list = is_list
    return DocxText(markdown="".join(blocks), pictures=state.pictures, truncated=truncated)


def _parse(package: zipfile.ZipFile, name: str) -> ElementTree.Element:
    info = package.getinfo(name)
    if info.file_size > MAX_PART_BYTES:
        raise NotADocument
    with package.open(info) as part:
        raw = part.read(MAX_PART_BYTES + 1)
    if len(raw) > MAX_PART_BYTES:
        raise NotADocument
    # A document type declaration is where entities come from, and no part of
    # a Word document has one; refusing it leaves expat nothing to expand.
    if _DOCTYPE.search(raw) is not None:
        raise NotADocument
    return ElementTree.fromstring(raw)


def _relations_part(part: str) -> str:
    folder, name = posixpath.split(part)
    return posixpath.join(folder, "_rels", f"{name}.rels")


def _relations(
    package: zipfile.ZipFile, name: str
) -> dict[str, tuple[str, str, bool]]:
    if name not in package.NameToInfo:
        return {}
    found: dict[str, tuple[str, str, bool]] = {}
    for item in _parse(package, name):
        if _local(item.tag) != "Relationship":
            continue
        key = item.get("Id")
        target = item.get("Target")
        if key is None or target is None:
            continue
        external = item.get("TargetMode") == "External"
        found[key] = (item.get("Type", ""), target, external)
    return found


def _target(
    relations: dict[str, tuple[str, str, bool]], kind: str, source: str
) -> str | None:
    for found_kind, target, external in relations.values():
        if external or not found_kind.endswith(kind):
            continue
        if target.startswith("/"):
            return target.lstrip("/")
        return posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
    return None


def _styles(root: ElementTree.Element) -> dict[str, _Style]:
    styles: dict[str, _Style] = {}
    for style in root:
        if _local(style.tag) != "style":
            continue
        key = _attribute(style, "styleId")
        if key is None:
            continue
        name = _child(style, "name")
        properties = _child(style, "pPr")
        styles[key] = _Style(
            heading=_heading_of_name(
                "" if name is None else (_attribute(name, "val") or "")
            )
            or _outline_heading(properties),
            numbering=_numbering_of(properties),
            based_on=_value(_child(style, "basedOn")),
        )
    return styles


def _heading_of_name(name: str) -> int | None:
    lowered = name.strip().lower()
    if lowered == "title":
        return 1
    match = re.fullmatch(r"heading\s*(\d)", lowered)
    if match is None:
        return None
    return min(max(int(match.group(1)), 1), MAX_HEADING_LEVEL)


def _outline_heading(properties: ElementTree.Element | None) -> int | None:
    level = _value(_child(properties, "outlineLvl"))
    if level is None or not level.isdigit():
        return None
    # Level 9 is "body text" in the format's own numbering.
    number = int(level) + 1
    return number if number <= MAX_HEADING_LEVEL else None


def _numbering_of(properties: ElementTree.Element | None) -> tuple[str, int] | None:
    numbering = _child(properties, "numPr")
    if numbering is None:
        return None
    number = _value(_child(numbering, "numId"))
    level = _value(_child(numbering, "ilvl")) or "0"
    if number is None or number == "0" or not level.isdigit():
        return None
    return number, int(level)


def _numbering(root: ElementTree.Element) -> dict[str, dict[int, bool]]:
    abstract: dict[str, dict[int, bool]] = {}
    for item in root:
        if _local(item.tag) != "abstractNum":
            continue
        key = _attribute(item, "abstractNumId")
        if key is None:
            continue
        levels: dict[int, bool] = {}
        for level in item:
            if _local(level.tag) != "lvl":
                continue
            index = _attribute(level, "ilvl")
            if index is None or not index.isdigit():
                continue
            levels[int(index)] = _value(_child(level, "numFmt")) in {"bullet", "none", None}
        abstract[key] = levels
    found: dict[str, dict[int, bool]] = {}
    for item in root:
        if _local(item.tag) != "num":
            continue
        key = _attribute(item, "numId")
        reference = _value(_child(item, "abstractNumId"))
        if key is not None and reference is not None:
            found[key] = abstract.get(reference, {})
    return found


def _blocks(
    container: ElementTree.Element, state: _Package
) -> Iterator[tuple[str, bool]]:
    """Each block of the body in order, and whether it is an item of a list."""
    for element in container:
        match _local(element.tag):
            case "p":
                block = _paragraph(element, state)
                if block is not None:
                    yield block
            case "tbl":
                table = _table(element, state)
                if table:
                    yield table, False
            case "sdt":
                content = _child(element, "sdtContent")
                if content is not None:
                    yield from _blocks(content, state)
            case "customXml" | "ins" | "moveTo":
                yield from _blocks(element, state)
            case _:
                continue


def _paragraph(
    paragraph: ElementTree.Element, state: _Package
) -> tuple[str, bool] | None:
    properties = _child(paragraph, "pPr")
    style = _resolved_style(_value(_child(properties, "pStyle")), state)
    numbering = _numbering_of(properties) or style.numbering
    heading = _outline_heading(properties) or style.heading
    in_list = numbering is not None and heading is None
    # A break inside a line is held as a NUL until the paragraph's own ends
    # are trimmed, so a break at either end leaves no stray backslash.
    held = _inline(paragraph, state).strip(_BLANK)
    if not held:
        return None
    held = _LINE_START.sub(_escaped_start, held)
    text = held.replace(_BREAK, " " if in_list or heading else "\\\n")
    if heading is not None:
        return "#" * heading + " " + text, False
    if numbering is not None:
        number, level = numbering
        bullet = state.bullets.get(number, {}).get(level, True)
        marker = "-" if bullet else "1."
        return "    " * min(level, 8) + marker + " " + text, True
    return text, False


def _resolved_style(key: str | None, state: _Package) -> _Style:
    """A paragraph style with what it inherits filled in."""
    heading: int | None = None
    numbering: tuple[str, int] | None = None
    seen: set[str] = set()
    while key is not None and key not in seen and len(seen) < MAX_STYLE_DEPTH:
        seen.add(key)
        style = state.styles.get(key)
        if style is None:
            break
        heading = heading or style.heading
        numbering = numbering or style.numbering
        key = style.based_on
    return _Style(heading=heading, numbering=numbering, based_on=None)


def _inline(element: ElementTree.Element, state: _Package) -> str:
    parts: list[str] = []
    for child in element:
        match _local(child.tag):
            case "r":
                parts.append(_run(child, state))
            case "hyperlink":
                parts.append(_link(child, state))
            case "ins" | "moveTo" | "smartTag" | "fldSimple" | "customXml" | "dir" | "bdo":
                parts.append(_inline(child, state))
            case "sdt":
                content = _child(child, "sdtContent")
                if content is not None:
                    parts.append(_inline(content, state))
            case _:
                # Deleted text, properties, bookmarks, comments' anchors.
                continue
    return "".join(parts)


def _link(element: ElementTree.Element, state: _Package) -> str:
    text = _inline(element, state)
    key = next(
        (value for name, value in element.attrib.items() if _local(name) == "id"),
        None,
    )
    target = None if key is None else state.links.get(key)
    if (
        not text.strip()
        or target is None
        or not target.lower().startswith(LINK_SCHEMES)
        or any(character in target for character in "<>\n\r ")
    ):
        return text
    return f"[{text}](<{target}>)"


def _run(run: ElementTree.Element, state: _Package) -> str:
    text: list[str] = []
    for child in run:
        match _local(child.tag):
            case "t":
                text.append(_escape(child.text or ""))
            case "tab" | "ptab":
                text.append(" ")
            case "br" | "cr":
                if _attribute(child, "type") in {None, "textWrapping"}:
                    text.append(_BREAK)
            case "noBreakHyphen":
                text.append("\\-")
            case "drawing" | "pict" | "object":
                state.pictures += 1
            case _:
                continue
    joined = "".join(text)
    if not joined.strip(_BLANK):
        return joined
    properties = _child(run, "rPr")
    marker = ""
    if _switched_on(_child(properties, "b")):
        marker += "**"
    if _switched_on(_child(properties, "i")):
        marker += "*"
    struck = _switched_on(_child(properties, "strike")) or _switched_on(
        _child(properties, "dstrike")
    )
    if not marker and not struck:
        return joined
    # Emphasis does not open on a space, so the spaces stay outside it.
    match = _ENDS.match(joined)
    assert match is not None  # the pattern matches any string
    before, middle, after = match.groups()
    if struck:
        middle = f"~~{middle}~~"
    return f"{before}{marker}{middle}{marker[::-1]}{after}"


def _table(table: ElementTree.Element, state: _Package) -> str:
    rows: list[list[str]] = []
    for row in table:
        if _local(row.tag) != "tr":
            continue
        cells: list[str] = []
        for cell in row:
            if _local(cell.tag) != "tc":
                continue
            properties = _child(cell, "tcPr")
            text = " ".join(
                part for part in (block for block, _ in _blocks(cell, state)) if part
            )
            # A cell is one line of a Markdown table: what made lines is spaces.
            cells.append(" ".join(text.replace("\\\n", " ").split()))
            span = _value(_child(properties, "gridSpan"))
            if span is not None and span.isdigit():
                cells.extend([""] * min(int(span) - 1, 63))
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    lines = [
        "| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in rows
    ]
    lines.insert(1, "|" + " --- |" * width)
    return "\n".join(lines)


def _escape(text: str) -> str:
    return _SPECIAL.sub(r"\\\1", text.replace("\t", " ").replace("\xa0", " "))


def _escaped_start(match: re.Match[str]) -> str:
    number, stop, mark = match.groups()
    return f"{number}\\{stop}" if number else f"\\{mark}"


def _switched_on(element: ElementTree.Element | None) -> bool:
    if element is None:
        return False
    value = _attribute(element, "val")
    return value is None or value.lower() not in _OFF


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(
    element: ElementTree.Element | None, name: str
) -> ElementTree.Element | None:
    if element is None:
        return None
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _attribute(element: ElementTree.Element, name: str) -> str | None:
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _value(element: ElementTree.Element | None) -> str | None:
    return None if element is None else _attribute(element, "val")

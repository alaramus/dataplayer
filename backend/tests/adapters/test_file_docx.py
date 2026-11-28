"""A Word document opened by a file source as the document viewer's Markdown (D462)."""

import io
import zipfile
from pathlib import Path

import pytest

from app.adapters.content import (
    ContentRequest,
    EditorContentRequest,
    MarkdownContent,
)
from app.adapters.explorer.content import ExplorerContent
from app.adapters.explorer.docx import NotADocument, read_docx
from app.adapters.explorer.formats import offers_source, representations_of
from app.adapters.file.storage import LocalStorage

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"

STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="{W}">
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>
  <w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Chapter"><w:name w:val="Chapter"/><w:basedOn w:val="1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Deep">
    <w:name w:val="Deep"/><w:pPr><w:outlineLvl w:val="2"/></w:pPr>
  </w:style>
</w:styles>"""

NUMBERING = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:numbering xmlns:w="{W}">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>
    <w:lvl w:ilvl="1"><w:numFmt w:val="decimal"/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="5"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""


def _p(inner: str, style: str | None = None, numbered: tuple[int, int] | None = None) -> str:
    properties = ""
    if style is not None:
        properties += f'<w:pStyle w:val="{style}"/>'
    if numbered is not None:
        number, level = numbered
        properties += (
            f'<w:numPr><w:ilvl w:val="{level}"/><w:numId w:val="{number}"/></w:numPr>'
        )
    return f"<w:p><w:pPr>{properties}</w:pPr>{inner}</w:p>"


def _r(text: str, properties: str = "") -> str:
    return f'<w:r><w:rPr>{properties}</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r>'


BODY = "".join(
    [
        _p(_r("Quarterly report"), style="Title"),
        _p(_r("Summary"), style="Chapter"),
        _p(
            _r("Plain, ")
            + _r("bold", "<w:b/>")
            + _r(" and ")
            + _r("italic ", "<w:i/>")
            + _r("not bold", '<w:b w:val="0"/>')
            + '<w:hyperlink r:id="rLink">' + _r("a link") + "</w:hyperlink>"
            + '<w:hyperlink r:id="rScript">' + _r("a script") + "</w:hyperlink>"
        ),
        _p(_r("Costs $5 * 2 &amp; [more]")),
        _p(_r("1. not a list") + "<w:r><w:br/></w:r>" + _r("second line") + "<w:r><w:br/></w:r>"),
        _p(_r("Detail"), style="Deep"),
        _p(_r("first point"), numbered=(5, 0)),
        _p(_r("its step"), numbered=(5, 1)),
        _p(_r("A picture:") + "<w:r><w:drawing/></w:r>"),
        "<w:tbl>"
        "<w:tr><w:tc>" + _p(_r("Name")) + "</w:tc><w:tc>" + _p(_r("Total")) + "</w:tc></w:tr>"
        "<w:tr><w:tc><w:tcPr><w:gridSpan w:val=\"2\"/></w:tcPr>" + _p(_r("a|b")) + "</w:tc></w:tr>"
        "</w:tbl>",
        _p("<w:del><w:r><w:delText>removed</w:delText></w:r></w:del>"),
        "<w:sectPr/>",
    ]
)


def _docx(
    body: str = BODY,
    document: str | None = None,
    link: str = "https://example.test/a b",
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr(
            "_rels/.rels",
            f'<Relationships xmlns="{PACKAGE}">'
            f'<Relationship Id="r1" Type="{R}/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        package.writestr(
            "word/_rels/document.xml.rels",
            f'<Relationships xmlns="{PACKAGE}">'
            f'<Relationship Id="rS" Type="{R}/styles" Target="styles.xml"/>'
            f'<Relationship Id="rN" Type="{R}/numbering" Target="numbering.xml"/>'
            f'<Relationship Id="rLink" Type="{R}/hyperlink" Target="{link}" TargetMode="External"/>'
            f'<Relationship Id="rScript" Type="{R}/hyperlink" Target="javascript:alert(1)" TargetMode="External"/>'
            "</Relationships>",
        )
        package.writestr("word/styles.xml", STYLES)
        package.writestr("word/numbering.xml", NUMBERING)
        package.writestr(
            "word/document.xml",
            document
            or f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}</w:body></w:document>',
        )
    return buffer.getvalue()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "report.docx").write_bytes(_docx())
    (tmp_path / "renamed.docx").write_bytes(b"not a zip at all")
    return tmp_path


@pytest.fixture
def content(root: Path) -> ExplorerContent:
    return ExplorerContent(LocalStorage(root))


def test_a_word_document_offers_the_document_viewer_and_no_source() -> None:
    assert [item.kind for item in representations_of("Report.DOCX")] == ["markdown"]
    assert offers_source("report.docx") is False
    # The legacy binary format is another container, and stays opaque.
    assert representations_of("report.doc") == []


async def test_a_word_document_arrives_as_markdown(content: ExplorerContent) -> None:
    result = await content.read_content(
        ContentRequest(node_id="report.docx", representation="markdown")
    )

    assert isinstance(result, MarkdownContent)
    lines = result.text.split("\n")
    assert lines[0] == "# Quarterly report"
    # A style based on "heading 1" is one, whatever it is called.
    assert "# Summary" in lines
    # A level of the outline is a heading even without the name.
    assert "### Detail" in lines
    # A target with a space, and one that is not a web or mail address, leave
    # their text and no link.
    assert "Plain, **bold** and *italic* not bolda linka script" in lines
    assert "javascript:" not in result.text
    assert r"Costs \$5 \* 2 \& \[more\]" in lines
    assert "1\\. not a list\\" in lines
    assert "second line" in lines
    assert "- first point" in lines
    assert "    1. its step" in lines
    assert "| Name | Total |" in lines
    assert r"| a\|b |  |" in lines
    assert "removed" not in result.text
    assert result.notice == "Pictures not shown: 1"


async def test_a_plain_link_becomes_a_markdown_link(root: Path) -> None:
    body = '<w:p><w:hyperlink r:id="rLink">' + _r("here") + "</w:hyperlink></w:p>"
    document = _docx(body, link="https://example.test/a_b")
    (root / "link.docx").write_bytes(document)

    result = await ExplorerContent(LocalStorage(root)).read_content(
        ContentRequest(node_id="link.docx", representation="markdown")
    )

    assert isinstance(result, MarkdownContent)
    assert result.text == "[here](<https://example.test/a_b>)"
    assert result.notice is None


async def test_a_file_that_is_not_a_word_document_is_named_so(
    content: ExplorerContent,
) -> None:
    with pytest.raises(ValueError, match="not a Word document"):
        await content.read_content(
            ContentRequest(node_id="renamed.docx", representation="markdown")
        )


async def test_a_word_document_has_no_text_for_the_editor(
    content: ExplorerContent,
) -> None:
    with pytest.raises(ValueError, match="no text to show"):
        await content.read_editor_content(EditorContentRequest(node_id="report.docx"))


def test_a_document_type_declaration_is_refused() -> None:
    document = (
        '<?xml version="1.0"?><!DOCTYPE w:document [<!ENTITY a "aaaa">]>'
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>'
    )

    with pytest.raises(NotADocument):
        read_docx(io.BytesIO(_docx(document=document)), 1024)


def test_the_markdown_stops_at_its_ceiling_on_a_whole_block() -> None:
    body = "".join(_p(_r(f"paragraph {index}")) for index in range(100))

    read = read_docx(io.BytesIO(_docx(body)), 50)

    assert read.truncated is True
    assert read.markdown.startswith("paragraph 0\n\nparagraph 1")
    assert len(read.markdown.encode()) <= 50
    assert read.markdown.endswith(tuple("0123456789"))

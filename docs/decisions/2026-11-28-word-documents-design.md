# Reading a Word document

## Problem

A folder of files is full of `.docx`, and a file source listed every one of
them as opaque: listed, downloadable, and nothing to open. Somebody who wanted
to know what a report said had to download it and open another program.

## What a Word document is read as

The document viewer already exists: Markdown is rendered in the browser with a
table of contents, search, export to HTML and print, and reading aloud (D50).
A Word document's body is headings, paragraphs, lists, tables, emphasis and
links, which is what Markdown states. So the server reads the `.docx` and
answers the `markdown` representation with Markdown made from it. No new
representation, panel or route; the browser cannot tell the two apart except
that a `.docx` offers nothing else.

Rejected:

- **HTML from the server.** `MarkdownContent` carries no HTML on purpose
  (D50): rendering and sanitising live in one place, in the browser. A second
  path for HTML would be a second sanitiser.
- **A converter library** (`mammoth`, `python-docx`, `pandoc`). Each is a new
  dependency for what is a ZIP of XML parts read by name; `mammoth`'s own
  Markdown output is deprecated, and `pandoc` is a program to install.
- **Rendering pages as Word does.** Layout, fonts and pages are what a word
  processor is for. What is wanted here is to read the text.

## How it is read

- `word/document.xml` is found through `_rels/.rels`, and styles and numbering
  through the document's own relationships. Elements are matched by local name,
  so the strict variant of the format reads the same.
- A heading is a paragraph whose style, or a style it is based on, is named
  `heading N` or `Title`, or whose outline level is set. Style ids are not
  trusted: a Russian Word names them `1`, `2`.
- A list item is a paragraph with numbering, its own or its style's; the
  numbering part says whether that level is bulleted. Items nest by level.
- A table is a Markdown table whose first row is the header; a merged cell
  leaves empty cells after it, and a cell's paragraphs join into one line.
- Bold, italic and struck text keep their marks. A link keeps its target only
  if that is `http`, `https` or `mailto` with no space or angle bracket;
  otherwise its text stays and the link goes.
- Text is escaped where Markdown or the renderer's extensions would read it:
  `$` would be maths, `|` a cell, a leading `#` a heading. As few characters as
  that, because reading aloud reads the same text.
- Deleted text of tracked changes is left out; inserted text is in.

## Bounds

The file is read whole up to 64 MB, because a ZIP's index is at its end. Each
XML part is refused above 32 MB unpacked, whatever the ZIP's header claims, and
a part carrying a document type declaration is refused, so the XML parser has
no entity to expand. The Markdown stops at the viewer's 1 MB on a whole block
and says it was cut.

## What it is not

- **No source.** The Markdown is a rendering, so the file offers no `text`, has
  no text for the editor, and the panel has no View as text.
- **No pictures.** They are counted and the count is the document's notice.
- **Not `.doc`, `.odt`, `.rtf`.** Other containers, other readers.
- **Not searched by content.** Search inside files reads text files line by
  line; a `.docx` is a ZIP to it.
- Footnotes, comments, headers and footers, text boxes and page layout are not
  read.

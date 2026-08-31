# Editing a file in place

## Problem

D47 gave a file node an ordered list of representations and a bounded content
read. That answered how to look at a file. It did not answer the next request:
a `.py` file should open the way it opens in an editor, with its own syntax
highlighted, and a JSON file should be correctable where it is wrong.

A bounded viewer cannot become an editor by adding a text box to it. A viewer
is allowed to return a prefix, a page, or a parsed tree — none of which can be
written back, because none of them is the document. Writing needs the whole
source, and it needs to know that the file has not moved on since it was read.

## Reading for an editor is not reading for a viewer

`SupportsContentEdit` is a separate capability with two operations, and a
source that has one has both:

- `read_editor_content(node_id)` returns the whole source as text, the
  filename, an optional language hint, an optional validation kind, an opaque
  `version`, and `writable` with a `reason` when it is false.
- `update_content(node_id, text, version)` replaces the document and returns
  the version it now has.

The two reads are kept apart deliberately. `read_content` may bound, page and
parse; `read_editor_content` may do none of those, because what it returns is
what a save will be diffed against. A source that offers viewers but cannot be
written answers 501 to the editor routes and keeps its viewers.

## The version is the source's, and opaque

The version is a SHA-256 of the bytes that were read. The client never
interprets it: it holds it and hands it back. Saving compares it against the
file as it is now, and a mismatch is a 409 with the file left untouched.

A hash rather than a modification time because a file source has no
transaction and no row version to borrow (D25 gives that to relations). Mtime
has one-second granularity on some filesystems and moves when nothing changed;
content is the only thing the answer is actually about. The cost is one read
of a document already bounded to 4 MB.

The size ceiling is the same on both sides. Above it the editor returns a
prefix with `writable=false` and says why, so a large file is still readable
and never half-written. A file that is not valid UTF-8 is returned with
replacement characters, unwritable, naming the byte that failed — the editor
cannot round-trip bytes it had to guess at.

## What a save may refuse

Before anything is written:

- the node must still be a file of an editable format, and not binary;
- the version must match;
- a `.json` document must parse, and every non-blank line of a `.jsonl`
  document must parse, with the position of the first failure in the message.

Validation belongs to the server even though the browser also lints. The
linter is a convenience; the file is the server's, and the only rule that
counts is the one applied where the write happens.

The write itself goes to a temporary file beside the target, is flushed and
synced, takes the original's mode, and replaces it with `os.replace`. A failed
write leaves the previous document intact rather than a truncated one.

Editing needs `write` on the connection. A reader who may only read gets the
document with `writable=false` and the reason, so a shared connection explains
itself instead of failing at the save.

## One mode, not two

A content tab opens the editor. There is no viewer/editor switch: a file that
can be opened at all is opened as its own source, and a file that cannot be
written says so in place. This is the whole reason the JSON tree was removed
from the screen — two representations of the same document, one of which
cannot be edited, is a choice the reader did not ask for.

**View as table** stays, because a table really is a different question about
the same file. It is offered where a projection means something: JSON and
JSONL. Text lost it: numbering the lines of a source file produced a table
whose only column was the line, and D47 had kept it only for the import path.

## The editor in the browser

CodeMirror 6, loaded lazily. The language is resolved by
`@codemirror/language-data` from the filename, with the source's hint taking
precedence — so `.py`, `.sql`, `.md`, `.vue` and the rest are recognised by
metadata that CodeMirror maintains, not by a table of extensions in this
repository. JSON and JSONL additionally get a linter: the standard one for a
whole document, and a per-line one for JSONL, so a single bad record is marked
without condemning the file.

The panel holds a draft and the baseline it was loaded from. Save is offered
only while they differ; re-reading a tab with unsaved changes is refused and
said out loud rather than silently discarding the edit.

## Rejected alternatives

- **Extend `ContentResult` with a `text` you can post back.** It would make
  every viewer look writable, including the paged and parsed ones that are not
  the document.
- **Use mtime or size as the version.** Both can be equal across a real change.
- **Trust the browser's JSON check.** The client is not the authority on what
  the file may become.
- **Write in place.** A crash mid-write leaves a truncated file, and the
  editor is precisely where a whole document is at stake.
- **Keep a viewer/editor toggle.** It puts the reader in front of a choice
  that only exists because the implementation grew that way.

## Known deviations and next slices

- The bounded content viewers of D47 are no longer shown anywhere. The routes
  and their models remain, tested, because paging a large JSONL file is the
  one thing the editor's ceiling cannot do; nothing in the interface reaches
  them today.
- A text file no longer declares a table representation, so it can no longer
  be chosen as the source of an import (D43). CSV, TSV, JSON and JSONL still
  can.
- The editor holds the whole document in memory on both sides, bounded at
  4 MB. A larger file is read-only.
- Nothing watches the file while a tab is open. A change underneath is
  discovered by the version check at save, not before it.
- Media, PDF and archives still declare no representation and so have no
  editor either.

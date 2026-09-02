# Opening a node's content

For adding a way to open a node that is not a page of rows — a document, an
image, a recording, a container walked into. Rows are
[relations.md](relations.md).

## D47. A node declares its ordered representations

The client neither infers a viewer from a suffix nor assumes that every readable
leaf has rows.

- `CatalogNode.representations` is the source's ordered answer to "how may this
  node be opened?". The first entry is preferred, the rest are explicit
  alternatives, and each has a closed `kind` and source-owned wording.
- The boundary has two operations. `SupportsFetch` answers a tabular question;
  `SupportsContent` answers `ContentRequest` with one bounded native
  representation. Opening a JSON document therefore cannot silently flatten it
  into rows, and asking for a table cannot silently fall back to text.
- A viewer unsupported by the node is 422; a source with no content viewers is
  the ordinary capability-level 501.
- Content results are discriminated unions rather than untyped payloads. JSON
  objects keep ordered entries, arrays keep nesting, scalars keep their kind, and
  numbers remain lexical text so a JavaScript number cannot round an identifier
  ([D23](relations.md)). An invalid JSON document stays in the JSON viewer as
  source text with the parser's position. JSONL is independent by physical line:
  one invalid or oversized line is shown and named without hiding the valid
  values around it.
- Bounds belong to the representation. Text reads at most 256 KB; a whole JSON
  document is parsed only up to 4 MB, because there is no honest partial tree,
  and above that the same viewer shows a bounded source preview and the reason;
  JSONL pages at most 100 records and 4 MB of source through a 1 MB line
  ceiling. All blocking file work runs in a worker thread.
- **View as table** is a retained alternative, not the meaning of opening JSON.
  It uses the fetch boundary: the whole file decides its columns before paging,
  so every page has one stable shape. A top-level object is one record, an array
  supplies records, and values without object keys use one `value` column. Capped
  at 4 MB. Offered by JSON and JSONL, and by CSV and TSV as their natural
  representation; a text file does not offer it, because numbering the lines of a
  source file produced a table with one column and no meaning.

Known deviations:

- **Catalog classification is by filename.** Opening the selected node checks its
  bytes, but listing a directory does not open every file, so a file with a
  misleading suffix can advertise a view that it later refuses.
- **Content reads are not cached.** Reopening or paging JSONL reads the file
  again; a file source has not opted into [D31](connecting.md), and what a save
  must match is versioned by D48's editor read instead.
- **The document viewers have no screen.** Image uses `read_content`, while text,
  JSON and JSONL open the D48 editor. Their bounded results remain tested,
  because paging a large JSONL file is the one thing the editor's ceiling cannot
  do.
- **The table projection equates an absent key with JSON null.** Both become the
  grid's `None`; the native JSON viewer preserves the distinction.

Spec: [Native file representations](../../superpowers/specs/2026-08-30-file-representations-design.md)

## D48. Editing a document is its own capability

A viewer is allowed to bound, page and parse, and none of those results is the
document. What the editor read returns is exactly what a save is compared
against.

- `SupportsContentEdit` is separate from `SupportsContent`, and a source may have
  either. `read_editor_content` returns the whole source, its filename, an
  optional language hint, an optional validation kind and an opaque `version`;
  `update_content` takes that version back and replaces the document.
- The version is a SHA-256 of the bytes read, and the client only carries it. A
  mismatch is 409 with nothing written. A modification time was rejected: its
  granularity hides a change and it moves when none happened. A file source has
  no transaction to borrow a row version from ([D25](relations.md)).
- Both sides are bounded at 4 MB. Above it the read returns a prefix with
  `writable=false` and the reason; a file that is not valid UTF-8 comes back
  unwritable naming the byte that failed, because bytes that had to be guessed at
  cannot be written back.
- Editing needs `write` on the connection (D33); a reader holding only `read`
  gets the document unwritable with that as the reason, rather than a failure at
  the save.
- Before writing, the source validates what the format promises: a `.json`
  document must parse, and every non-blank line of a `.jsonl` document must, with
  the position of the first failure. The browser lints as well, but the file is
  the server's.
- The write goes to a temporary file in the same directory, is flushed and
  synced, takes the original's mode and replaces it with `os.replace`, so a
  failure leaves the previous document rather than half of the new one.
- A content tab has one mode: opening a file opens its source, with no
  viewer/editor switch.

Known deviations:

- **Nothing watches an open file.** A change underneath is found by the version
  check at save, not before it.
- **Only text, JSON and JSONL are editable.** Everything the file source calls
  binary or opaque is refused, media and PDF included.
- **The document is held whole on both sides.** Above 4 MB the editor is
  read-only; there is no partial or streaming edit.

Spec: [Editing a file in place](../../superpowers/specs/2026-08-30-content-editing-design.md)

## D52. Seekable bytes are a ranged stream

[D49](actions.md)'s preview returns verified bytes whole, which is right for an
image and wrong for a recording: a player asks for the end of an MP4 first,
because that is where its index may be, and a browser that gets no answer to
`Range` will not seek and may not play.

- `SupportsContentStream.open_content_stream` answers with the verified media
  type, the filename, the exact size and a reader over an inclusive byte range.
  It is separate from `SupportsContentPreview`, and a source may have either.
- The HTTP belongs to the route: one `Range` parsed, `206` with `Content-Range`,
  `200` for no range or a multi-range request, `416` with `bytes */size` for a
  range outside the file, and `Accept-Ranges: bytes` always. Nothing about ranges
  reaches the adapter and nothing about files reaches the route.
- Authority is D49's ticket, because a media element cannot send a header, and
  the ticket names the representation it was minted for, so one for a sound file
  cannot be redeemed for a video.
- The media type is what the container proves, never what the suffix suggests.
  Verification is a bounded header read with no third-party decoder: an ID3 tag
  or frame sync for MP3; `RIFF`/`WAVE` with `fmt ` and `data` for WAV, which give
  channels, sample rate and an exact duration; `fLaC` with STREAMINFO; `OggS` for
  Ogg; `ftyp` for ISO base media, whose top-level boxes are walked by their sizes
  until `moov`, where `mvhd` states the duration and `tkhd` the picture size; the
  EBML header read to its `DocType` for Matroska; and `%PDF-` within the first
  kilobyte. What a container does not state is absent rather than guessed.
- A PDF is rendered by the application with `pdf.js` — pages to a canvas, no
  annotation layer, no forms, no scripting manager wired — rather than handed to
  the browser's own viewer, which understands all of those. The only thing
  besides pixels reaching the DOM is the text layer, positioned over the page, so
  selection and find work without markup crossing. Pages render as they are
  scrolled to, through the same ranged route.

Known deviations:

- **A stream has no byte ceiling.** It is ranged and chunked, so what is held is
  one chunk. Concurrent streams are not pooled per user, as archive staging is
  not ([D49](actions.md)).
- **Codecs are not verified, only containers.** A file whose container is sound
  and whose codec this browser lacks fails in the player, and the panel shows
  that failure rather than predicting it.
- **Duration is absent for Matroska and Ogg.** Both keep it where a demuxer
  reads, not in a header this slice parses.
- **No posters, waveforms, captions or chapters**, and no transcoding.
- **AVI has no viewer.** No browser plays it; it stays downloadable.
- **A PDF shows no annotations, links or forms.** They are the active part of the
  format.

Spec: [Playing media, and reading a PDF](../../superpowers/specs/2026-08-31-media-and-pdf-viewers-design.md)

## D51. A file that states its schema is a dataset

Parquet declares its columns, their types and its exact row count; a workbook
declares nothing as a whole, because it holds several sheets and one has to be
chosen before rows exist. The choice is made in the catalog rather than in the
request, so no generic contract learns that one file can hold several tables —
which is what the old `sheet_title` parameter did to every caller.

- An `.xlsx` or `.xlsm` file has children: listing it opens the workbook once and
  answers with one node per worksheet, in workbook order, each declaring `table`.
  `FetchRequest` keeps its single opaque `node_id`.
- `dataset` is the node kind for a tabular member of a container file.
  Deliberately not a `file`: it has no bytes of its own, so rename, delete and
  download are ruled out by the kind their `applies_to` already names.
- A sheet's id is the workbook's id plus the sheet's one-based position — a
  position, because a sheet title is written by a person and need not survive the
  containment rule of [D8](contract.md). A node id is split at most once, and only
  when the whole of it names nothing on disk, so a directory named `book.xlsx`
  holding a file named `1` keeps its ordinary meaning.
- A Parquet file is one dataset in one file, so it stays a `file` node declaring
  `table`.
- A CSV or TSV states no source types, but its header is addressable and its
  on-disk representation is safely rewritable within the upload bound. It
  declares editable, insertable and deletable rows with versioned handles; each
  rewrite stages a complete replacement beside the file and publishes it
  atomically, and a handle names the row position and the file version, so an
  external edit makes a stale write conflict. Its relation model offers only
  add, rename and drop of a text column.
- What only a format knows travels typed in `RelationModel.dataset`: a
  discriminated union whose Parquet member states rows, row groups, compression
  codecs, writer and format version, and whose worksheet member states title,
  position, sibling count, hidden state and declared used range.
- `CatalogNode.describable` says which node can be described, instead of the
  client deciding from the kind. `schema_name`, `owner`, `persistence` and
  `Column.storage` are relational vocabulary a file does not have and are absent
  rather than filled with something plausible. `RelationKind` gains `dataset`.
- Nothing reads a whole file to answer a bounded question. A Parquet page is read
  from the row groups it falls in, located through the footer. A worksheet
  streams through the read-only iterator and stops one row past the page. Because
  XLSX is a zip, the central directory is read first and a workbook declaring
  more uncompressed bytes than the ceiling is refused before a byte is inflated:
  64 MB encoded, 512 MB declared, 10,000 entries, 1024 columns.
- Parquet columns keep their declared types; worksheet columns are text, because
  Excel types cells rather than columns, so a type read off one page would change
  with the page.

Known deviations:

- **A formula cell shows the value the spreadsheet last saved.** The workbook is
  opened with `data_only=True`, and no formula engine is run.
- **Paging deep into a sheet walks the rows before it.** XLSX has no row index.
- **`.xls` is not read.** The legacy binary format needs a different library; it
  stays opaque and downloadable.
- **A sheet's node id follows its position, not its title.** Reordering the sheets
  of an open workbook changes what a reopened tab shows.
- **Merged ranges, formatting and formulas are not carried.**
- **A directory of Parquet part files is a directory.** One dataset over many
  files needs a decision about schema unification.
- **The page reads every column.** Parquet can prune columns, but the grid's
  visible-column choice does not yet reach the reader.

Spec: [Parquet files and workbook sheets as declared datasets](../../superpowers/specs/2026-08-31-parquet-and-workbook-datasets-design.md)

## D53. An archive is a container of entries

A `.zip` is a directory that happens to be one file, so it is a container in the
sense D51 gave the word.

- Walking into it lists its children, and each entry is a node whose id is the
  archive's id plus the entry's path. Resolution splits an id at the longest
  prefix naming a container file on disk, so a directory called `backup.zip`
  keeps its ordinary meaning.
- An entry name goes through the containment rule of [D8](contract.md) — the same
  rule a name typed into a form and a filename inside a multipart upload go
  through, because zip-slip is an entry called `../../etc/passwd` and the whole
  value of that rule is that there is one of it. An archive holding a name that
  fails it is refused whole, with the name in the message: listing the rest would
  be a second rule, "mostly contained", and a reader could not tell that what
  they see is not what the file holds.
- Listing reads the central directory, which is metadata, so nothing is inflated
  and the only bound listing needs is the entry count — 10,000, the number
  [D49](actions.md) refuses to archive past.
- Reading one entry expands it into a temporary file bounded at 32 MB, and the
  viewer that asked reads that file under its own ceiling. Both ends are checked:
  the declared size before anything is read, and the bytes as they are written.
  Expanding rather than streaming is deliberate — every reader here reads a path,
  so one bounded temporary file lets text, Markdown, JSON, JSONL, the image
  viewer and the table projection all work inside an archive with no second
  implementation. It costs one write per open.
- A zip entry that says it is a symbolic link is listed, because it is in the
  archive, but declares no viewer and cannot be read: a source that will not
  follow a link out of its root on disk does not follow one written inside a
  file either. An encrypted entry is listed the same way.
- `entry` joins `dataset` as a kind of member, with `has_children` telling a
  directory inside the archive from a file inside it. Rename, delete, new folder
  and upload name `file` and `directory`, so an entry is out of all four without
  a rule of its own; download names `entry` and streams one entry's decompressed
  bytes.

Known deviations:

- **Only ZIP.** A tar has no index, so listing means reading it end to end and
  every entry read means reading it again.
- **Parquet, workbooks, media and PDF have no viewer inside an archive.** The
  first two seek around their own bytes and the others are streamed by range
  (D52); expansion answers neither.
- **A nested archive is not walked into.** It is an entry with no viewer.
- **Nothing is written into an archive**, and nothing is extracted out of one into
  the personal directory. An entry still opens in the editor as an unwritable
  document carrying the reason — the channel D48 already uses — because refusing
  it would take the reading away with the writing.
- **A directory inside an archive cannot be downloaded.** Building a zip out of a
  zip is a different result, and the action refuses rather than guessing.
- **An archive claims children by its name.** Bytes that are not an archive under
  a `.zip` name are found when the node is walked into, as D47 says of every
  misleading suffix.

Spec: [Walking into an archive](../../superpowers/specs/2026-08-31-archive-browsing-design.md)

## D71. An archive is made and taken apart by the same containment rule

Browsing an archive is ZIP only, and stays that way for the reason
[D53](#d53-an-archive-is-a-container-of-entries) gives. Packing and unpacking
are one pass over the whole file and have no such requirement, so the tar
family joins ZIP there: `zip`, `tar`, `tar.gz`, `tar.bz2`, `tar.xz` to make one,
and those plus the short spellings and the single-stream compressions — `.gz`,
`.bz2`, `.xz`, which are one file rather than a container — to expand one. All
of it is the standard library; nothing is added to the dependency list to open
what somebody received by email.

Consequences:

- **A name inside an archive is judged by the one rule.** Every member goes
  through `stays_inside_root`, and an archive holding one that escapes is
  refused whole — every member is judged before a byte is written, because
  somebody told "that was refused" must not wonder what landed first.
- **A link is not expanded and not packed.** A tar holding one is refused, as
  is anything that is not a plain file or a directory; `tarfile`'s own `data`
  filter runs beside this source's walk rather than instead of it.
- **The ceilings are the download's ceilings**: ten thousand entries and two
  gigabytes, applied to what an archive declares before it is expanded.
- **Packing takes a set and expanding does not.** Five files chosen for one
  archive are one archive ([D68](actions.md)); three archives to expand are
  three expansions, and one refused says nothing about the other two.
- **A refused expansion takes its folder with it.** Nothing half-extracted is
  left wearing the name somebody will look for, which is the same statement
  every other write in this source makes by staging beside its destination.
- **The client needed no code at all.** The menu, the form with its format
  select, the confirmation and the set transport all followed from what the
  source declares — which is what D9 and D56 are for.

Known deviations:

- **Encrypted archives, RAR and 7z are not opened.** None of the three is in
  the standard library.
- **An expansion goes here or into a folder of its own, and nowhere else.**
  There is no way to say which folder.
- **A `.gz` that is not a tar is classified as opaque in the catalog** but is
  still expandable: `formats.py` calls it a binary file, and `packing.py` knows
  it holds one stream. Two answers about one name, which agree today because
  they answer different questions.

Spec: [Making an archive, and taking one apart](../../superpowers/specs/2026-09-02-archive-packing-design.md)

## D57. Source-issued SQL is read-only content

A relation has no text file to save back, so pretending its DDL is a text
document would make a read-only derived document claim an update capability the
source does not have.

- A PostgreSQL relation declares two ordered representations: `table` remains
  preferred and `sql` is the explicit **View DDL** alternative. `sql` is its own
  closed representation and `SqlContent` its bounded result.
- PostgreSQL implements `SupportsContent` and issues recreate-oriented SQL from
  its catalogs. Names are catalog facts quoted with `psycopg.sql.Identifier`;
  types and expressions come from `format_type`, `pg_get_expr`,
  `pg_get_constraintdef`, `pg_get_indexdef` and `pg_get_viewdef`.
- A rows panel retains the exact ordered representations it was opened with and
  exposes the first content alternative under the source's wording, so a declared
  alternative is also reachable. A stored panel predating this decision restores
  without inventing one.
- The result is capped at 256 KB of UTF-8. Individual catalog expressions are
  clipped before crossing the connection and the assembled document is clipped
  again by bytes without splitting a character. A clipped answer remains `sql`
  and carries a notice; it never falls back to a different viewer.
- The SQL panel uses the same code editor surface for syntax and selection but
  fixes it read-only and calls `read_content`, never D48's editor or update
  routes.
- Every successful structure mutation invalidates that content query together
  with the relation model and rows.

Known deviations:

- **This is a recreate-oriented definition, not a backup.** It includes the create
  statement, constraints, independent indexes, owner and relation comment. Grants,
  triggers, rules, row-security policies, storage parameters, column comments,
  identity sequence options and dependent objects are outside one relation
  representation.
- **A partition child is stated as `PARTITION OF` plus its bounds.** Local column
  `WITH OPTIONS` and independently attached constraints are not reconstructed.
- **Old-style table inheritance is flattened.** The visible inherited columns and
  constraints are emitted as one standalone definition; the parent relationship
  is not.
- **Only one content alternative is surfaced from the grid.** If a source later
  declares several, choosing among them needs a source-worded menu rather than
  silently picking the first forever.

Spec: [PostgreSQL relation DDL](../../superpowers/specs/2026-08-31-postgres-relation-ddl-design.md)

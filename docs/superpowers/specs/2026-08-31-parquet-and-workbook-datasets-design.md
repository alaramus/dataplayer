# Parquet files and workbook sheets as declared datasets

## Problem

Every tabular file the source has read so far is a projection of text. A CSV
has no types, so D47 gives its columns `text` and says why; a JSON document is
a document first and a table only when asked. Parquet and XLSX are neither.

A Parquet file states its own schema, its row count and how it was written.
Reading it as text is impossible — it is a binary columnar container — and
guessing its types would throw away facts the file already carries.

A workbook is not one table at all. It holds sheets, and which sheet is meant
is a choice a reader makes before any rows exist. The old application answered
that with a `sheet_title` string beside every fetch and a `sheets_names` list
in the response metadata, so every caller of a generic read had to know that
one file format can carry several tables. The same request also read the whole
workbook into memory through `openpyxl.load_workbook`, and the Parquet path
read the whole file through `pandas.read_parquet` before slicing one page out
of it.

Three things are therefore needed: a place for a choice between sheets that
does not add a parameter to the generic fetch, honest types and metadata that
the format already states, and bounds that hold for a file whose compressed
size says nothing about its cost.

## A sheet is a node, not a parameter

The catalog already answers "what may be opened, and what is inside it". A
workbook uses it: an `.xlsx` file has children. Listing it opens the workbook
once and returns one node per worksheet, and each of those nodes declares the
`table` representation. Selecting a sheet is therefore walking into a file, and
the generic `FetchRequest` keeps its single opaque `node_id`.

The new node kind is `dataset`: a tabular member of a container file. It is not
a `file` — it has no bytes of its own, cannot be renamed, deleted or
downloaded, and the action set says so by kind alone, without a new rule. The
sheet's node id is issued by the source and is the workbook's id plus the
sheet's one-based position among the worksheets. The client neither composes
nor reads it (D21); the position is used rather than the title because a sheet
title is written by a person and need not be a plain path segment, while the
containment rule of D8 judges every segment of a node id.

Resolution splits a node id at most once: if the whole id names something on
disk it is a path, and only when it does not is the last segment considered as
a member of the file named by the rest. A directory called `book.xlsx` holding
a file called `1` therefore keeps its ordinary meaning.

A Parquet file is one dataset in one file, so it stays a `file` node with the
`table` representation. A directory of part files is a dataset in some other
tools; here it is a directory, and making it one dataset needs a decision about
schema unification that this slice does not take.

## The source says whether a node can be described

`relation-model` is the existing route for "what is this made of", and a
Parquet file and a worksheet both have an honest answer: declared columns with
declared types. Until now the screen decided what could be described from the
node's kind, which was a rule the client had to hold about every source. It
becomes `CatalogNode.describable`, said by the source about the node.

Three fields of `RelationModel` are relational vocabulary that a file does not
have — `schema_name`, `owner` and `persistence` — and `Column.storage` is a
fourth. They become optional and absent rather than filled with a plausible
lie. `RelationKind` gains `dataset`, because a Parquet file is not a table, a
view or a foreign table.

## Format-specific facts travel typed

`RelationModel.dataset` carries what only this format knows, as a discriminated
union rather than a bag of strings:

- a Parquet dataset states its exact row count, how many row groups it is
  written in, which compression codecs appear in it, the writer that produced
  it and the format version;
- a worksheet states its title, its position among the sheets, how many sheets
  the workbook holds, whether it is hidden, and the used range it declares.

Adding a format means adding a member to that union and a branch to the one
exhaustive switch that renders it, which is a type error until it is written —
the same friction `CatalogNode` uses.

## Bounds

Nothing here reads a whole file to answer a bounded question.

A Parquet page is read from the row groups it falls in: the footer says how
many rows each group holds, so groups before the offset are never touched. The
footer is metadata, read without decompressing a single page.

A worksheet is read through `openpyxl`'s read-only iterator, which streams rows
and stops one row past the page. Skipping to an offset still walks the rows
before it, which is the cost of a format that has no row index.

XLSX is a zip, so it has the expansion problem every zip has. The central
directory — metadata again — is read first, and a workbook is refused when it
declares more uncompressed bytes than the ceiling allows, before anything is
decompressed. The encoded file has its own ceiling, and so does the number of
columns, for both formats: a page of a thousand rows across sixteen thousand
Excel columns is bounded by the format and by nothing else.

A workbook is opened with `data_only=True`, which reads the values a
spreadsheet application last saved. A file written by a program that never
evaluated its formulas has no cached values, and those cells are empty. That is
the file's state, not a reading error, and inventing a formula engine to hide
it is not in this slice.

## Types, and what a cell says

A Parquet column keeps its declared type: integers, floats and decimals are
numbers, timestamps are datetimes, nested values are JSON, binary is binary.
Every value crosses the boundary as text (D23), through the same `encode_cell`
that PostgreSQL rows go through — it moves out of the PostgreSQL adapter into
`adapters/cells.py`, because the canonical rendering of a boolean, a timestamp
and a byte string is not a property of one driver.

A worksheet column is text, for the reason a CSV column is: Excel types cells,
not columns, so a type read off the page would change with the page. The values
themselves are rendered by the same canonical rules, so a date is ISO and a
number is not reformatted.

## What is deliberately absent

- `.xls`, the legacy binary format, is not read. It is a different container
  and needs a different library.
- Merged ranges, cell formatting, colours and formulas are not carried. The
  grid shows rows; a spreadsheet viewer is not this slice.
- A worksheet has no content viewer, no editor and no actions of its own.
- Neither format is written. Import (D43) can read from them, because import
  reads through the ordinary fetch, and neither accepts rows.
- A Parquet directory dataset, statistics-based filtering and column pruning by
  the grid's visible columns are all later work; the page reads every column.

## Tests

Backend: a Parquet file's declared types and exact row count; a page that
begins inside the second row group; a page past the end; a file with too many
columns refused; bytes that are not Parquet under a `.parquet` name refused
with a safe message; the union rendered for the relation model.

A workbook listed as children, sheets in workbook order with the hidden one
marked, a page from the second sheet, a member id whose position does not
exist, a member id under a real directory of the same name, a worksheet
refusing content, editing and every action, and a zip whose declared expansion
is over the ceiling refused before it is opened.

Frontend: a dataset node is a leaf that opens rows and offers structure; a file
that has children is walked into; the format facts of both unions render.

# Native file representations

## Problem

The file source originally treated “can be opened” as “can be fetched as
rows”. CSV fits that assumption. JSON, source code, images, audio, video, PDF
and archives do not. Making every file pass through the grid destroys the
shape the file actually has and makes future viewers an exception to a
tabular contract.

JSON exposed the mistake first. Flattening a document into columns is useful
for analysis, but it is not the same operation as viewing the document. A
nested object is a tree, a top-level scalar is still valid JSON, JSONL is a
sequence of independent values, and invalid JSON is source text somebody may
need to diagnose. None of those becomes clearer merely by assigning columns.

The design needs to answer two questions independently:

1. What is the best viewer for this node?
2. Which alternative transformations may the user explicitly request?

## A node publishes views, in order

Every `CatalogNode` carries `representations`. Each entry has a closed `kind`
and a human title. Order is part of the answer: the first representation is
what an ordinary open uses, and the remaining entries become explicit choices
inside that viewer.

The source publishes this list because only the source knows what it can
actually read. The browser does not map `.json` to a component and does not
branch on adapter type. That keeps a future object store, HTTP source or
notebook adapter free to offer the same representation under a completely
different node kind or identifier.

The first vocabulary is:

- `table` — the existing `FetchRequest` / `FetchResult` boundary;
- `text` — a bounded source preview;
- `json` — one structured JSON value;
- `jsonl` — a bounded sequence of independent JSON values.

It is intentionally extensible but closed in each release. Image, audio,
video, PDF, spreadsheet and archive kinds will be added only with a result
contract and a viewer that can keep the promise. Until then an opaque file has
an empty list: it remains in the catalog, and opening it explains that no
viewer exists.

## Content is not a fetch

`SupportsFetch` means rows: columns, filters, sorting, paging and row
capabilities. Native content has none of those meanings, so it gets a separate
`SupportsContent.read_content(ContentRequest)` capability and route.

`ContentRequest` names the opaque node id and one content representation.
Paging fields are used by record-oriented representations and ignored by a
whole JSON document or text preview, whose byte ceilings already bound them.
The adapter rejects a representation the node did not advertise. It never
answers with a different kind: a JSON request stays a JSON response even when
the document cannot be parsed, and a table request fails if a table cannot be
made.

This separation is what keeps **View as table** honest. It invokes `fetch`; it
does not change the meaning of opening the file.

## Native JSON

A JSON document opens as one recursively typed value:

- object entries retain source order;
- arrays retain their nested values;
- string, boolean, number and null remain distinct scalar kinds;
- a numeric token crosses as text, never through a Python or JavaScript float.

That last rule applies D23 to the viewer. The identifier
`10000000000000001` must arrive with every digit, just as it does in a
PostgreSQL JSON cell and in the optional table projection.

A whole document is parsed only up to 4 MB. JSON has no valid partial tree, so
sampling a prefix and presenting it as structure was rejected. Above the
ceiling the response remains `kind: json`, carries a bounded source preview,
marks it truncated where appropriate and says why it was not parsed.

Invalid UTF-8 or invalid JSON is not changed into rows or into the generic text
viewer. The JSON result carries the bounded source text and the precise parser
position. The viewer can therefore show what was received and why structure
is unavailable without changing tabs underneath the user.

## Native JSONL

JSONL and NDJSON are record streams rather than one document. Blank physical
lines separate records and are not records themselves. A request pages the
non-blank records, while every result retains its physical line number so an
error can be found in the source file.

Each line is parsed independently. One invalid line carries its source text
and notice; valid lines before and after it remain structured values. A line is
read through a 1 MB ceiling, including when the file contains no newline for a
long time, so `readline()` cannot allocate an unbounded value. An oversized
line is skipped to its terminator and represented as a named refusal.

The maximum page is 100 records and 4 MB of source, whichever comes first. The
first UI asks for 50 and advances by the number actually returned, retaining a
history of prior offsets so byte-bounded pages still move backward correctly.

## Native text

Plain text opens as text, not as a two-column grid of line number and content.
The preview reads at most 256 KB and reports truncation. A NUL-byte check keeps
an unknown binary file from being painted as text merely because its extension
was unfamiliar.

The numbered-line table remains available as an explicit alternative. It is
useful for copying, charting and moving bounded rows, but those operations no
longer decide the default viewer.

## Explicit JSON-to-table projection

The earlier record projection remains behind **View as table**. It has one
important invariant: the whole file decides its columns before a page is cut,
so page two cannot acquire a shape page one did not have.

For `.json`, a top-level array supplies records and any other top-level value
is one record. For `.jsonl` and `.ndjson`, every non-blank line is a record. If
all records are objects, columns are the union of their keys in first-seen
order. Otherwise one `value` column carries each value. Values retain their
JSON types where a column agrees, and mixed columns are text. Nested values use
compact lossless JSON.

This whole-file pass has a 4 MB ceiling. Invalid JSON, invalid UTF-8 or a larger
file refuses the table request with a precise reason. Falling back to numbered
lines was rejected because the user explicitly asked for a table of JSON
records, not for whatever shape happened to be available.

## Workspace behaviour

Opening a catalog leaf takes the first declared representation. A `table`
opens the existing rows panel. `text`, `json` and `jsonl` open content panels
in the same work role, so the generic workspace engine learns no application
kind.

Two representations of one node are different work and have different panel
identities. Opening **View as table** beside a JSON viewer therefore keeps both
tabs; it does not mutate the native viewer into a grid. Both tab icons can
reveal the same opaque node in its catalog, and each panel reloads its own
request.

The JSON component is recursive and collapsible. It renders scalar tokens from
their declared kind and text rather than feeding them through JavaScript
numbers. Nested branches start collapsed after the first structural level, and
a wide branch reveals at most 100 children at a time so the 4 MB transport
bound does not become an unbounded DOM. JSONL renders a sequence of those trees
with physical line labels and per-line notices. Text and invalid JSON use
`<pre>` as text with wrapping rather than injecting source as HTML.

## Rejected alternatives

- **Choose a viewer in the frontend from the extension.** That duplicates a
  source decision and cannot work for opaque ids or non-file sources.
- **Keep `content_kind` on files.** One kind can express only one viewer; it
  cannot say “JSON by default, table on request”, and it makes the contract a
  property of file nodes rather than all catalog nodes.
- **Return arbitrary JSON payloads.** A viewer would learn backend-specific
  shapes at runtime. Discriminated result models keep the generated client and
  every switch exhaustive.
- **Use the grid as a universal viewer.** It conflates content with rows and
  makes media, PDF and archives impossible without pretending they are tables.
- **Parse an oversized JSON prefix.** A prefix is not a JSON document and a
  partial tree would claim structure the source did not read.
- **Silently fall back when a projection fails.** The requested
  representation is part of the operation; changing it is a false success.

## Known deviations and next slices

- Catalog classification is by filename to avoid opening every file during a
  directory listing. The chosen reader checks bytes when the node is opened,
  so a misleading extension may advertise a view that is then refused.
- Object member order is preserved, but duplicate JSON object names have the
  ordinary parser behaviour: the last value wins. A lossless source editor
  would need a token-level model rather than a semantic JSON viewer.
- Content reads are not cached and files carry no version token. Reloading or
  paging can therefore observe a file changed between requests.
- Large whole-document JSON has a source preview but no structural navigation.
- Media, PDF, spreadsheet and archive representations are deliberately not
  advertised yet. They extend this same contract in later slices.

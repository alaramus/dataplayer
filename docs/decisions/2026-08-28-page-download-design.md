# Downloading the visible page, and the commands of an open table

## Problem

The user downloads a CSV not of the whole relation, which may be enormous, but
of exactly one bounded page of the grid. Every such download also stays in the
user's personal file space, grouped by connection. The structure command
belongs to a table that is already open, and therefore moves out of the catalog
row and into the grid header.

## The page contract

The download request carries the same `node_id`, `limit`, `offset`, filters and
ordered sort as the current `FetchRequest`, plus the tab title and the names of
the visible columns in their on-screen order. The `MAX_LIMIT` ceiling stays
shared with an ordinary read: a download has no "unlimited" of its own.

The server calls `SupportsFetch` again. The mechanism is therefore the same for
PostgreSQL, for a tabular file, and for any future source that already answers
with rows and columns. A separate `SupportsExport` capability is not needed: it
would repeat the tabular boundary that already exists.

Client rows are not accepted. Otherwise a browser could save arbitrary data
under the guise of a source read, and the server would lose the ability to
check which columns it holds. The requested visible columns are checked against
a fresh `FetchResult`; an unknown or repeated name is a 422.

## The file

One and the same file is written to
`<user-home>/downloads/<connector-id>/<safe-title>-<UTC timestamp>.csv` and
returned to the browser as an attachment. The name holds no client path
segment. Writing goes to a temporary `.part` and is renamed atomically, so an
interrupted operation does not look like a finished download.

The encoding is UTF-8 with a BOM, for practical compatibility with spreadsheet
editors. The header holds the visible columns in their on-screen order. SQL
null is written as an empty unquoted field and every other value is quoted, the
convention PostgreSQL's own `COPY ... CSV` reads back, so null stays distinct
from the empty string. The standard CSV writer handles quotes, commas and
newlines inside values.

Corrected during execution: this first specified `\N` for null. A cell whose
value is literally those two characters was then indistinguishable from a null,
which no round trip could recover.

## Interface

Download and Show structure sit in `GridHeader`. Download is unavailable before
a page has been answered successfully, and when there is no visible column. A
second press is unavailable while the file is being written; a success and a
safe failure are both reported by a toast.

Show structure opens the existing structure tab through a workspace action. For
a tabular source that can be read but not described, the command is not drawn.
The `describable` flag therefore travels with the rows panel from the catalog
node; it is not derived from the adapter type, and not re-checked by the name
of the node kind.

## The freshness race

A source may change between the page being shown and the download. The CSV
reflects the moment of the download. Reproducing the old pixels exactly would
need a source-owned snapshot or version token; sending rows that have already
been shown back to the server is not such a token.

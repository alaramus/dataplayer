# A reference the person draws

## Problem

D36 gave a row a way out: the source names its foreign keys, and following one
lands on the rows it points at. Everything that answer is made of is read from
the source, which is why it is safe — and which is also its limit. Two columns
that hold the same numbers are not a foreign key, so nothing joins them.

That is most of the data people actually work with. A `country_code` column in
PostgreSQL and a `code` column in a CSV of the same office's making; an
`order_id` in one database and the same id in another; a key that was a foreign
key before somebody dropped the constraint to make loading faster. The old
application answered this with a feature it called an external reference, and it
was used constantly.

The rewrite deferred it on purpose. The D36 spec says so in as many words: a
registry of links between arbitrary columns of arbitrary connections is a
separate feature with its own storage, its own owner and its own answer to what
a link between two different connections means. This is that feature.

## What the old application did

`ExtraReferences` was a table of the application's own: an author, a name, a
type, and two points, each a connector id, a schema, a document and a column.
Nothing was written to either source. Creating one took two steps in the UI —
mark a column here, walk to another table anywhere, mark a column there, then a
dialog with a `swap relation` button to decide which end was the key. Reading a
relation mixed the matching rows into its model as pseudo-constraints named
`EXT-KEY-FOREIGN` and `EXT-KEY-PRIMARY`, which the client turned back into an
arrow beside the column. Following one called `slave_table` on the far
connector, and a file connector answered it by reading the CSV and filtering it
in pandas.

The idea is right and is worth having. The implementation carried five things
this project does not repeat:

- the two points travelled from the browser as tab-separated strings, with a
  fabricated connector id in the envelope;
- the SQL that found them was assembled with f-strings guarded by a blacklist;
- nothing checked that either column still existed, or that the caller could
  read the far connection at all;
- the constraint was copied onto every column it touched, so a key over two
  columns became two independent links;
- following one went down a second read path — `slave_table` — with its own
  types, its own paging and its own idea of what a row is.

## The registry is the application's

A declared reference is a row in the application's database with two ends. An
end is a connection, a node in that connection, and one column of it. There is
no source side and no target side: both ends are navigable, and which one a
person is standing on is decided by which relation they are looking at. The old
`swap relation` button only chose which badge got drawn, and the answer to
following a key — the rows where this column equals that value — is the same
statement read from either end.

It belongs to the person who drew it. That is what the old application did, it
is the smaller claim, and it avoids inventing an answer to "whose is a line
between two connections that two people can both see". A reference is visible
only while both of its ends are still readable by that person: a revoked grant,
a disabled connection or a deleted one takes it off the screen rather than
leaving an arrow that answers 403.

One column at each end. A composite declared key would need a column-pairing
screen and has no demand behind it; a real composite key is D36's business and
is read from the source.

## What the client sees, and what it sends back

Nothing new. A declared reference reaches the grid as an ordinary
`FetchResult.references` entry — a name, its one column, and a title for the
target — so the arrow, the tooltip and the click are the ones D36 already built.
The name is issued by the application and says which reference and which end is
being stood on, so a node linked to itself still offers two distinct ways out.

The follow route recognises the names it issued and answers them itself, without
asking the adapter. That is a lookup rather than a guess: the name carries the
reference's own id, and an adapter cannot produce one because the prefix is
reserved.

## Checked against both sources, twice

Everything D36 does for a real key is done here for a declared one, at both
moments that matter.

When the reference is made, both ends are read: the caller must hold `read` on
each connection, each node must exist and be readable as rows, each named column
must be among the columns that node states, and each must admit equality
lookup. A source that cannot look a value up in a column cannot be an end of a
reference, and saying so when the reference is drawn is better than drawing one
that fails on every click.

When it is followed, the far end is read again. The grant may have gone, the
connection may have been switched off, the file may have been rewritten with
different headers, the table may have lost the column. The predicate is built
from that reading, never from the request, and it is an equality filter in the
same closed vocabulary a typed filter uses — which the target's own fetch
validates a second time anyway. The application composes no SQL, and takes no
identifier from the client but the reference's own name.

The two answers stay the ones D36 defined. A row whose cell is empty names
nothing and gets `NoReferencedRows` with a reason; a column that has stopped
admitting equality gets the same. Neither is a failure of the request.

## Landing in another connection

`ReferencedRows` said where to go but not whose it was, because until now the
answer was always the connection that was asked. It now names the connection
too, filled in by the route rather than by the adapter: an adapter knows itself
and not its identity, and the route is the one place that knows which connection
it just asked. For a key inside one source that is the same connection it always
was; for a declared reference it is the far end.

The workspace opens the target's tab in that connection, exactly as the catalog
opens one, and leaves the predicate where the tab picks it up — the mechanism
D36 already has, with the connection now taken from the answer instead of from
the tab the click came from.

## The file source has to be able to look a value up

The reference this feature exists for points at a CSV, and the file source
refused every filter: it has no index, and a page of it is whatever the reader
read. Refusing to sort remains right — a sorted page needs the whole file
ordered — but refusing to filter meant the arrow could be drawn, the tab could
be opened and the fetch behind it would be rejected.

So the file source now filters by equality, and only by equality. It is applied
where the rows are read, on the canonical text the page already carries, so a
filtered page is the same page as an unfiltered one with rows left out — no
second reader, no typed reinterpretation of a CSV, no ceiling that silently
truncates the answer. It costs a scan, which is what paging a file already
costs: the tenth page of a delimited file walks the nine before it.

Paging over a filter counts matching rows, and `has_more` means another matching
row exists. Row handles carry the row's real position in the file rather than
its position on the page, because a page of matches is not a window into a
contiguous run and an edit must land where the row actually is.

Equality alone is deliberate. `contains` over a text file is a different feature
— it is a search, it wants its own answer shape, and the roadmap already says so.
Null tests are left out because an empty cell in a delimited file is exactly the
ambiguity D45 spent a decision on, and a filter that has to answer "is this null
or empty" would be answering it for the file source alone.

## Deliberate boundaries

- **One column each end**, as above.
- **Private to its author.** Sharing one is a question about ownership between
  two connections, and it can be answered when somebody wants it.
- **No reverse search.** A declared reference is drawn between two named nodes;
  finding every node in a schema whose column might match is the search D36
  deferred, and this feature does not need it.
- **No editing through one.** Picking a value from the far end instead of typing
  it belongs to the cell editor, the same conclusion D36 reached.

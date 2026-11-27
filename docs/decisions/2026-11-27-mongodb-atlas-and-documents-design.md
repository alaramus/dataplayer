# MongoDB Atlas, and documents cloned, added and deleted

Three requests arrived together: reach a MongoDB Atlas cluster, choose how
many documents a page of the document view holds, and delete and clone
documents there, with a clone in the grid as well.

## D457. A MongoDB source may name a DNS seed list

Atlas gives an address of one form, `mongodb+srv://cluster0.abc.mongodb.net/`:
a name whose SRV records list the members of a replica set and whose TXT
record names the set and the authentication database. D283 refused it,
because a client made with `directConnection` speaks to one server and a
tunnel's end must not be traded for the names a set calls its members by.

A seed list is the opposite of that, and the two are kept apart rather than
merged: the form gains a switch, "DNS seed list (mongodb+srv)". With it on,
the host is the seed list's name, the port is not used, the client is made
from the `mongodb+srv://` address without `directConnection`, and the driver
discovers the members and writes to the primary. With it off nothing changes.

- **No tunnel.** The members the records name are reached directly; a
  tunnel reaches one address. The form refuses both together.
- **TLS as the address says.** A seed list implies TLS in the driver; the form
  still says it in its TLS block. A pasted `mongodb+srv://` address fills
  Verify full unless it says `tls=false`, and an address composed for a
  person or a program says `tls=false` when the form turned TLS off.
- **Users in `admin`.** Atlas keeps its database users there and its TXT
  record says so; a pasted address without `authSource` fills `admin` rather
  than the database in its path, which a one-server address uses.
- **The seed list is resolved by the client as it first connects**,
  asynchronously, so making a client stays free of DNS.
- The console, a backup and Copy tables compose the same address; the server
  Copy tables names is the seed list's name.

Atlas answers its own refusals — a wrong password, a command its tier does
not allow — with code 8000 (`AtlasError`) and a sentence, not with the
server's codes. Classifying by code alone made a wrong password "the server
refused the request" with a reference. So code 8000 alone is told apart by the
opening words of its text: `bad auth` is an authentication failure, an
unauthenticated command is a missing password, and everything else says Atlas
does not allow it on this cluster. The text is read and never shown.

The shared tiers refuse what a server of one's own allows: creating users,
server-side JavaScript (`$where`), reading the server's own collections,
`$currentOp` for others' operations, renaming a collection into another
database. Those are known deviations, said in Atlas's refusal; the suite marks
the tests that need them and skips them when it runs against a seed list.

A seed list's address names no server to knock on, so the test registry
counts one as answering when it is set; running the MongoDB suite against
Atlas is setting `TEST_MONGODB_URL` to its address.

Rejected: parsing a `mongodb://` seed list of several hosts. Nobody asked, and
it raises the question of which member a tunnel reaches.

## D458. A ticked row can be cloned into the row being inserted

The grid gains Clone beside Insert: with one row ticked, the insert row opens
filled from it. It is pasting a copied line into the insert row, fed from the
page instead of the clipboard, so the owner reviews and saves the clone as
any new row, and nothing is written until then.

A clone must not repeat the key the source would make, or it fails (a serial)
or, worse, means something else (MongoDB's `_id`). `insertable` cannot say
it: a serial and `_id` are both insertable. `has_default` cannot either: a
ClickHouse column always has one, and so does MongoDB's every field. So
`FetchColumn` gains `assigned_on_insert` — PostgreSQL's identity and
`nextval(…)` defaults, MySQL's auto-increment, SQLite's rowid alias, DuckDB's
`nextval(…)` defaults, MongoDB's `_id` — and a clone leaves those out, naming
them the way a paste names what it left to the source. An empty cell is left
out too: on MongoDB it is a field the document lacks, and writing null into
every one would give the clone fields its source never had.

## D459. The document view chooses its page, adds, clones and deletes

- **Page size.** 10, 20, 50 or 100 documents, 20 by default, remembered for
  every collection as the grid remembers its own. Not the grid's 50–500: a
  document is the height of many rows.
- **Delete** sits beside Copy and Edit, asks first, and goes through the grid's
  `DELETE /rows` with the document's handle, so D287's conflict check holds.
- **New document and Clone** open one editor above the list. Clone fills it
  with the document without its `_id`; Insert sends the text to
  `POST /connectors/{id}/documents/new`, which `SupportsDocuments` now
  answers with `insert_document`, and the source writes it as written: a
  value keeps the type its relaxed Extended JSON names, and the driver makes
  the `_id`. The clone's text is written from the tree the page already holds
  rather than parsed from its text, because the tree keeps a number's digits
  and `JSON.parse` would round a 64-bit one.
- A page says `insert_supported` apart from `change_supported`: a time series
  takes new documents and changes none.

Rejected: cloning on the server in one step. The owner would then have to find
the copy and edit it; Compass opens the copy in an insert window for the same
reason.

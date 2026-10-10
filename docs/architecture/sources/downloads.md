# Downloads and reports

Taking a file away from a source, asking something before it is made, and a
report a source publishes about itself. What an action is, and how one is
declared, is in [actions.md](actions.md); the grid's own current-page download
is in [../grid.md](../grid.md).

Decisions here: D49, D73, D55.

## D49. Download is a source-declared action

Download is not a property of a file node or its viewer, so every adapter uses
the same Actions menu without an adapter-name or action-name branch.

- A source declares an ordinary action named `download`, and the callable action
  implements `ProducesDownload`. The listing derives `downloads` from that
  protocol, as it derives file upload and preview transports.
- The action receives the whole non-empty selection once. The file source returns
  one selected file unchanged; more than one node, or any selected directory,
  becomes one recursive ZIP — `<directory>.zip` for one folder and
  `download.zip` for a set — with empty directories retained.
- ZIP staging runs in a worker thread and a temporary file, with ceilings of
  10,000 entries and 2 GiB of uncompressed source bytes; symbolic links and
  ambiguous duplicate top-level names are refused. The archive is removed after
  the stream closes.
- The authenticated request issues a signed one-minute ticket containing the
  user, connector, action and opaque node ids. Following it with a normal browser
  navigation re-checks the user, access, enabled connector, action and every
  target before asking the source for `ActionDownload`. A server path never
  enters the ticket or the client.
- `image` is the first binary `NodeRepresentation`. The catalog classifies PNG
  and JPEG by name, because listing must not open every file, while the content
  read reads the header with Pillow and returns the MIME type, width, height and
  byte length it states. Its dedicated preview ticket verifies the bytes whole
  and returns them inline with `nosniff`; it is not the download action's
  ticket or transport.
- Preview has two independent ceilings: 20 MB of encoded bytes and 40 million
  decoded pixels. The verified bytes are the bounded bytes returned, so a file
  cannot change between checking and rendering. A single-file action stream is
  yielded in 256 KB chunks and never assembled in Python or JavaScript.
- The first viewer accepts only PNG and JPEG. GIF and WebP need animation and
  frame bounds, SVG an active-content decision, TIFF and icons their own format
  behaviour. All can still be selected for Download.

Known deviations:

- **Tickets may be replayed until they expire.** Every redemption re-checks
  current access, the action and its targets, but the signed token is not
  consumed.
- **Archive staging has no per-user or process-wide quota.** Each result has hard
  entry and source-byte bounds, but concurrent staging is not pooled.
- **Preview returns the bounded original image, not a thumbnail.** A later
  source-owned thumbnail can reduce transfer without changing the representation.
- **The JSON and JSONL bounded viewers remain API-only.** A large-document
  fallback still needs a screen that does not imply a partial document is
  editable.

Spec: [Download actions and bounded image content](../../decisions/2026-08-31-original-file-and-image-content-design.md)

## D73. A download may ask something first, and the model is written as code

`ProducesDownload` took the selection and nothing else, which is right while a
download is only a copy of what was picked. It is not enough when a download is
also a choice: the same relations written as a SQLAlchemy model, a Django model
or a DBML document are three different files.

So the capability takes the filled form too — `download(node_ids, raw)` — and
validates it with the action's own model, exactly as `perform` does. The signed
ticket a browser redeems carries the parameters, because the ticket is the
authority for one invocation and what was chosen is part of what was
authorised; a parameter in the URL is one a person can edit on the way.

Its first user is `describe_model`, offered on a schema and on a relation. The
renderers are pure functions over `RelationModel` in `adapters/model_code.py`:
a source that can describe a relation already publishes its columns, types,
keys and comments (D22), so this is a transformation of an answer that already
exists rather than a second description of a relation.

Consequences:

- **A schema stands for its contents**, which is what makes a diagram of a
  database one selection rather than forty.
- **A key is written by the published name of what it points at**, looked up
  among the relations in the document; a node id is opaque and reading one
  apart is what D21 forbids. A key pointing outside the document is left out of
  DBML entirely, because dbdiagram refuses a file that names a table it was not
  given.
- **Nothing generated claims to be a migration**, and every file says so in its
  first line. No singularisation — a singular is a guess about English, and a
  guess in generated code is a bug somebody has to find. Django models are
  `managed = False`, because the tables exist and Django did not make them.
- **A composite key is named as what it is.** Django has none, so the columns
  stay ordinary fields and `unique_together` says the rest, under the names the
  file actually gave them.
- **A written model is read before it is taken anywhere.** The action declares
  `x-ui-workflow: model-as-code`, and the client opens a screen of its own
  instead of the generic form: the three dialects as three names on one line,
  the document itself in the editor everything else reads code in, and Copy,
  Save and — for the one dialect a website draws — a door to that website.
  Loading a dialect, a refused dialect and its document keep one stable wide
  window; the editor takes the body above the fixed actions. Saving is the
  bytes already on the screen, so nothing is asked twice.
- **A download runs straight from the menu only when it has nothing to ask and
  nothing to show.** One with a form goes through the form; one with a screen
  of its own goes through that. Downloading a file somebody has not seen is
  asking them to open it in something else to find out what it says.
- **What a workflow screen chooses between is read off the schema**, never
  written out again: `x-ui-choices` carries the source's own words for each
  value — `dbml` is a value, "DBML (dbdiagram.io)" is what a person
  recognises — and the schema's default is what the screen opens on. A screen
  may name the field it is about, the way the file-to-relation screen names
  the ones it fills; it may not invent the values or the words.

Known deviations:

- **The dialects are three, and the obvious fourth is missing.** Alembic,
  Liquibase, Prisma and plain DDL are not written.
- **The document is fetched again for every dialect.** Pressing one of the
  three names is a round trip, and a dialect looked at twice is asked for
  twice.
- **A type is mapped by name, and a name this has never seen becomes text.**
  Every mapping is a best effort at a portable type, and a dialect-specific one
  would tie the file to one database.
- **There is a ceiling of two hundred relations** in one document, and a schema
  above it is refused rather than partly written.

Spec: [The model a source published, written as code](../../decisions/2026-09-02-model-as-code-design.md)

## D55. A source may publish reports of its own

Some of what a source knows about itself has no relation to open and never
will — tablespaces need `pg_tablespace` joined to `pg_roles` and `pg_class`
with `pg_tablespace_size` and a count of objects, and a reader cannot be asked
to write the join.

- A report is a named, read-only, tabular answer a source gives about itself. It
  is a catalog node of kind `report`, walked to and opened like anything else,
  and the section holding them is a report with children, the way a folder inside
  an archive is an entry with children ([D53](content.md)).
- The registry in `postgres/system_reports.py` holds one `sql.SQL` per report,
  written in this repository and never composed from anything a request carries.
  A node id selects one entry from a closed tuple; an id naming no entry is
  `NodeNotFound`, not a query.
- Filters, sorting and paging arrive as the ordinary `FetchRequest` and are
  validated against the report's own columns exactly as against a relation's,
  because the report becomes the `FROM` of the same builder —
  `SELECT … FROM (statement) AS report`. So [D2c](contract.md) holds unchanged.
- The columns are described, not declared. Listing them beside each statement
  would drift the first time a statement changed, so the statement is executed
  with `LIMIT 0`, psycopg's cursor description gives each column's name and type
  OID, and one lookup in `pg_type` turns those into the same `ColumnType` a
  relation's columns are built from. A report therefore sorts, filters, charts
  and downloads with no code that knows it is a report.
- Nothing is written through a report, and this needs no rule: `update`, `insert`
  and `delete` are refused for it as for a view, and no row handle is issued.
- The section's node id is `pg_dataplayer`. PostgreSQL refuses to create a schema
  whose name begins with `pg_`, so the id cannot collide with a schema a user
  could make — the server's own guarantee rather than a convention this project
  hopes holds.
- The six reports PostgreSQL publishes are processes, settings, tablespaces,
  roles, routines and extensions. Extensions is one report rather than two,
  because `pg_available_extensions` already states the installed version —
  and it is where extensions are installed and removed, on its own rows
  ([D70](relations.md)).
- A report is not a relation and answers no relation model: `describable` is
  false, and a subquery has no constraints, indexes or owner.
- **A report offers its own statement as a second representation.** It has no
  DDL — there is nothing on the server to recreate — but the question a person
  asks by opening a table's DDL is the same one they ask here: what is this,
  really. So a report is read as rows and as `sql`, and the statement is
  written in this repository, which is why answering costs no round trip. The
  same text is what "open as a query" puts in a console, because there is
  nothing to select *from*: a report is a statement, and wrapping it in another
  one would hide what it is.
- Another adapter gets this for nothing: a queue's consumer lag and a container
  runtime's process list are the same shape, and the kind is not named after
  PostgreSQL.

Known deviations:

- **A report has no row count and no estimate.** `pg_class.reltuples` is about a
  relation; running the statement to count would cost what reading it costs.
- **Following a foreign key out of a report is not offered.** The columns of a
  join carry no constraint, and inventing a reference from a column name is the
  guessing [D36](relations.md) exists to avoid.
- **Ordering falls back to the statement's own.** A report has neither a key nor a
  `ctid`, which is why every registered statement ends in an `ORDER BY` of its
  own.

Spec: [What the PostgreSQL adapter does beyond the table rounds](../../decisions/2026-08-31-postgres-system-operations-design.md)

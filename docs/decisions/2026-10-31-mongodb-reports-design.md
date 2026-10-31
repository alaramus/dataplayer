# MongoDB reports and actions

Decisions D289 and D290. The fifth slice of the MongoDB source (D283–D288):
what the server says about itself, finding and exporting, and the catalog's
actions.

## Reports as pipelines (D289)

PostgreSQL's and ClickHouse's reports are statements over system tables, read
as subqueries so the grid's filters and order are the server's. MongoDB's
counterparts are commands (`currentOp`, `usersInfo`) and aggregation stages
(`$currentOp`). The stages were chosen: a report is then a pipeline, and the
reader's filter, sort, skip and limit are more stages after it, built by the
same code that builds a collection's query (D285). A command's answer would
have to be filtered and paged here, which is a second implementation of what
the server already does.

A report has no documents to sample before it is read, so its columns and
their BSON types are written beside its pipeline; a filter value is read by
that type as for a collection.

Four reports were chosen for what a person asks of a server: what is running
(and stop it), who is connected, who may sign in, and what roles there are.
`serverStatus` and the startup options are documents of hundreds of keys,
better read in `mongosh` (D286) than as two columns.

## Search (D289)

There is no `information_schema` to narrow: `listCollections` filters by an
exact name or a regular expression, and a regular expression built from the
words typed would be a query composed from a client's text, which D2c refuses.
Listing every name and classing here is bounded by a ceiling and the clock,
and is what SQLite's and Redis's searches do.

## Actions (D290)

A database is never created on its own in MongoDB: `use shop` creates nothing
until something is stored. The form asks for the first collection's name,
saying why, rather than making a placeholder collection nobody asked for.

Moving a collection between databases is `renameCollection` across
namespaces, which the server does on one machine. Views cannot be renamed or
moved by it; making a view again from its pipeline under another name is a
`mongosh` command, and offering a rename that silently drops and recreates
would hide that its dependents are found by name.

A drop cannot be rehearsed: MongoDB has no transactional DDL on a server
alone. The preview reads what it can: the views whose `viewOn` is being
dropped, and how many documents go with it.

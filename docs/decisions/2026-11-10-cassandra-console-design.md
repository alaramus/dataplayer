# CQL in the console, cqlsh in a terminal

Decisions D343 and D344, the second slice of the Cassandra source
([A Cassandra and ScyllaDB source](2026-11-10-cassandra-source-design.md)).
The user chose both (2026-11-10): CQL in the query console with its results in
the grid, and the real `cqlsh` in a terminal.

## CQL in the query console (D343)

CQL is close enough to SQL for the console's editor, its result grid and its
history to serve it unchanged. What the source decides:

**Statements.** A tokenizer of CQL's lexical rules splits the text: strings
with doubled quotes, quoted names, `$$` function bodies and the three comment
forms hold semicolons that end nothing. A batch, `BEGIN … BATCH` to
`APPLY BATCH`, is one statement, because the server applies it as one. The
alternatives were splitting on semicolons — wrong inside a string — and a full
CQL grammar, which this console does not need: it needs boundaries and a class.

**Classes.** `SELECT`, `DESCRIBE` and `LIST` read; `INSERT`, `UPDATE`,
`DELETE` and a batch change rows; `CREATE`, `ALTER`, `DROP`, `TRUNCATE`,
`GRANT` and `REVOKE` change structure, the drops and the truncation being
destructive; `USE` is a session statement. cqlsh's own commands —
`CONSISTENCY`, `TRACING`, `COPY`, `SOURCE`, `PAGING` and the rest — are not
CQL, and the server would answer them with a syntax error that says nothing
useful; they are refused with a sentence naming cqlsh. Anything else is
refused as unknown.

**Modes.** Cassandra has no transaction and no read-only session. Read mode
runs only statements of the reading class, judged from the text. Auto-commit
runs everything, but a change runs alone, as on ClickHouse (D271): a run of
three inserts that failed on the second would have kept the first, and the run
would claim nothing was kept. The refusal names `BATCH`, which is how CQL
groups changes that must land together. There is no manual mode.

**Keyspace.** The keyspace chosen above the editor is the run's. A run has a
driver session of its own on the connector's cluster, opened on that keyspace,
so a `USE` inside it changes that run alone. The connector's shared session,
which the grid pages through, is never told `USE`.

**Parameters.** CQL's own named markers, `:name`, are the parameters. A
statement with any is prepared on the server, which says each marker's type;
the value typed in the form is read as that type — a scalar as a cell shows
it, a collection, a tuple or a user-defined type as JSON — and bound. No value
is ever written into the statement.

**Results.** Pages of five thousand are read until the row ceiling and one row
past it; the result's types come from the server's answer and the values cross
as the grid's do (D342). A refusal is the server's own sentence; its category
is read from the driver's exception class and, for "it is not there", from the
words of the sentence — only the category, never the text shown.

**Cancel.** CQL cannot stop a statement on the server. Stop lets the answer
go and reports the statement cancelled; the server finishes it. The time limit
is the driver's per-request timeout.

**Completion.** Keyspaces, the relations of the run's keyspace and the
columns of a relation the editor names, all from `system_schema`. **Open as a
query** writes a `SELECT` of every column with a `LIMIT`.

## cqlsh in a terminal (D344)

The same arrangement as `mongosh` (D286): a program in a container of the
vendor's image, its screen the terminal. Cassandra's image, because
ScyllaDB's starts its server whatever command it is given; cqlsh speaks CQL to
both. The node is named in `CQLSH_HOST` and `CQLSH_PORT`. The user and the
password go into cqlsh's credentials file, written inside the container with
mode 600 from a variable that is unset before cqlsh starts; cqlsh reads the
user through ConfigParser, so a `%` in it is doubled, and the password raw. A
line break in either is refused, because it would end the line of the file.
TLS uses the image's CA bundle. Through an SSH tunnel there is no terminal yet,
as for every other console.

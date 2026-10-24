# The SQLite console

Decisions D252 and D253. The second slice of the SQLite source: the SQL
console PostgreSQL has (D62–D66), on a SQLite file.

## Reading the text (D252)

PostgreSQL's console reads statements with the server's own parser and
MySQL's with sqlglot. For SQLite neither is needed whole. SQLite's grammar
names every statement by its first keyword, after an optional `EXPLAIN` or a
`WITH` clause, so the class follows from one keyword read off tokens — the
adapter's own tokenizer, already written for a table's `CREATE TABLE` text
(D249), which knows SQLite's three kinds of quoted names, its strings and its
comments. sqlglot was considered and set aside for classing: it fell back to an
opaque command on ordinary SQLite DDL (D249's spec).

Boundaries are the one place a semicolon is not enough: a trigger's body holds
semicolons of its own. SQLite answers the question itself in
`sqlite3.complete_statement`, so a semicolon ends a statement only where the
text before it is complete. A trigger is then one statement, and is refused by
name, as on the other sources.

PRAGMA is the statement that needs care. It reads, sets a connection's
behaviour, writes the file's header, or looks after storage, all under one
keyword. A pragma that only reports — `table_info(t)`, `integrity_check`,
`user_version` read bare — is a read; any pragma given a value is a session
statement, which no mode runs; `optimize`, `incremental_vacuum` and
`wal_checkpoint` are maintenance; anything else is unknown. `ATTACH` and
`DETACH` are session statements refused by name.

Parameters are `:name`, which SQLite binds itself, so the text goes to the
driver unchanged and the values go by name. Formatting is sqlglot's, and only
for reads and row changes: its layout of SQLite's DDL drops clauses it does not
model.

## Running it (D253)

SQLite's structure changes are transactional, unlike MySQL's (D233). So the
console behaves as PostgreSQL's does: a run is one transaction whatever it
holds, a held transaction may change structure, and a destructive change is
rehearsed by carrying it out and rolling it back, inside a savepoint when a
transaction is held. Only maintenance runs alone and outside a transaction,
because VACUUM cannot run inside one (D206).

A read runs on a connection with `query_only` set, in a transaction, so its
statements see one state of the file. The settings this application makes on
every connection — `query_only`, the checks against a crafted file, and
`foreign_keys` — may be read and may not be changed: the authorizer refuses
setting them whatever statement tries.

`foreign_keys` is on in every connection DataPlayer opens. SQLite leaves it off
unless a connection asks, so a file's declared keys are enforced only by the
programs that turn it on. The alternative, leaving it as SQLite ships it,
would let the console and later the grid write rows the file's own schema
forbids; a person reading `REFERENCES` in the DDL expects it to hold.

VACUUM attaches a nameless temporary database to rebuild the file into, so the
limit on attached databases is one rather than none, and the authorizer refuses
any attachment that names a file. `VACUUM INTO` names one and stays refused.

A held transaction keeps its connection between requests. A SQLite connection
belongs to the thread that made it unless told otherwise; this one is told, and
a lock keeps two calls from using it at once, so each statement may run on any
worker thread. The time limit and Stop are the same mechanism: the progress
handler interrupts the statement once its deadline passes or it is stopped,
and the run reports which.

A failed statement leaves a SQLite transaction open and usable. A full disk,
an I/O error and the like roll it back by themselves, and the transaction is
then marked broken, as is any run after which SQLite says no transaction is
open.

Results are read as positional rows. A result column's type is what its
values are, since SQLite keeps a class per value and a result has no declared
type to read (D250).

`EXPLAIN QUERY PLAN` answers with a parent and a sentence per step and no
costs, so the plan is a tree of those sentences. A row change is planned too:
planning it does not carry it out.

## Left for later

Other files in the same storage could be attached by name in a later slice,
under the same containment rule as the connection's own file. A large result
is read whole by the driver up to the ceiling, as on the other sources.

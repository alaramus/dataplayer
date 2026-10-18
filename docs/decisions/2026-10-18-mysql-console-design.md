# The MySQL console

Decisions D232 and D233. The second slice of the MySQL source: the SQL
console PostgreSQL has (D62–D66), on MySQL and MariaDB.

## Reading the text (D232)

PostgreSQL's console reads statements with pglast, the server's own parser.
MySQL has nothing like it for Python. sqlglot has a MySQL dialect and is
already a dependency, so its tokenizer draws boundaries and its parser
classes the statement.

sqlglot is not the server's parser, and it is generous: what it cannot model
it returns as a bare `Command`, and some text it reads as something it is
not — `FLUSH PRIVILEGES` and `TABLE t` both parse as an alias. So the rule is
the one D62 already states, applied strictly: `read` is granted to the shapes
that are reads and to nothing that merely parsed. A bare command is run only
for a few keywords sqlglot kept, each named with what it is: REPLACE writes,
OPTIMIZE is maintenance, CREATE, ALTER, RENAME, GRANT and REVOKE are
structure changes the vocabulary then judges by the word after the keyword.

The server is still the defence for a read. `START TRANSACTION READ ONLY`
refuses a write to a table, including one inside a stored function. It does
not refuse DDL, which MySQL commits before it runs; the class is what keeps
DDL out of a read, and a parse that does not produce a read shape is not a
read.

Parameters keep the spelling the console already shows, `:name`, read from
tokens so that `@a := 1` stays an assignment. MySQL's own placeholder `?` has
no name, and the console's bindings do. The driver escapes each value for the
server, minding NO_BACKSLASH_ESCAPES; every value is a string, as the
parameter model says, so a numeric context converts it and `LIMIT` refuses it.

Formatting showed the trap of a generous parser on its first test: the tree of
`FLUSH PRIVILEGES` is the tree of `FLUSH AS PRIVILEGES`, so a round trip that
compares trees approves the change. A statement is laid out again only when
its class is known.

## What MySQL commits by itself (D233)

D66 promises that an auto-commit run is one transaction, that a held
transaction ends when its owner says so, and that a destructive change is
rehearsed in a transaction and rolled back first. MySQL breaks all three for
DDL: a structure change commits the open transaction, runs, and commits
itself.

The alternatives were to run DDL anyway and say so afterwards, or to emulate
a rollback. Running it anyway makes "the run is one transaction" and "nothing
is committed by accident" false where they matter most. A rollback of DDL
cannot be emulated. So:

- a run holding a structure change or a maintenance command holds nothing
  else, and with others it is refused at the first statement;
- a held transaction refuses a structure change with the reason;
- the source does not claim a rehearsal. The console used to try one for
  every destructive statement and treat a refusal as a toast; it now reads
  `supports_rehearsal` and says in its question that the change cannot be
  tried out first.

A failed statement does not end a MySQL transaction, unlike PostgreSQL's, so
a held transaction stays usable after one. A deadlock does end it — MySQL has
already rolled it back — and the transaction is then marked broken.

The time limit is the adapter's. MySQL's `max_execution_time` bounds a SELECT
and nothing else, and MariaDB's `max_statement_time` is spelled differently;
one mechanism for both is a watchdog that kills the statement with
`KILL QUERY` from a second connection, the same thing Stop does. A statement
made only of `SLEEP()` returns early instead of failing when it is killed, so
the outcome reported is what the adapter did.

A document's schema context is MySQL's default database. It is set after the
name is found on the server, and put back before the pool has the connection;
a connection opened with no database cannot return to having none, so it is
closed instead.

Results are read as positional rows: a dictionary row merges two columns of
the same name. Whether a TEXT-typed column is binary is decided by what the
driver returned, since the wire type of TEXT and BLOB is the same.

## Left for later

`EXPLAIN ANALYZE` executes the statement and stays out, as PostgreSQL's does.
A large result is read whole by the driver before the ceiling is applied, as
psycopg's is; reading it unbuffered would leave a held transaction's
connection mid-result when the ceiling is reached.

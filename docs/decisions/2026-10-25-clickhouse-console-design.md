# The ClickHouse console

Decisions D270 and D271. The second slice of the ClickHouse source: the SQL
console PostgreSQL, MySQL and SQLite have — statements read and classed, runs,
Explain, completion, formatting and generated statements.

## Reading the text (D270)

MySQL's console reads its dialect with sqlglot (D232), and sqlglot has a
ClickHouse dialect, so the same shape is kept: the tokenizer decides where a
statement ends, the parser decides its class, and a statement the parser keeps
as a bare command is classed only by the keyword the parser kept.

ClickHouse has statements the parser does not model. Three were worth reading
off the tokens instead of refusing:

- `EXISTS TABLE t` and `CHECK TABLE t`, both reads that a person types often;
- `INSERT INTO t FORMAT JSONEachRow` followed by its rows, which is how
  ClickHouse's own documentation inserts anything that is not a `VALUES`
  list. Refusing it would leave the most common way of loading a few rows by
  hand out of the console.

`ALTER TABLE … DELETE` and `ALTER TABLE … UPDATE` are mutations: they change
rows and leave the structure as it was, so they are DML and need write access
rather than structure access (D160).

ClickHouse's EXPLAIN has variants that are not plans — the syntax tree, the
rewritten query, the pipeline, an estimate of rows and marks to read. They are
answers about a statement, run as reads; plain EXPLAIN stays Explain, the
command beside Run.

### Parameters

The console's parameters so far are `:name` (PostgreSQL, MySQL, SQLite) and
`$name` (DuckDB). Two ways were weighed for ClickHouse:

- `:name`, rewritten to `{pN:String}` — rejected: a String parameter is
  compared with a number column only by the server's implicit conversion, it
  cannot take part in arithmetic, and a person used to ClickHouse would be
  writing somebody else's syntax;
- ClickHouse's own `{name:Type}` — chosen. The server parses the value as the
  type the statement names and refuses one it cannot hold, nothing is put into
  the text, and a statement copied out of the console runs in clickhouse-client
  with `--param_name`. `QueryProfile.parameter_syntax` gains `named_braces`;
  the parameter form needs nothing new, since names come from the server's
  prepared script.

## Runs without transactions (D271)

ClickHouse keeps every insert, mutation and structure change the moment it
ends; its transactions are experimental and off by default. Auto-commit
promises that a run's changes are kept when the run succeeds. Two answers:

- run a script statement by statement and let a failure leave what came before
  it — rejected: the run would say it failed while some of it was kept, the
  same lie D233 refuses for MySQL's structure changes;
- a run that changes anything holds that one statement — chosen, extending
  D233 from structure to every change. A script of reads runs as one run, as
  before.

There is no manual mode and nothing is rehearsed: both rest on a transaction
that can be rolled back.

A read carries `readonly=2`. The class already keeps a write out of a read;
the setting is the server saying the same, so a statement the parser
misjudged still cannot write.

A mutation is queued by default and its statement returns before any row has
changed. `mutations_sync=1` makes the statement wait, so the row count after
it is true and its time limit covers the work.

The statement's time is limited by the server (`max_execution_time`), which
checks between blocks, and by the adapter five seconds later. Stop and the
adapter's own clock kill the statement by its query id from a request of
their own: over HTTP there is no connection to interrupt, and closing the
request stops only a read.

A result is read a line at a time and the request is closed once the row
ceiling is passed. `max_result_rows` with `result_overflow_mode=break` was the
alternative and was rejected: the server checks it in subqueries too, so an
`IN (SELECT …)` larger than the ceiling would quietly answer from part of its
rows.

`SET` and `USE` stay unrun, as they are on MySQL: each statement is a request
of its own, and an HTTP session to carry them would have to be held across a
run, the thing this slice does not have. `SETTINGS` on a statement and the
document's database do the same work.

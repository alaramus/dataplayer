# The DuckDB console

Decisions D392–D394. The second slice of the DuckDB source (D387–D391): the
SQL console PostgreSQL has (D62–D66), on a DuckDB file. Facts marked
*checked* were tried on DuckDB 2.0.0 on 2026-11-20.

## Reading the text with DuckDB's own parser (D392)

PostgreSQL's console reads statements with the server's parser, MySQL's with
sqlglot, SQLite's with a tokenizer of its own (D252). DuckDB's library brings
both halves in the package already here: `extract_statements` cuts a text
into statements and names each one's type, and `tokenize` gives the tokens of
DuckDB's grammar, so a semicolon in a string, a quoted name or a comment is
not a boundary (*checked*). Nothing is written to guess at DuckDB's grammar.

A statement's range runs from its first token to its last that is not a
comment or its semicolon. A text DuckDB cannot parse is cut at the semicolons
`tokenize` finds, each piece parsed alone, and a piece that still does not
parse is refused before anything runs, with DuckDB's own sentence — the
person learns the mistake without a run.

The class comes from the statement type DuckDB names, and from the first word
where one type covers several things:

- `SELECT` — which DuckDB also gives `FROM t`, `DESCRIBE`, `SHOW`, `SUMMARIZE`
  and `VALUES` — is a read; so is `PIVOT` (a `MULTI`), and `CALL` of a table
  function. `CALL`'s `CHECKPOINT` is maintenance, as are `VACUUM` and
  `ANALYZE`.
- `INSERT`, `UPDATE`, `DELETE` (with `TRUNCATE`) and `MERGE INTO` change rows.
- `CREATE`, `ALTER` (with `COMMENT ON`) and `DROP` change structure, for
  tables, views, indexes, schemas, sequences, types and macros. A secret is
  refused: this engine reaches no network to use one.
- `EXPLAIN` is an explain; `EXPLAIN ANALYZE` runs what it explains, so it is
  of the class of the statement after it.
- A `PRAGMA` that reports — `version`, `table_info`, `database_size`,
  `storage_info`, `show_tables` and the like — is a read. Any other is a
  setting.
- Refused by family, each with a sentence that says why: `ATTACH` and
  `DETACH` (one file per connection); `COPY`, `EXPORT DATABASE` and
  `IMPORT DATABASE`, which DuckDB calls a pragma (files are written through
  downloads, and a file is loaded with `INSERT … SELECT * FROM '~/file.csv'`);
  `INSTALL` and `LOAD` (no extensions here, D388); `SET`, `RESET`, `USE` and a
  setting pragma (the engine's settings are fixed, and the schema is chosen
  above the editor); `PREPARE`, `EXECUTE` and `DEALLOCATE` (parameters are
  `$name`).
- Anything else, `UPDATE EXTENSIONS` among it, is `unknown` and does not run.

Parameters are DuckDB's `$name`, the same spelling as SQL over files (D77);
DuckDB binds them by name itself.

## Running it (D393)

DuckDB changes structure inside a transaction and undoes it on rollback
(*checked*), so the console is PostgreSQL's (D253's argument): a run is one
transaction, a held one may change structure, and a destructive change is
rehearsed by being carried out and rolled back.

Every run, a read included, opens the file as the catalog does (D387) and
locks the engine to the owner's home (D388), so the console reads the files
of the person's storage as `~/…` and nothing else. DuckDB has no read-only
switch for one connection — opening the file read-only would be a second
configuration, which a shared instance refuses (D387) — so a read is the
class check plus a transaction that is rolled back.

A held transaction keeps its connection, and so keeps the file open: no other
program can open it until the transaction ends. The guide says so.

Any failed statement aborts a DuckDB transaction, as in PostgreSQL: the next
statement is refused until a rollback (*checked*), and a commit of it quietly
rolls back. The transaction is marked broken after any failure.

DuckDB has no savepoints (*checked*), so a change cannot be tried out inside a
held transaction and then undone without undoing everything before it. A
rehearsal there is refused, as MySQL's is (D233), and the destructive change
is run in auto-commit, where it is rehearsed. A rehearsal on a second
connection was considered and rejected: it sees the file without the held
transaction's changes, so it would describe a different database.

The schema search path is DuckDB's own `search_path`, which a session may
still set after the configuration is locked (*checked*); every name in it is
checked against the file's schemas first.

## Results and failures (D394)

A result crosses as text DuckDB writes, as the grid's does (D390). A read's
statement is bound once to learn its columns' types, which binds and does not
run it, and is then run wrapped: `SELECT CAST(#1 AS VARCHAR), … FROM
(statement)`, with `to_json` for a nested column and `0x` and hex for a blob.
Positional references keep duplicate and empty column names apart. This is
not only for consistency: the driver cannot hand a moment with a time zone to
Python without `pytz` (D390). A result that is not a read — a pragma, a
`CALL`, `RETURNING` — is read as the driver gives it and written as text here;
one holding a moment with a time zone fails with a sentence saying to select
it instead. A relation was considered for those and rejected: in DuckDB 2.0 a
relation runs its statement again every time it is read (*checked*), and
reading a `RETURNING` twice would insert twice.

A row change answers with DuckDB's `Count`, which is its affected rows rather
than a result.

A failure is DuckDB's own sentence, as a server's is on the other sources,
without the `LINE 1:` excerpt and with the owner's home written as `~`: the
sentence is about the statement, and the home is the one path it can name.
The category comes from the exception's class.

`EXPLAIN (FORMAT JSON)` gives the plan as a tree of operators, each with its
name and what DuckDB says about it, `Estimated Cardinality` among it; the raw
text is DuckDB's own drawing of the same plan.

## Left for later

The console of a file shared with another person reads that person's storage
as `~`, since the home is the owner's (D387); sharing is a later decision.

# Copying DuckDB tables, backing a file up, the lab, and a file seen from a file source

Decisions D400–D404. The sixth and last slice of the DuckDB source
(D387–D399): SQLite's D259–D263 told in DuckDB's terms. Facts marked
*checked* were tried on DuckDB 2.0.0 on 2026-11-21.

## Copying tables (D400)

A table is described from DuckDB's catalog, not from its text: each column's
type as `duckdb_columns()` spells it, its `NOT NULL`, its default and its
generation expression; the primary key, unique keys and checks from
`duckdb_constraints()`; the foreign keys as links; each index's keys, read
from the `CREATE INDEX` DuckDB keeps after `ON <table>`; the table's and its
columns' comments. A user type needs no description of its own: a column of
an enum is spelt `ENUM('sad', 'ok')` (*checked*), so the type travels inside
the column.

**An identity travels as a sequence of its own.** A default that is exactly
`nextval('<sequence>')`, naming a sequence of the file, is described as an
identity starting where the sequence would go next and stepping as it does;
the copy makes `<table>_<column>_seq` for it first, as the designer does
(D397). Any other default is copied as written, every fragment checked to be
one expression (D182).

**Rows travel as DuckDB's text.** The source casts every value to `VARCHAR`
and the destination casts it back with `CAST(? AS <type>)`. That round trip is
exact for every type DuckDB has but one (*checked*: integers to 128 bits,
decimals, doubles with `nan` and `1e+308`, blobs as `\xAA`, moments with a
zone, intervals, UUIDs, enums, nested lists, structs and maps with quoted
strings, `NULL` inside a list, bit strings, `TIMETZ`, `TIMESTAMP_NS`). The one
is `UNION`: its text does not say which member it holds, so a table with a
union column is refused, with the column named. Lines of the bulk format are
JSON arrays of those texts and nulls.

**One transaction, parents first.** DuckDB checks a foreign key at once and
cannot defer it (D397), and a key must name a table that already exists, so
the tables are made and filled in an order where a table comes after every
table of the copy it points at; a cycle cannot exist, since DuckDB adds no key
to a table that exists (D396). Tables, sequences, rows, indexes and comments
are committed together, or nothing is left. Indexes come after the rows.
Inside one file the rows are copied by `INSERT … SELECT`.

A link is kept pointing at its original only inside one file, and into the
same schema (D389): a copy into another schema can keep no link to an original.
Names of the copy and its indexes are compared without case.

## Backing a file up (D401)

DuckDB has no online backup a script can reach without DuckDB, and the tool
image must not carry a version of its own (D87). The file itself is the
backup: before the program is named, the connection opens the file and runs
`CHECKPOINT`, which writes the log into the file (*checked*: the `.wal` is
gone after it), and the program — a short script in `python:3.14-slim`, as
SQLite's (D260) — copies the file byte by byte, refusing while a `.wal` lies
beside it, since then another program is writing. A restore must begin with
DuckDB's header, `DUCK` after eight bytes (*checked*), is refused while the
file it replaces has a `.wal`, and is written beside the file and moved into
place, so a reader never sees half of it.

## The lab (D402)

A DuckDB source starts no server, so its sample is a file, as SQLite's
(D261): `lab.duckdb`, the lab of the other samples told in what DuckDB has —
enums, a struct, a list, a map, `HUGEINT`, `TIMESTAMPTZ`, intervals, JSON, a
blob, a sequence behind an identity, a virtual generated column, checks,
foreign keys, an index, a view, a macro, a second schema and a table with no
key. `app.seed_storage` writes it into the development superuser's storage,
and `bun run seed:connectors` adds the `duckdb-lab` connection to it.

## A DuckDB file in a file source (D403)

A file named `.duckdb` or `.ddb` offers the `database` representation as a
SQLite file does (D262): its tables and views with DuckDB's estimates, the
engine and the size, at most a thousand, a relation outside `main` named with
its schema. It is opened read only by an engine sealed as every connection's
is (D388), under a clock; a file without DuckDB's header says so. No rows:
they belong to a connection. The driver stays in its package, which registers
a reader for the `duckdb` engine; the explorer asks for the reader by the
file's format.

**Connect as DuckDB** on such a file drafts a DuckDB connection to it the way
Connect as SQLite does, owner only, in personal storage only. The database
panel offers whichever of the two the server offers for the file.

## A DuckDB database made here (D404)

**Create DuckDB here**, as Create SQLite here (D263): left to the server, it
makes `databases/dataplayer.duckdb` with the lab of D402; chosen, the folder,
the name, and the lab or an empty database. A taken name is numbered, a folder
outside the storage refused, a file whose connection was not saved removed. A
connection deleted with its file takes the `.wal` beside it too. There is no
WAL choice: DuckDB always keeps a log.

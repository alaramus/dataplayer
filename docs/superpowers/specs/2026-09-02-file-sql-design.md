# SQL over tabular files

## Goal

Phase 3.5's first item. The file source already reads CSV, TSV, Parquet, JSON
and JSON lines as relations; a person looking at three of them cannot join
them, group them or filter them by anything the grid's closed predicates do not
offer. Running a statement over them needs a query engine, and the source has
none.

The console, the documents, the runs, the bounded snapshots and the history are
already there and know nothing about PostgreSQL: `app/queries` talks to
`SupportsQuery` (D62) and the browser branches on no adapter name. So this is
one adapter capability, not a second console.

## The engine

DuckDB. It is the only embedded engine that reads all five formats natively,
and it is three separate commitments at once, which is why the roadmap said to
decide it before writing any of it:

- **a dependency** — 13 MB of compiled engine in the backend image, with its
  own release cadence and its own CVE surface;
- **a sandbox** — it reads files, installs extensions, attaches databases and
  writes with `COPY`. Every one of those is a way out of a personal directory;
- **a second dialect** — a second parser, a second set of statement classes, a
  second parameter spelling and a second vocabulary of refusals.

SQLite was the alternative and fails the first test: it reads none of these
formats without an extension, so the whole point would have to be built on top
of it. Reading the files in Python and running the SQL somewhere else is worse
still — it is a third implementation of what the grid and the engine both
already do.

The dependency is contained the way `psycopg`, `pyarrow` and `openpyxl` are:
`duckdb` is imported by `app/adapters/file/` and by nothing else, and
`.importlinter` fails on a violation.

## What SQL sees

**The relation named in a statement is a node id.**

```sql
SELECT * FROM "sales.csv"
SELECT * FROM "reports/2026/q1.parquet" WHERE region = $region
```

Not a path, and not a name invented for SQL. The alternative — stripping the
extension so a file is `sales`, or mapping folders onto schemas — invents a
second naming rule, and then two files called `sales.csv` and `sales.parquet`
need a third rule to break the tie. A node id is what the catalog shows, what
the client already sends everywhere else, and what one containment rule already
judges.

Nobody types it. `generate_query` writes the statement for a node, the same
command that already writes a bounded SELECT for a PostgreSQL table, and the
editor completes to the names the source lists.

Every name goes through `FileSession.resolve` — the same call the listing, the
download, the archive walk and the upload go through. A `..` segment, an
absolute path, a Windows drive reference or a symbolic link out of the root is
refused there, once, for every operation this source has.

**A name that does not resolve is refused before anything is opened**, unless
the text defines it as a CTE. This matters more than it sounds: with no view
registered under a name, DuckDB falls back to reading the name as a file path.
Refusing first means `FROM "C:/Windows/win.ini"` is answered by the source's
containment rule, in the source's own words, rather than by the sandbox.

**A qualified name is refused.** This source has no schemas, its `search_path`
is empty, and `main."sales.csv"` would be a second spelling of one thing.

**A table function is refused.** `read_csv('…')`, `glob('…')`, `range(10)` —
all of them, not a list of the dangerous ones. A table function is how a path
is written in this dialect, and admitting them would mean a client-supplied
path judged by DuckDB's containment rather than by the source's. One rule is
the whole point of the rule. `range(10)` is collateral damage and is worth it.

The check is structural, not a blacklist of names: the statement is serialized
to its parse tree by the engine itself, and a `TABLE_FUNCTION` reference
anywhere in that tree refuses the statement. A text the engine will not
serialize is `unknown` and is not run, which is what D62 already says.

## What may run

Read only. `statement_modes` is `["read"]`, and every other class is refused
with the family named:

| Family | Why not |
| --- | --- |
| `dml`, `ddl` | Writing to somebody's CSV through SQL is a different promise from reading it, and the grid already owns changing a file's rows and columns (D51) |
| `copy` | `COPY … TO` writes a file. Export is a capability with its own ceilings and its own streaming (D45) |
| `transaction`, `session` | The engine is thrown away after every run; there is nothing for them to be about |
| `explain` | Explain is a command of its own here, with its own result type (D65) |

Nothing is refused by reading the first word. The class comes from
`duckdb.extract_statements`, the engine's own parser, which is what tells a
semicolon inside a string from one between statements.

## Parameters

DuckDB spells a named parameter `$name`. It has no `:name` at all — the parser
rejects the colon outright — so the protocol's `parameter_syntax` gains a
second value rather than the source pretending. The names come from the
engine's parser, the values are bound, and a statement is given only the
bindings it uses; the engine refuses a binding it did not ask for.

The browser reads the spelling out of the profile. It already asks the server
where the statements are and what they name; the one place it assumed a colon
was the completion list.

## The sandbox

The refusals above are the rule. The sandbox is what stands behind them, so
that a hole in the parse is not the last thing between a person and the disk.

Each run gets its own in-memory database, and it is closed when the run ends.
After the views are registered — and only then, because registering them reads
the files — the configuration is closed:

```text
allowed_directories = [the connector root]
enable_external_access = false
disabled_filesystems  = HTTPFileSystem, S3FileSystem
autoinstall / autoload extensions = false
community and unsigned extensions = false
lock_configuration = true
```

`enable_external_access = false` is what turns `allowed_directories` from a
list into a restriction: on its own the list does nothing, which was worth
finding out by trying it. With both set, a read inside the root works and a
read of `C:/Windows/win.ini` is a permission error; `LOAD httpfs` is refused
even when the extension is already on the machine; and `lock_configuration`
means the user's own SQL cannot undo any of it, because `SET` is refused twice
over — by the class and by the lock.

Memory and threads are bounded, and there is no temp directory, so a runaway
aggregation fails rather than filling the server's disk.

## Being synchronous

DuckDB blocks. Every call — parsing, registering, executing, fetching — runs on
a worker thread, because a blocking call in a handler stalls the loop for
everyone.

That leaves cancellation, which cannot be a cancelled task: the thread would go
on reading. `interrupt()` is called on the connection from the loop, and the
thread comes back with an interrupt error. A timeout is the same call from a
watchdog. Which of the two happened is a fact the server holds rather than
something read out of the message, exactly as PostgreSQL's `57014` is told
apart by what this application asked for.

## Errors

Driver text does not cross. For PostgreSQL the reason is the password; here it
is the layout of the server — `Cannot access file "C:\Users\…"` is a sentence
about the machine, and this source's whole promise is that a person sees node
ids and never a path. What crosses is the exception's class as a code, a
category, one bounded line with the root redacted out of it, and nothing else.

## What is not in this slice

**A worksheet.** `.xlsx` needs DuckDB's `excel` extension, and downloading an
extension is precisely what the sandbox forbids. Reading the sheet with the
openpyxl reader this source already has and handing the rows to the engine
would work, but it materialises the whole sheet in memory, so it needs a
ceiling that refuses rather than truncates — a decision of its own, worth
making when somebody asks for it. Until then a worksheet is refused by name,
with the reason.

**A CSV's types differ between the grid and SQL.** D51 says every column of a
delimited file is text, because that is what makes a cell editable. The engine
sniffs types, so `amount` is a number in a query and text in the grid. Two
readers for two purposes rather than one answer computed twice: the grid's
answer is about editing, the engine's is about arithmetic.

**Formatting.** DuckDB has no formatter, so the source does not claim one and
the button is not offered. The profile is derived from what is implemented, so
this needs no saying anywhere else.

## Decisions

**D77. A file source's SQL names its own nodes, and nothing else.**
**D78. The engine is a disposable sandbox rather than a database the source
keeps.** Both are stated in [querying](../../architecture/querying.md).

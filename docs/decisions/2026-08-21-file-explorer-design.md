# File source

Date: 2026-08-21
Status: agreed
Subproject: 6

## Goal

A second source type, not SQL, to find out whether the abstraction leaks. The
catalog, `SupportsCatalog` and `SupportsFetch` were designed against PostgreSQL
alone, and until a source of a different nature is plugged into them, their
generality is an assumption, not a fact.

The user-facing side of the goal: every user has their own directory on the
server, creates a connector to it, walks the folder tree and reads files as
rows in the same grid as database tables.

## Why files and not SQLite

SQLite would have been cheaper and would have reused the whole shape of the
catalog and fetching, but that is exactly why it proves nothing: it is a third
SQL source. At most it would check the "no schemas" level in the tree and a
synchronous driver through a thread. A file source differs from a database in
everything that needs checking: node kinds, columns without types, no indexes,
no connection as a concept.

S3 would give the same check without reading the server's file system, but it
requires MinIO in compose and extra infrastructure in tests, while the user's
personal directory is something the application needs in its own right.

## What we learned about the old application

An analysis of `data_adapter/file_explorer/` produced six facts, and each of
them is closed by a decision here.

**Confinement to the root does not work.** `resolve_path` checks the path
against the root only when `connector_type == 'FileExplorer'`, and the
condition `not resolved.startswith(root) and not root.startswith(resolved)`
lets through any ancestor of the root — that is, climbing up to `/` is allowed
by construction. Apparently for the sake of the `.` and `..` entries, which are
mixed right into the catalog data.

**The node kind is stored in the `schema` key.** The value `file` or
`directory` in the field that holds the schema name for databases. This is
exactly the case because of which `CatalogNode` became a discriminated union.

**Fetching is a cascade of `if extension ==` with six branches.** Inside one of
them is `SELECT * FROM '{table}'` built by string formatting, and a
`create_query` that pastes the path into the SQL text.

**An error silently turns into a different response.** `except Exception` in
`fetch` returns the file as text; a catalog error returns the content of the
parent folder. Telling a failure from a success from outside is impossible.

**Formats are given by whitelists of extensions** (`TEXT_EXTENSIONS`,
`DATA_EXTENSIONS`, …), so a file without an extension or an unfamiliar config
is simply not read.

**All I/O is synchronous inside `async def`**: `os.listdir`, `open`,
`pandas.read_csv` — right in the handler.

## Boundaries

**The home directory.** The `USER_STORAGE_ROOT` setting; in compose, a volume
mounted into the backend container. The module `app/users/storage.py`:

```python
def home_dir(user_id: uuid.UUID) -> Path      # USER_STORAGE_ROOT / str(user_id)
def create_home(user_id: uuid.UUID) -> Path   # mkdir, mode 0700, idempotent
```

`create_home` is called from `users/crud.create_user` and from
`users/bootstrap.init_db` for the first superuser — otherwise existing users
would have no folder. Ownership of the directories stays in the `users`
module: the adapter knows nothing about users.

**How the root reaches the adapter.** The root is not an option: the client
must not be able to name it. In the registry the factory gets a second
argument:

```python
@dataclass(frozen=True)
class AdapterContext:
    home_dir: Path

Factory = Callable[[Any, AdapterContext], DataAdapter]
```

`build_adapter(adapter_type, options, context)` — the context is built by
`connectors/service` from the connector's `owner_id`, and for `check-draft`
from the current user. PostgreSQL ignores the argument.

The alternative — slipping the root into the options dictionary before
validation — is rejected: the options schema is at once the form in the
interface and the stored configuration, and a value computed by the server
would become both an input field and a database record in it.

The generalisation is made on the second use, not in advance: PostgreSQL did
not need a context, the file source needs one.

**Options of the file type** — one: `path: str = "/"`. The value is read as a
path relative to the home directory; `/` means the home directory itself. It is
never an absolute path on the server's file system.

**Path resolution.** `node_id` is a path relative to the connector root. Before
every operation: join with the root, `Path.resolve()`, check
`is_relative_to(root.resolve())`, otherwise refuse. `resolve()` expands
symbolic links, so a link pointing outside is cut off by the same condition,
not by a separate check. There are no `.` and `..` entries in the output:
navigating up is the interface's business, not the data's. Error texts contain
only relative paths.

**A path segment is a plain name.** Found during implementation: on Windows
`Path(root) / "C:" / "Windows"` silently throws away everything before the
drive and gives `root/Windows` — the path turns into another path without a
single error. So each segment is checked by the rules of both platforms at
once: a segment with a drive letter or a root is rejected, not reinterpreted.
The price is that a directory on Linux named like `C:` is unreachable; that is
cheaper than a `node_id` that means different things on different platforms.

**Kind of refusal.** A path leaving the root is a bad request, not a source
failure, so it gives 422, not 502. Today the catalog route catches only
`AdapterError` and answers 502; so in this subproject `SupportsCatalog` gets the
same promise `SupportsFetch` already has — `ValueError` for a request naming a
nonexistent or disallowed node — and the catalog route starts catching it. For
PostgreSQL this changes nothing.

There is exactly one boundary, set by the server, and it cannot be moved by an
option, by `node_id` or by a symlink.

## Catalog

Two new node kinds in the union:

```python
class DirectoryNode(BaseNode):
    kind: Literal["directory"] = "directory"
    modified_at: datetime | None = None


class FileNode(BaseNode):
    kind: Literal["file"] = "file"
    has_children: bool = False
    size_bytes: int
    modified_at: datetime | None = None
    content_kind: Literal["table", "text", "opaque"]
```

`has_children` on a folder is not "always yes": `os.scandir` and one step of the
iterator, so an empty folder is honestly shown as empty.

The order of the output is set by the server: folders first, then files, by
name within each. In the old application the order was whatever the OS
returned.

`content_kind` is determined by extension, without reading the content:
otherwise listing a folder of a thousand files would cost a thousand opens. The
rule is inverted relative to the old application: `csv` and `tsv` give `table`,
a list of known binary extensions (archives, images, audio, video, `pdf`,
`exe`, …) gives `opaque`, **everything else is `text`**. So `Dockerfile`, `.env`
and a file without an extension are read rather than filtered out by a
whitelist; reading will give an error if the inside turns out to be binary.

**A ceiling on a listing.** PostgreSQL has a bounded number of schemas, a folder
does not. More than 2000 entries in a directory is an `AdapterError` with a
plain message that paging of catalog children is not implemented. Silently
truncating the output is not allowed: that is exactly the kind of lie because of
which the old catalog returned the parent folder's content instead of an error.
The subproject makes the known deviation visible rather than fixing it.

## Reading

`postgres/fetch.py` builds SQL, `file/fetch.py` picks a reader by
`content_kind` — a mapping from a `Literal` to a class, so a forgotten kind will
not pass `mypy`. There is no branching on extension, as in
`_fetch_by_extension`.

- `table`: the first line is the column names; empty and repeated ones get a
  suffix. The type of every column is `text`, because CSV has no types. The
  delimiter is by extension; for `.csv` it is detected from the first line.
- `text`: two columns, `line_no` and `line`.
- `opaque`: `ValueError` → 422. The same answer is given for a folder and for a
  file that turns out to be binary (a zero byte in the first 4 KiB). No new
  error kind is needed: `SupportsFetch` already promises `ValueError` for a
  request asking for the impossible.

Both readers stream through the file: skip `offset` lines, take `limit + 1`,
the extra one gives `has_more`. The whole file never gets into memory. A deep
`offset` costs a pass over the file — a known price, written down here rather
than disguised.

All I/O goes through `anyio.to_thread.run_sync`. ruff catches `open()` in
`async def` (`ASYNC230`), but nobody catches `os.scandir` and `os.stat`, so the
rule is spelled out explicitly.

## Sorting and filters

A file cannot be sorted without reading it whole, and CSV columns have no
types, so `gt` and `lt` over them are meaningless. So `SupportsFetch` as one
indivisible capability leaks here, and this is recorded in data rather than by
silence:

```python
class FetchResult(BaseModel):
    ...
    sortable: bool = True
    filterable: bool = True
```

PostgreSQL does not change. The file adapter returns `False` and answers 422 to
non-empty `sort` and `filters`. The grid learns this from the very first
response and does not offer what is not there — the frontend still does not
branch on the source type anywhere.

The option "support everything by reading the file up to a size ceiling" is
rejected: the order of rows would depend on the file size, and one request
could eat hundreds of megabytes.

## Row count

`FileNode` has no `row_count_estimate`: it can only be learned by a pass over
the file. The grid currently takes the estimate from the catalog node — so it
will have to work without it too, paging by `has_more`. This is the main check
of the subproject: whether the abstraction leaks or not.

## Module layout

```
backend/app/adapters/file/
├── options.py    FileOptions: path
├── session.py    root, path resolution and confinement, check_connection
├── catalog.py    listing → DirectoryNode | FileNode
├── fetch.py      choosing a reader by content_kind
├── readers.py    CsvReader, TextReader
└── adapter.py    facade + register(name="file", ...)
```

The layout is the same as for PostgreSQL (R2b): the session separate, the
capabilities separate, the facade thin. For the file source the "session" is
the root and the path checks, and `check_connection` is "the folder is in place
and readable".

## API

No new endpoints. The existing ones work:

```
GET  /api/v1/adapter-types/            — the file type with its own schema
POST /api/v1/connectors/               — creating a file connector
GET  /api/v1/connectors/{id}/catalog   — walking the tree
POST /api/v1/connectors/{id}/fetch     — the rows of a file
```

The absence of new endpoints is part of the result: if the file source had
needed an endpoint of its own, the abstraction would have leaked.

## Interface

The connector form is not touched: the `file` type arrives from
`/adapter-types` with its own schema, and `SchemaForm` builds the `path` field
itself.

- `treeNodes.ts` — icons and captions for `directory` and `file` (size, date).
  The caption goes through the `QTree` header slot and is confirmed in the
  browser: `QTree` has no `caption` property, and captions computed once were
  never drawn, having passed the unit tests.
- `RowGrid.vue` — working without a total row count: when `row_count_estimate`
  is absent, the grid pages by `has_more`, showing neither the number of pages
  nor a jump to the end. Sorting by header is disabled when `sortable: false`.
  A file with `content_kind: "opaque"` is visible in the tree, but selecting it
  does not open the grid — a message is shown right away instead of a request.

## Sample files

There are no writes in the subproject, and a new user's home directory is
empty — so there is nothing to look at by hand or to run Playwright on. Next to
the existing `app/initial_data.py` comes `app/seed_storage.py`: it puts a set
of samples (`sample.csv`, `sample.tsv`, `notes.txt`, a nested folder, an image
as a known `opaque`) into the home directory of the given user. This is a
development tool and preparation for the e2e scenario, not part of the API.

## Verification

The tests run against `tmp_path`, not against an empty folder.

- escaping through `..` in `node_id`, through an absolute path and through a
  symbolic link outward — 422 both in the catalog and in fetching; a
  nonexistent node is also 422, not 502;
- an empty folder gives `has_children: false`; the order "folders, then files,
  by name";
- more than 2000 entries is an `AdapterError`, not a truncated list;
- CSV: header, pages, `has_more` in the middle and on the last line, repeated
  and empty column names;
- text: line numbering with an offset;
- a binary file, a folder and `opaque` — 422;
- non-empty `sort` and `filters` — 422, and `FetchResult` declares
  `sortable: false`;
- the home directory is created when a user is created and in `init_db`;
- another user's connector is not accessible, and the error text has no
  absolute server path;
- `mypy --strict`, `ruff` and `lint-imports` are clean;
- a Playwright scenario: a tree of samples, opening a CSV, the second page, a
  text file, `opaque` without a grid.

## A side finding for subproject 4b

A file source has no connection at all. So the pool cannot be designed as a
shared mechanism on top of all adapters: it belongs to the session module of a
specific driver. Subproject 4b must start from this premise.

## Not in this subproject

- writes of any kind — upload, creating a folder, renaming, deleting; these
  are the first real actions for the registry of subproject 5;
- downloading a file and streaming media out — subproject 7;
- archives, `.sqlite` inside the tree, parquet, XLSX;
- quotas and accounting of used space;
- paging of catalog children;
- the connection pool.

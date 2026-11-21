# Adding a source type

How a new source type is built, slice by slice, and every place outside its
package it has to touch. Not a decision file: what a type must answer is in
[contract.md](contract.md), and each step below names where its rule lives.
Written after DuckDB (D387–D404), which followed SQLite (D247–D263); read the
newest adapter of the same shape before writing a line.

## Choose the template

| The new type is | Copy the shape of |
| --- | --- |
| A file in the owner's storage | `duckdb/` (newest), `sqlite/` |
| An SQL server reached over the network | `clickhouse/`, `mysql/` |
| A document store | `mongodb/` |
| A broker or a stream | `kafka/`, `rabbitmq/` |
| A storage of files | [explorer.md](explorer.md), `s3/`, `ftp/` |
| A server reached only through an SSH connection, an HTTP API with no paging | `docker/` |

Shared pieces to use instead of writing again: `database_ids.py` (schema and
relation in one node id, D229), `home_file.py` (a file below the home, D247),
`made_here.py` (a database file made here, D263), `row_handles.py`,
`csv_load.py`, `model_code.py`, `table_copy.py` (`is_one_fragment`),
`search.py` (`class_of_name`, `Kept`), `listed.py` (a list read whole,
filtered and sorted in memory), `tunnels.py` (`reach`, `socket_endpoint`).

## Before any code: facts and a spec

1. Probe the engine in a scratch script, not from memory: what ALTER does in
   place, what is transactional, how values cross as text, what a catalog
   function returns, what the driver raises. Mark each fact *checked* with the
   version in the spec. Every slice of DuckDB found at least one fact that
   changed the design.
2. Write `docs/decisions/<date>-<type>-<topic>-design.md` with the decisions
   and the plan of slices; add its row at the top of
   [decisions/README.md](../../decisions/README.md). Take the next free `D…`
   numbers: `grep -rhoE "D[0-9]{3}" AGENTS.md docs backend/app | sort -u | tail`.
3. A branch `<type>-adapter`; one commit per slice.

## The six slices

Each slice lists its capability protocols (`adapters/protocol.py`) and the
template files to read.

1. **Read only.** Options (`SecretStr` for secrets), session, catalog,
   relation model, fetch with filters and sort, summary, content (DDL),
   features. `@register(...)` in `adapter.py`; the package imported in
   `adapters/__init__.py`; locales registered in the package's `__init__.py`.
2. **Console.** Statement classes from the engine's own parser where it has
   one; what reaches outside the source refused by family; runs, held
   transactions, rehearsal (D66), explain, metadata, formatting.
3. **Row edits.** How a row is named (key, digest), update, insert, delete,
   references both ways ([relations.md](relations.md)).
4. **Structure and the designer.** Column, index and constraint changes with
   counts first (D37–D40), the vocabulary of types, the table designer (D117),
   a table made from rows. Add a known deviation to [ddl.md](ddl.md) when the
   engine cannot do something every type is expected to.
5. **Reports, search, export, catalog actions.** A `\system` section of
   reports read like tables (D55); `SupportsNodeSearch`, `SearchesColumns`,
   `EnumeratesNames`; `export_rows`; rename, drop (rehearsed where structure
   changes are transactional), schemas, load from CSV, model as code.
6. **Copying tables, backups, the lab, made here.** `SupportsTableCopy`
   (D182), `SupportsBackup` (a program in a container, D87), the lab (a
   service template for a server, D80; a file for a file type, D261), metrics
   where the server has them ([dashboards.md](../dashboards.md)).

## Every slice

- Code with tests mirroring the source layout (`tests/adapters/test_<type>_*.py`,
  `tests/connectors/test_<type>_routes.py`); a fixture that builds the test
  database as a person would.
- Translations: every `N_`/`say` string in all seven catalogs of the package
  (`locales/*.py`). List what is missing with the helpers of
  `tests/core/test_translation_catalogs.py` (`_findings`, `catalog`). Reuse an
  existing sentence of another type where one exists: the test
  `disagreements()` fails when one English sentence has two translations. The
  Russian glossary of the screens says «столбец», not «колонка».
- The guide page `backend/app/guide/pages/source-<type>.md` and its seven
  translations under `pages/<lang>/`: "What you can see" and "What you can
  change" items are at most 80 characters (`tests/guide/test_reader.py`), and
  "What … does not have here yet" shrinks slice by slice.
- `docs/architecture/sources/<type>.md`: one `## D…` section per decision,
  each ending in exactly one `Spec:` line, and the `Decisions here:` line
  naming them all — on one line.
- [AGENTS.md](../../../AGENTS.md): the "Read before changing" row and the
  registry row (`D…–D…`). [README.md](README.md): the type's paragraph and its
  files in the tree.
- Tests elsewhere that list every action or capability fail when the type
  adds one; that is their job. Seen so far: `test_action_routes.py`,
  `test_file_actions.py`, a route test asserting 501 for what a later slice
  brings.

## Once per type

- Icon `frontend/public/icons/services/<type>.svg` and its line in
  `frontend/src/features/connectors/adapters.ts`.
- `backend/.importlinter`: the driver imported only by this package, and this
  package importing no other driver. Add the driver to `pyproject.toml`.
- A server type: the test server in `compose.override.yml`, its entry in
  `tests/utils/services.py` (tests skip without it), the CI job in
  `.github/workflows/ci.yml`, a connection in `scripts/seed-connectors.ts`.
- A file type: the lab written by `app/seed_storage.py`, its connection in
  `scripts/seed-connectors.ts`, a reader for the explorer
  (`register_database_reader`, D262) and a Connect action
  (`explorer/actions.py`), `MakesSourceHere` with `makes_here_file`.
- After a route or schema change: `bash scripts/generate-client.sh`, run from
  the repository root.

## Checks and traps

- Per slice: `uv run ruff check app tests`, `uv run mypy app`,
  `uv run lint-imports`, the type's tests, `bash scripts/check-docs.sh`; at the
  end of a slice the full `uv run pytest tests/ -q`, and the frontend checks
  when the frontend changed.
- Never rebuild or restart the backend container while the full suite runs:
  prestart touches `app_test`, and about 140 tests fail at once.
- On Windows give pytest its own `--basetemp` when it cannot remove
  `pytest-current`.
- Edit a locale file by inserting lines, not by rewriting it: a rewrite
  changes its quotes throughout and buries the change.
- Patch scripts go in a file in the scratchpad, not in a heredoc: bash eats
  backslashes and quotes in one.
- A new node kind is a class in `adapters/catalog.py`, its name in
  `NodeKind`, and on the client its shape and icon in
  `features/catalog/nodes.ts`, its caption, its word in the `summary` and
  `pipelines` locales of every language, and `src/client` regenerated.
- An SSH server refuses a forwarded Unix socket the same way whatever the
  reason (OpenSSH 10.3: code 2, "open failed"); do not promise a person which
  of the reasons it was.
- Look at what the screen shows before calling a slice done: a unit test does
  not prove a label, a button or a translation reaches the person.

# Data fetching

Date: 2026-08-15
Status: agreed
Subproject: 4a

## Goal

Show the rows of a table: page by page, with sorting and filters. The user
selects a table in the catalog tree and sees the data.

## Splitting the subproject

The original subproject 4 also included the connection pool. It is split in
two: fetching works without a pool too, opening a connection per request, as
the catalog does now. The pool is about performance and lifecycle, with its own
decisions about workers, and it is not needed for fetching to work. This
document describes only 4a.

## What we learned about the old application

An analysis of `fetch` in `postgres_extended_adaptor.py` produced five facts.

**SQL is built by string formatting.** A call of the form
`sql_template(...).format(fields_str, table, where, orderby_str, limit, offset)`,
where `where` comes from `get_where(**kwargs)` and `orderby` comes from the
client.

**The client can pass a raw SQL fragment.** The `sql_conditions` parameter is
substituted into the query whole; the only protection is a blacklist in
`validate_sql()`. This is SQL injection by construction, and a blacklist is the
weakest protection there is.

**A cascade of branches instead of one query.** Four templates for the
combinations of `orderby` / `orderby_str` / `where`, plus a special case
`if full_table_name.startswith('md_')` hard-coded into a shared method.

**The total row count is smuggled in as a fake column.**
`COUNT(*) OVER() AS ____total_count____` is appended to the field list, and it
ends up in the response model: the client has to know to throw it away.

**`meta` is a dump of twelve keys**, from `is_hypertable` to `queryLang` and
`supported_actions`.

Plus `limit: int = -1` by default, that is, a fetch without a limit.

## Contract

```python
@runtime_checkable
class SupportsFetch(Protocol):
    async def fetch(self, request: FetchRequest) -> FetchResult: ...
```

```python
FilterOp = Literal["eq", "ne", "gt", "gte", "lt", "lte",
                   "contains", "starts_with", "in", "is_null", "is_not_null"]

class Filter(BaseModel):
    column: str
    op: FilterOp
    value: Any | None = None      # not used for is_null / is_not_null

class Sort(BaseModel):
    column: str
    descending: bool = False

class FetchRequest(BaseModel):
    node_id: str
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    filters: list[Filter] = []
    sort: list[Sort] = []

class FetchColumn(BaseModel):
    name: str
    data_type: str

class FetchResult(BaseModel):
    columns: list[FetchColumn]
    rows: list[list[Any]]
    has_more: bool
```

`node_id` is the same opaque identifier the catalog returns. The interface
already has it from the tree, and only the adapter parses it, as before.

Rows are sent as arrays, not objects: on a wide table repeating the column
names in every row inflates the response several times over, and the grid
works by index.

## Security

Four rules, each closing a specific hole in the old code.

**Column names are checked against the catalog.** Before building the query
the adapter gets the columns of the relation and checks that every filter and
sort column is among them. An unknown column gives 422 and never reaches SQL.

**Identifiers are escaped with `psycopg.sql.Identifier`**, values are passed
through `sql.Placeholder` as parameters, and the query is assembled by
composing `psycopg.sql.SQL`. No `.format()` over user input.

**SQL strings from the client are not accepted anywhere.** There is no
equivalent of `sql_conditions`.

**`limit` has a default and an upper bound.** There is no "no limit" option.

## Total row count

There is no separate `COUNT(*)` per page. The adapter requests `limit + 1` rows
and returns `has_more`; the interface already has an approximate total — it
arrives in the catalog node as `row_count_estimate`. On a large table an exact
count would mean a full scan on every open.

## API

```
POST /api/v1/connectors/{connector_id}/fetch
```

POST rather than GET: the request is structured, and filter values must not
end up in the URL.

Adapter errors are returned as 502 with a kind and a message — the same as in
the catalog. A source that cannot fetch answers 501: `SupportsFetch` is an
optional capability, like `SupportsCatalog`.

## Interface

Selecting a table or view in the catalog tree opens a grid of rows: server-side
paging, sorting by clicking a header. The total is taken from the catalog
node's estimate, and pages are turned by `has_more`.

## Verification

Against the same test database; the fixtures exist.

- page, offset and the bounds of `limit`;
- ascending and descending sort;
- every predicate in the enumeration;
- `has_more` is true in the middle and false on the last page;
- an unknown column in a filter and in a sort gives an error;
- **an injection attempt through a column name is rejected before the database
  is touched**;
- a source without the fetch capability answers 501;
- `mypy --strict` and `ruff` are clean;
- a Playwright scenario: catalog, selecting a table, rows, second page.

## Not in this subproject

- the connection pool — subproject 4b;
- writes, aggregates, table joins;
- streaming export — it is a separate operation of subproject 7, not an
  extension of fetching; mixing these two scenarios in one method is exactly
  what happened in the old application;
- an SQL editor.

# Data source catalog

Date: 2026-08-15
Status: agreed
Subproject: 3

## Goal

Extend the adapter contract with catalog traversal: the user expands a
PostgreSQL connection and sees schemas, tables and columns. The response shape
must fit not only databases but also the object stores, queues and file
sources that will come later.

## What we learned about the old application

An analysis of `get_catalog` in `dbwebtool` produced four facts, each of which
shaped the decision.

**The outer shape was the same for every adapter.** Postgres, Mongo and AWS
return `{"data": [...], "meta": {...}}`. The envelope was not what broke.

**What broke was the content of the elements.** The type is `dict`, so each
adapter interpreted the shared keys its own way. In Postgres `schema` is the
name of a database schema; in AWS the same field means `"directory"`, and its
own `path` and `directory` are added there as well. The frontend branched on
adapters silently, because there were no types.

**One method held two access scenarios.** Postgres and Mongo return everything
at once; AWS takes a `path` and returns one level: there are unboundedly many
objects there.

**Errors were swallowed.** `except Exception` → `{'data': [], 'meta': {}}`.
An empty database and a failed query are indistinguishable.

Besides that, `meta` mixed schema metadata, the list of supported actions and
the list of backup files, and the catalog had no columns at all.

**`refresh_model` is not ported.** In the base class it returns
`NotImplemented`, the Postgres adapter does not implement it, and the web layer
never calls it. A dead method.

## Key decision

Differences between sources live **in the node kind, not in the source
family**.

An alternative was discussed — presets per family: one catalog type for
databases, another for file sources. It was rejected because the boundary
between families is blurred, and it would have to be decided for every
adapter: ClickHouse, Kafka, Google Sheets, S3 with parquet files. It was
exactly the attempt to assign a source to a category that broke in the old
application.

With the chosen approach one source can contain nodes of different kinds
without trouble: S3 returns prefixes, objects, and tables too if it can read
parquet. There is no need to categorise the source as a whole.

## Node shape

A node is a discriminated union; there is no nested dictionary of details.

```python
class BaseNode(BaseModel):
    id: str            # opaque to everyone except the adapter
    name: str
    has_children: bool

class SchemaNode(BaseNode):
    kind: Literal["schema"] = "schema"
    is_system: bool = False

class TableNode(BaseNode):
    kind: Literal["table"] = "table"
    row_count_estimate: int | None = None
    size_bytes: int | None = None
    is_system: bool = False

class ViewNode(BaseNode):
    kind: Literal["view"] = "view"
    is_materialized: bool = False
    is_system: bool = False

class ColumnNode(BaseNode):
    kind: Literal["column"] = "column"
    data_type: str
    nullable: bool
    primary_key: bool = False

CatalogNode = Annotated[
    SchemaNode | TableNode | ViewNode | ColumnNode, Field(discriminator="kind")
]
```

There are exactly three shared fields, and none of them can be reinterpreted:
`id`, `name`, `has_children`. The case where one field name means different
things in two adapters is excluded by construction — an object store will have
its own node class.

The union reaches OpenAPI as discriminated, so the frontend gets a real tagged
union: TypeScript narrows the type by `kind`.

A new node kind is a new class in the union. The friction is intentional: a
field can be added to a shared dictionary silently, a class cannot.

`row_count_estimate` is named honestly, instead of the old pair `row_count`
and `row_precise: "raw"`.

## Adapter contract

```python
class DataAdapter(Protocol):
    async def check_connection(self) -> ConnectionCheckResult: ...
    async def list_children(self, node_id: str | None) -> list[CatalogNode]: ...
```

`node_id = None` is the root. The value is opaque to the API and the frontend:
Postgres encodes `"public"` and `"public.users"` into it. Nobody but the
adapter parses it.

### Errors

The adapter raises `AdapterError(kind, message)`, where `kind` is the same
`ErrorKind` as in the connection check. The endpoint answers 502 with the body
`{"message": ..., "error_kind": ...}`. The driver's exception text does not go
out, for the same reason as in the connection check.

An empty catalog and a failed query must be distinguishable — this is a direct
requirement from the analysis of the old application.

## PostgreSQL adapter

| Level | What it returns |
| --- | --- |
| Root | Schemas. System ones are marked `is_system`, not hidden |
| Schema | Tables and views |
| Table | Columns |

The row count estimate is `reltuples` from `pg_class`, the size is
`pg_total_relation_size`. Both values are cheap and approximate, which the
field name reflects.

## API

```
GET /api/v1/connectors/{connector_id}/catalog            root
GET /api/v1/connectors/{connector_id}/catalog?node_id=…  children of a node
```

The response is `list[CatalogNode]`. A foreign connector returns 404, like the
other connector endpoints.

## Frontend

A tree on `QTree` with lazy loading: expanding a node requests its children.
It opens from a row of the connections list.

The component draws the shared fields and narrows the type by `kind` where it
shows details: the row count of a table, the data type of a column.

## Verification

The adapter tests run against the same test database as the others: suitable
fixtures already exist — the `user` and `connector` tables.

- the root contains the schema `public`;
- `public` contains the table `connector`;
- `connector` has the column `adapter_type` with a non-empty data type;
- a nonexistent node gives `AdapterError`, not an empty list;
- the catalog endpoint of a foreign connector returns 404;
- a fake adapter in the registry checks the endpoint without touching the database;
- `mypy --strict` and `ruff` are clean;
- a Playwright scenario: log in, expand a connection, schema → table → column.

## Not in this subproject

- catalog caching — that is subproject 4, together with the connection pool;
- `refresh_model` — a dead method, not ported;
- search and filtering over the catalog;
- any write operations;
- **paging of children**. Postgres has a finite number of them; object stores
  will need a cursor. The deferral is deliberate: adding a cursor will change
  the contract, but there is only one adapter so far, and that is cheap.

# Implementation plan: relation model

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A source can describe its relation in full — columns with the type taken apart, constraints with ordered columns, indexes, partitioning — and this is visible on a separate structure tab.

**Architecture:** A new optional capability `SupportsRelationModel` beside `SupportsCatalog` and `SupportsFetch`. The model types live in `app/adapters/relation.py` without a single line of SQL; the PostgreSQL implementation is four queries written over a set of relations, with an optional predicate on the name. A column type is an object, not a string: `sql` for DDL, `category` for behaviour. The file source does not implement the capability and answers 501.

**Tech Stack:** Python 3.14, FastAPI, psycopg 3 (async) with `psycopg.sql`, Pydantic v2, pytest + pytest-asyncio, uv. Frontend: Vue 3, TypeScript, Quasar, `@tanstack/vue-query`, Vitest, Playwright, bun.

Spec: [2026-08-24-relation-model-design.md](../2026-08-24-relation-model-design.md)

## Global Constraints

- Python 3.14; backend commands run from `backend/`, through `uv run`.
- After every task these are clean: `uv run pytest tests/ -q`, `uv run mypy app`, `uv run ruff check app tests`, `uv run lint-imports`.
- After tasks that touch the frontend: `bun run type-check`, `bun run lint`, `bun run test:unit` from `frontend/`.
- The database must be up before backend tests: `docker compose up -d db backend`.
- **A backend test run wipes all users**, the superuser included. `docker compose up -d db backend` restores them.
- **On Windows** async psycopg 3 is incompatible with `ProactorEventLoop`; the loop comes from `app.core.db.loop_factory`, which is already wired into pytest.
- All endpoints are under the `/api/v1` prefix (`settings.API_V1_STR`).
- **A query is never built from client strings** (D2c): identifiers through `psycopg.sql.Identifier`, values through placeholders. The schema name and the relation name come from `node_id` and are passed as parameters.
- **psycopg reads a literal `%` as a placeholder when parameters are passed**, even an empty tuple. No query in this round has a literal `%` — if one appears, it must be doubled.
- **Driver text does not reach the caller**: what goes out is `AdapterError` with a kind and a safe message, `NodeNotFound` for a node that has disappeared, `ValueError` for an unusable `node_id`.
- `frontend/src/client` is generated and not edited by hand: `bash scripts/generate-client.sh`.
- A screen asks for meaning, not for a look (D11): components from `src/shared/ui`, not one raw `z-index`, not one `q-*` that the kit replaces.
- Everything in the repository is in English, except `docs/superpowers/`.
- A commit after every task; messages in English, in the style of the existing ones (`feat(adapters): …`, `test(…): …`).

---

## File structure

**Created:**

| File | Responsible for |
| --- | --- |
| `backend/app/adapters/relation.py` | Relation model types. Not a single query. |
| `backend/app/adapters/postgres/column_type.py` | Pure parsing of a column type: `category`, length, precision, array element. |
| `backend/app/adapters/postgres/relation.py` | Four queries and the assembly of `RelationModel`. |
| `backend/tests/adapters/test_relation_models.py` | Validation of the model types without a database. |
| `backend/tests/adapters/test_postgres_column_type.py` | Type parsing, without a database. |
| `backend/tests/adapters/test_postgres_relation.py` | The model against a real database, including the round trip through DDL. |
| `backend/tests/utils/relation_fixture.py` | Fixture of an "awkward" table. |
| `frontend/src/features/structure/api.ts` | `useRelationModel` on vue-query. |
| `frontend/src/features/structure/model.ts` | Pure functions: column badges, foreign key caption. |
| `frontend/src/features/structure/model.spec.ts` | Unit tests for them. |
| `frontend/src/features/structure/StructureView.vue` | Columns, constraints, indexes. |
| `frontend/src/features/workspace/panels/StructurePanel.vue` | Panel wrapper. |
| `frontend/tests/structure.spec.ts` | Playwright scenario. |

**Changed:**

| File | What |
| --- | --- |
| `backend/app/adapters/protocol.py` | `SupportsRelationModel`. |
| `backend/app/adapters/registry.py` | A line in `capabilities_of`. |
| `backend/app/adapters/postgres/adapter.py` | Composition and delegation. |
| `backend/app/adapters/postgres/catalog.py` | `_list_columns` is removed, `has_children=False` on a table. |
| `backend/app/adapters/catalog.py` | `ColumnNode` is removed from the union and from `NodeKind`. |
| `backend/app/connectors/routes.py` | `GET /{connector_id}/relation-model`. |
| `frontend/src/features/catalog/nodes.ts` | `describable`, the `column` role goes. |
| `frontend/src/features/catalog/CatalogList.vue` | A "structure" button on the row. |
| `frontend/src/features/workspace/panels.ts` | The `structure` kind in the union, `structurePanelId`, `roleOf`, `lookOf`, `componentOf`. |
| `frontend/src/features/workspace/state.ts` | `openStructure` in the actions contract. |
| `frontend/src/features/workspace/WorkspacePage.vue` | Implementation of `openStructure`. |
| `AGENTS.md`, `docs/architecture/adapters.md` | D22. |

**Deviation from the spec:** the spec names one file `postgres/relation.py`. The plan splits it in two — type parsing moves to `postgres/column_type.py`, because it is the only part that can be checked without a database, and it is exactly where the `_int4` bug lives. Query assembly stays in `relation.py`.

---

### Task 1: Model types and the capability

**Files:**
- Create: `backend/app/adapters/relation.py`
- Create: `backend/tests/adapters/test_relation_models.py`
- Modify: `backend/app/adapters/protocol.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ColumnType`, `Column`, `PrimaryKey`, `UniqueConstraint`, `ForeignKey`, `CheckConstraint`, `ExclusionConstraint`, `Constraint`, `Index`, `Partitioning`, `PartitionOf`, `RelationModel`, `TypeCategory`, `RelationKind`, `RefAction`; the protocol `SupportsRelationModel` with `async def relation_model(self, node_id: str) -> RelationModel`.

- [ ] **Step 1: Write the failing test**

`backend/tests/adapters/test_relation_models.py`:

```python
import pytest
from pydantic import TypeAdapter, ValidationError

from app.adapters.relation import (
    Column,
    ColumnType,
    Constraint,
    ForeignKey,
    PrimaryKey,
    RelationModel,
)


def _text() -> ColumnType:
    return ColumnType(sql="text", category="string")


def test_a_scalar_type_needs_only_its_sql_and_category() -> None:
    column_type = ColumnType(sql="text", category="string")

    assert column_type.dimensions == 0
    assert column_type.element is None
    assert column_type.enum_values is None


def test_an_array_type_carries_its_element_and_depth() -> None:
    column_type = ColumnType(
        sql="integer[]",
        category="array",
        dimensions=1,
        element=ColumnType(sql="integer", category="number"),
    )

    assert column_type.element is not None
    assert column_type.element.category == "number"


def test_a_field_of_one_constraint_is_not_accepted_on_another() -> None:
    """The union is closed: a key belonging to a foreign key must fail loudly."""
    adapter = TypeAdapter(Constraint)

    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "kind": "primary_key",
                "name": "orders_pkey",
                "columns": ["id"],
                "target_node_id": "public.customers",
            }
        )


def test_a_foreign_key_names_the_target_as_a_node_id() -> None:
    key = ForeignKey(
        name="orders_customer_fkey",
        columns=["customer_id", "customer_region"],
        target_node_id="public.customers",
        target_columns=["id", "region"],
        on_update="no_action",
        on_delete="cascade",
        match="simple",
    )

    assert key.kind == "foreign_key"
    assert key.columns == ["customer_id", "customer_region"]


def test_a_relation_model_holds_columns_constraints_and_indexes() -> None:
    model = RelationModel(
        node_id="public.orders",
        schema_name="public",
        name="orders",
        kind="table",
        owner="postgres",
        persistence="permanent",
        columns=[
            Column(position=1, name="id", type=_text(), nullable=False, storage="plain")
        ],
        constraints=[PrimaryKey(name="orders_pkey", columns=["id"])],
    )

    assert model.indexes == []
    assert model.partitioning is None
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_relation_models.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.adapters.relation'`

- [ ] **Step 3: Write the types**

`backend/app/adapters/relation.py`:

```python
"""What a source can say about one relation, whatever the source is.

Separate from `catalog.py` on purpose. A catalog node answers "what is here";
this answers "what is this made of", and the two have different lifetimes: a
listing changes when something is created, a model when something is altered.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# What a value is, as far as anything outside the adapter needs to care.
# Derived on the server so that the grid never parses a type name with a
# regular expression and the filters never offer `contains` for an int — the
# same computation on both sides is a defect by ENGINEERING.md.
TypeCategory = Literal[
    "number",
    "string",
    "boolean",
    "datetime",
    "binary",
    "json",
    "uuid",
    "network",
    "geometric",
    "range",
    "enum",
    "composite",
    "array",
    "other",
]

RelationKind = Literal[
    "table",
    "partitioned_table",
    "view",
    "materialized_view",
    "foreign_table",
]

Persistence = Literal["permanent", "unlogged", "temporary"]

RefAction = Literal["no_action", "restrict", "cascade", "set_null", "set_default"]

Storage = Literal["plain", "main", "external", "extended"]


class ColumnType(BaseModel):
    """A type, said three ways, because one string cannot do three jobs.

    The old application kept one: `typname`, which is `_int4` for an array of
    integers and cannot be written into a CREATE TABLE at all. The workaround
    was a second per-column query, and it was still wrong — it dropped the
    modifier, turning varchar(50) into character varying.
    """

    model_config = ConfigDict(extra="forbid")

    # What goes into DDL, and what pg_dump itself writes.
    sql: str
    category: TypeCategory
    # The element of an array, when this is one. Recursive so that int[][] and
    # an array of enums both describe themselves.
    element: "ColumnType | None" = None
    dimensions: int = 0
    enum_values: list[str] | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    name: str
    type: ColumnType
    nullable: bool
    storage: Storage
    comment: str | None = None
    default: str | None = None
    # GENERATED ... AS IDENTITY, which is not the same thing as a default.
    identity: Literal["always", "by_default"] | None = None
    # The expression of a GENERATED ALWAYS AS (...) STORED column.
    generated: str | None = None
    collation: str | None = None


class PrimaryKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["primary_key"] = "primary_key"
    name: str
    # In key order, never sorted. The old application flattened a composite key
    # into one entry per column, which represents a two-column relationship as
    # two independent ones — wrong for anything that has to follow it.
    columns: list[str]


class UniqueConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["unique"] = "unique"
    name: str
    columns: list[str]
    nulls_not_distinct: bool = False


class ForeignKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["foreign_key"] = "foreign_key"
    name: str
    columns: list[str]
    # Produced by the adapter, in the form its own catalog uses. The client
    # never takes an id apart and never builds one — D21.
    target_node_id: str
    target_columns: list[str]
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"
    match: Literal["full", "partial", "simple"] = "simple"


class CheckConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["check"] = "check"
    name: str
    expression: str
    columns: list[str] = Field(default_factory=list)


class ExclusionConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exclude"] = "exclude"
    name: str
    expression: str


Constraint = Annotated[
    PrimaryKey | UniqueConstraint | ForeignKey | CheckConstraint | ExclusionConstraint,
    Field(discriminator="kind"),
]


class Index(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    method: str
    unique: bool = False
    primary: bool = False
    valid: bool = True
    # Empty when every key is an expression; an expression column contributes
    # nothing here and is visible in `definition`.
    columns: list[str] = Field(default_factory=list)
    predicate: str | None = None
    definition: str


class Partitioning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["range", "list", "hash"]
    key: str


class PartitionOf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_node_id: str
    bounds: str


class RelationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    schema_name: str
    name: str
    kind: RelationKind
    owner: str
    persistence: Persistence
    comment: str | None = None
    row_estimate: int | None = None
    size_bytes: int | None = None
    columns: list[Column] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list)
    partitioning: Partitioning | None = None
    partition_of: PartitionOf | None = None
```

- [ ] **Step 4: Add the capability to the protocol**

At the end of `backend/app/adapters/protocol.py`, after `SupportsFetch`:

```python
@runtime_checkable
class SupportsRelationModel(Protocol):
    async def relation_model(self, node_id: str) -> RelationModel:
        """Describe one relation in full: columns, constraints, indexes.

        A capability rather than part of `SupportsCatalog`, because having a
        catalog and having relations are different things: a queue and an
        object store have the first and not the second. Answering with an
        invented model would be worse than answering 501.

        Raises NodeNotFound for an id that names nothing, AdapterError for
        source failures, and ValueError for an id this source may not reach.
        """
        ...
```

And the import at the top of the file:

```python
from app.adapters.relation import RelationModel
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/adapters/test_relation_models.py -q && uv run mypy app && uv run ruff check app tests && uv run lint-imports`
Expected: 5 passed; mypy, ruff and lint-imports without errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/relation.py backend/app/adapters/protocol.py backend/tests/adapters/test_relation_models.py && git commit -m "feat(adapters): a source can describe a relation in full"
```

---

### Task 2: Column type parsing

**Files:**
- Create: `backend/app/adapters/postgres/column_type.py`
- Create: `backend/tests/adapters/test_postgres_column_type.py`

**Interfaces:**
- Consumes: `ColumnType`, `TypeCategory` from Task 1.
- Produces: `build_column_type(row: Mapping[str, Any]) -> ColumnType`, where `row` carries the keys `sql_type`, `type_category`, `type_name`, `element_sql`, `element_category`, `element_name`, `type_mod`, `enum_values`, `element_enum_values`.

- [ ] **Step 1: Write the failing test**

`backend/tests/adapters/test_postgres_column_type.py`:

```python
from typing import Any

from app.adapters.postgres.column_type import build_column_type


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sql_type": "text",
        "type_category": "S",
        "type_name": "text",
        "type_mod": -1,
        "element_sql": None,
        "element_category": None,
        "element_name": None,
        "enum_values": None,
        "element_enum_values": None,
    }
    base.update(overrides)
    return base


def test_a_plain_type_keeps_what_format_type_said() -> None:
    result = build_column_type(_row())

    assert result.sql == "text"
    assert result.category == "string"


def test_an_array_is_a_category_of_its_own_and_carries_its_element() -> None:
    """The regression: the old model called this `_int4`, which is not DDL."""
    result = build_column_type(
        _row(
            sql_type="integer[]",
            type_category="A",
            type_name="_int4",
            element_sql="integer",
            element_category="N",
            element_name="int4",
        )
    )

    assert result.sql == "integer[]"
    assert result.category == "array"
    assert result.dimensions == 1
    assert result.element is not None
    assert result.element.sql == "integer"
    assert result.element.category == "number"


def test_a_two_dimensional_array_is_counted_from_the_sql() -> None:
    result = build_column_type(
        _row(
            sql_type="integer[][]",
            type_category="A",
            type_name="_int4",
            element_sql="integer",
            element_category="N",
            element_name="int4",
        )
    )

    assert result.dimensions == 2


def test_varchar_keeps_its_length() -> None:
    result = build_column_type(
        _row(sql_type="character varying(50)", type_category="S",
             type_name="varchar", type_mod=54)
    )

    assert result.sql == "character varying(50)"
    assert result.length == 50


def test_numeric_keeps_precision_and_scale() -> None:
    # atttypmod for numeric(10,2) is ((10 << 16) | 2) + 4
    result = build_column_type(
        _row(sql_type="numeric(10,2)", type_category="N",
             type_name="numeric", type_mod=((10 << 16) | 2) + 4)
    )

    assert result.precision == 10
    assert result.scale == 2


def test_the_types_postgres_files_under_user_defined_are_told_apart() -> None:
    """typcategory says 'U' for jsonb, uuid and bytea alike."""
    assert build_column_type(
        _row(sql_type="jsonb", type_category="U", type_name="jsonb")
    ).category == "json"
    assert build_column_type(
        _row(sql_type="uuid", type_category="U", type_name="uuid")
    ).category == "uuid"
    assert build_column_type(
        _row(sql_type="bytea", type_category="U", type_name="bytea")
    ).category == "binary"


def test_an_enum_carries_its_labels_in_declared_order() -> None:
    result = build_column_type(
        _row(sql_type="public.mood", type_category="E", type_name="mood",
             enum_values=["sad", "ok", "happy"])
    )

    assert result.category == "enum"
    assert result.enum_values == ["sad", "ok", "happy"]


def test_an_array_of_enums_carries_the_labels_on_the_element() -> None:
    result = build_column_type(
        _row(
            sql_type="public.mood[]",
            type_category="A",
            type_name="_mood",
            element_sql="public.mood",
            element_category="E",
            element_name="mood",
            element_enum_values=["sad", "ok", "happy"],
        )
    )

    assert result.element is not None
    assert result.element.enum_values == ["sad", "ok", "happy"]


def test_an_unknown_category_falls_through_rather_than_failing() -> None:
    result = build_column_type(
        _row(sql_type="pg_lsn", type_category="Z", type_name="pg_lsn")
    )

    assert result.category == "other"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_column_type.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.adapters.postgres.column_type'`

- [ ] **Step 3: Write the parser**

`backend/app/adapters/postgres/column_type.py`:

```python
"""Turning what pg_type says into what the rest of the application needs.

Kept apart from the queries because this is the whole of the round's risk and
the only part that can be checked without a database: the old application put
`typname` in the model, and `_int4` cannot be written into a CREATE TABLE.
"""

from collections.abc import Mapping
from typing import Any

from app.adapters.relation import ColumnType, TypeCategory

# pg_type.typcategory is one character. Most of it maps straight across.
_BY_CATEGORY: dict[str, TypeCategory] = {
    "A": "array",
    "B": "boolean",
    "C": "composite",
    "D": "datetime",
    "E": "enum",
    "G": "geometric",
    "I": "network",
    "N": "number",
    "R": "range",
    "S": "string",
    "T": "datetime",
    "V": "binary",
}

# What PostgreSQL files under "U" for user-defined, which is where the types
# an application cares about most end up. Anything else there is "other".
_BY_NAME: dict[str, TypeCategory] = {
    "json": "json",
    "jsonb": "json",
    "uuid": "uuid",
    "bytea": "binary",
    "xml": "string",
}


def _category(typcategory: str | None, typname: str | None) -> TypeCategory:
    named = _BY_NAME.get(typname or "")
    if named is not None:
        return named
    return _BY_CATEGORY.get(typcategory or "", "other")


def _length(typname: str | None, typmod: int | None) -> int | None:
    """The declared width of a character type.

    atttypmod carries it plus the four-byte header, and is -1 when the type
    was declared without one.
    """
    if typmod is None or typmod < 0:
        return None
    if typname in {"varchar", "bpchar"}:
        return typmod - 4
    return None


def _precision_and_scale(
    typname: str | None, typmod: int | None
) -> tuple[int | None, int | None]:
    if typname != "numeric" or typmod is None or typmod < 0:
        return None, None
    packed = typmod - 4
    return (packed >> 16) & 0xFFFF, packed & 0xFFFF


def _labels(value: Any) -> list[str] | None:
    """Enum labels as psycopg hands them over, or nothing."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return None


def build_column_type(row: Mapping[str, Any]) -> ColumnType:
    """One column's type, from the row the columns query produced.

    `sql` is taken verbatim from format_type(atttypid, atttypmod): that is what
    pg_dump writes, so it is the one form guaranteed to survive a round trip
    through CREATE TABLE. Nothing here reassembles it from parts.
    """
    sql = str(row["sql_type"])
    typname = row.get("type_name")
    typmod = row.get("type_mod")
    category = _category(row.get("type_category"), typname)

    element: ColumnType | None = None
    if category == "array" and row.get("element_sql") is not None:
        element = ColumnType(
            sql=str(row["element_sql"]),
            category=_category(row.get("element_category"), row.get("element_name")),
            enum_values=_labels(row.get("element_enum_values")),
        )

    precision, scale = _precision_and_scale(typname, typmod)
    return ColumnType(
        sql=sql,
        category=category,
        element=element,
        # Counted from the printed type rather than from attndims, which
        # PostgreSQL does not maintain: it is 0 for most array columns.
        dimensions=sql.count("[]"),
        enum_values=_labels(row.get("enum_values")),
        length=_length(typname, typmod),
        precision=precision,
        scale=scale,
    )
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_column_type.py -q && uv run mypy app && uv run ruff check app tests`
Expected: 9 passed; mypy and ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/postgres/column_type.py backend/tests/adapters/test_postgres_column_type.py && git commit -m "feat(postgres): a column type says what it is, not just what it is called"
```

---

### Task 3: Relation and columns, and the round trip through DDL

**Files:**
- Create: `backend/app/adapters/postgres/relation.py`
- Create: `backend/tests/utils/relation_fixture.py`
- Create: `backend/tests/adapters/test_postgres_relation.py`

**Interfaces:**
- Consumes: `build_column_type` (Task 2), the model types (Task 1), `PostgresSession.query(sql, params) -> list[dict[str, Any]]`.
- Produces: the class `PostgresRelation(session)` with `async def relation_model(self, node_id: str) -> RelationModel` and a private `async def _models(self, schema: str, relation: str | None) -> list[RelationModel]`.

- [ ] **Step 1: Write the fixture of the awkward table**

`backend/tests/utils/relation_fixture.py`:

```python
"""A relation awkward enough to be worth describing.

Everything here exists because something about it once went wrong or is easy
to get wrong: an array (whose internal name is not writable), a varchar with a
modifier (which the old fix dropped), a numeric with precision and scale, an
enum, a generated column, an identity column, and keys made of two columns.
"""

from collections.abc import AsyncGenerator

import psycopg

from tests.utils.database import working_postgres_options

SCHEMA = "relation_model_test"

SETUP = f"""
DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;
CREATE SCHEMA {SCHEMA};

CREATE TYPE {SCHEMA}.mood AS ENUM ('sad', 'ok', 'happy');

CREATE TABLE {SCHEMA}.regions (
    id      integer NOT NULL,
    code    varchar(8) NOT NULL,
    PRIMARY KEY (id, code)
);

CREATE TABLE {SCHEMA}.customers (
    id            integer GENERATED BY DEFAULT AS IDENTITY,
    region_id     integer NOT NULL,
    region_code   varchar(8) NOT NULL,
    name          varchar(50) NOT NULL,
    name_upper    text GENERATED ALWAYS AS (upper(name)) STORED,
    balance       numeric(10,2) NOT NULL DEFAULT 0,
    tags          integer[],
    feeling       {SCHEMA}.mood,
    payload       jsonb,
    token         uuid,
    picture       bytea,
    CONSTRAINT customers_pkey PRIMARY KEY (id),
    CONSTRAINT customers_region_fkey
        FOREIGN KEY (region_id, region_code)
        REFERENCES {SCHEMA}.regions (id, code)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT customers_name_unique UNIQUE (name),
    CONSTRAINT customers_balance_check CHECK (balance >= 0)
);

COMMENT ON TABLE {SCHEMA}.customers IS 'People who owe money';
COMMENT ON COLUMN {SCHEMA}.customers.balance IS 'In euros';

CREATE INDEX customers_name_idx ON {SCHEMA}.customers (name) WHERE balance > 0;

CREATE VIEW {SCHEMA}.rich_customers AS
    SELECT id, name FROM {SCHEMA}.customers WHERE balance > 1000;
"""


def conninfo() -> str:
    options = working_postgres_options()
    return psycopg.conninfo.make_conninfo(
        host=options["host"],
        port=options["port"],
        dbname=options["database"],
        user=options["user"],
        password=options["password"],
    )


async def run(statement: str) -> None:
    async with await psycopg.AsyncConnection.connect(
        conninfo(), autocommit=True
    ) as conn:
        await conn.execute(statement)


async def make_schema() -> AsyncGenerator[str]:
    """The schema, dropped afterwards whatever happened."""
    await run(SETUP)
    try:
        yield SCHEMA
    finally:
        await run(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/adapters/test_postgres_relation.py`:

```python
from collections.abc import AsyncGenerator

import pytest

from app.adapters.postgres.adapter import PostgresAdapter
from app.adapters.postgres.options import PostgresUserPassword
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import NodeNotFound
from tests.utils.database import working_postgres_options
from tests.utils.relation_fixture import SCHEMA, make_schema, run


@pytest.fixture
async def schema() -> AsyncGenerator[str]:
    async for name in make_schema():
        yield name


def _relation() -> PostgresRelation:
    session = PostgresSession(PostgresUserPassword(**working_postgres_options()))
    return PostgresRelation(session)


async def test_a_relation_says_what_it_is(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")

    assert model.node_id == f"{schema}.customers"
    assert model.schema_name == schema
    assert model.name == "customers"
    assert model.kind == "table"
    assert model.persistence == "permanent"
    assert model.comment == "People who owe money"
    assert model.owner != ""


async def test_columns_arrive_in_declaration_order_with_their_comments(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")

    names = [column.name for column in model.columns]
    assert names[:4] == ["id", "region_id", "region_code", "name"]
    balance = next(column for column in model.columns if column.name == "balance")
    assert balance.comment == "In euros"


async def test_the_awkward_types_are_taken_apart(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    by_name = {column.name: column for column in model.columns}

    assert by_name["tags"].type.sql == "integer[]"
    assert by_name["tags"].type.category == "array"
    assert by_name["tags"].type.element is not None
    assert by_name["tags"].type.element.sql == "integer"

    assert by_name["name"].type.sql == "character varying(50)"
    assert by_name["name"].type.length == 50

    assert by_name["balance"].type.precision == 10
    assert by_name["balance"].type.scale == 2

    assert by_name["feeling"].type.category == "enum"
    assert by_name["feeling"].type.enum_values == ["sad", "ok", "happy"]

    assert by_name["payload"].type.category == "json"
    assert by_name["token"].type.category == "uuid"
    assert by_name["picture"].type.category == "binary"


async def test_identity_generated_and_default_are_told_apart(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.customers")
    by_name = {column.name: column for column in model.columns}

    assert by_name["id"].identity == "by_default"
    assert by_name["name_upper"].generated is not None
    assert "upper" in by_name["name_upper"].generated
    assert by_name["balance"].default is not None
    assert by_name["name_upper"].default is None


async def test_the_type_of_every_column_can_be_written_back_into_ddl(
    schema: str,
) -> None:
    """The round trip, and the reason this round exists.

    `_int4` does not survive it, and `character varying` without the modifier
    comes back as a different type. Taking the model's own `sql` and building a
    table out of it is the only check that proves neither happened.
    """
    described = await _relation().relation_model(f"{schema}.customers")
    definition = ", ".join(
        f'"{column.name}" {column.type.sql}' for column in described.columns
    )
    await run(f"CREATE TABLE {schema}.round_trip ({definition})")

    rebuilt = await _relation().relation_model(f"{schema}.round_trip")

    original = {column.name: column.type.sql for column in described.columns}
    copied = {column.name: column.type.sql for column in rebuilt.columns}
    assert copied == original


async def test_a_view_has_columns_and_no_constraints(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.rich_customers")

    assert model.kind == "view"
    assert [column.name for column in model.columns] == ["id", "name"]
    assert model.constraints == []


async def test_a_relation_that_is_gone_is_not_a_failure(schema: str) -> None:
    with pytest.raises(NodeNotFound):
        await _relation().relation_model(f"{schema}.no_such_table")


async def test_an_id_that_is_not_a_relation_is_refused(schema: str) -> None:
    with pytest.raises(ValueError):
        await _relation().relation_model(schema)


async def test_the_adapter_delegates_to_it(schema: str) -> None:
    adapter = PostgresAdapter(PostgresUserPassword(**working_postgres_options()))

    model = await adapter.relation_model(f"{SCHEMA}.customers")

    assert model.name == "customers"
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.adapters.postgres.relation'`

- [ ] **Step 4: Write the queries and the assembly**

`backend/app/adapters/postgres/relation.py`:

```python
"""Describing a relation: what it is and what it is made of.

Every query here is written over a *set* of relations, with the relation name
as an optional predicate. Only one relation is ever asked for today, but the
short way — WHERE attrelid = %s::regclass, one oid — does not generalise, and
a whole schema at once is what the cache in the next round will want. Leaving
the predicate optional makes that a caller change rather than a rewrite.
"""

from typing import Any

from app.adapters.postgres.column_type import build_column_type
from app.adapters.postgres.session import PostgresSession
from app.adapters.protocol import NodeNotFound
from app.adapters.relation import (
    Column,
    Persistence,
    RelationKind,
    RelationModel,
    Storage,
)

_KINDS: dict[str, RelationKind] = {
    "r": "table",
    "p": "partitioned_table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
}

_PERSISTENCE: dict[str, Persistence] = {
    "p": "permanent",
    "u": "unlogged",
    "t": "temporary",
}

_STORAGE: dict[str, Storage] = {
    "p": "plain",
    "m": "main",
    "e": "external",
    "x": "extended",
}

_RELATIONS = """
SELECT c.relname                                  AS name,
       c.relkind                                  AS relkind,
       c.relpersistence                           AS persistence,
       c.reltuples                                AS row_estimate,
       pg_total_relation_size(c.oid)              AS size_bytes,
       pg_get_userbyid(c.relowner)                AS owner,
       obj_description(c.oid, 'pg_class')         AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = %s
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
"""

_COLUMNS = """
SELECT c.relname                                  AS relation,
       a.attnum                                   AS position,
       a.attname                                  AS name,
       format_type(a.atttypid, a.atttypmod)       AS sql_type,
       a.atttypmod                                AS type_mod,
       t.typcategory                              AS type_category,
       t.typname                                  AS type_name,
       format_type(t.typelem, a.atttypmod)        AS element_sql,
       et.typcategory                             AS element_category,
       et.typname                                 AS element_name,
       NOT a.attnotnull                           AS nullable,
       a.attstorage                               AS storage,
       a.attidentity                              AS identity,
       a.attgenerated                             AS generated,
       pg_get_expr(ad.adbin, ad.adrelid)          AS default_expression,
       col_description(a.attrelid, a.attnum)      AS comment,
       co.collname                                AS collation,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = t.oid)  AS enum_values,
       (SELECT array_agg(e.enumlabel ORDER BY e.enumsortorder)
          FROM pg_enum e WHERE e.enumtypid = et.oid) AS element_enum_values
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_type et ON et.oid = t.typelem
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
LEFT JOIN pg_collation co ON co.oid = a.attcollation AND co.collname <> 'default'
WHERE n.nspname = %s
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND a.attnum > 0
  AND NOT a.attisdropped
"""


class PostgresRelation:
    """Reading the structure of a relation out of the system catalogs."""

    def __init__(self, session: PostgresSession) -> None:
        self._session = session

    async def relation_model(self, node_id: str) -> RelationModel:
        schema, _, relation = node_id.partition(".")
        if not relation:
            raise ValueError(
                f'"{node_id}" is not a relation: expected schema.relation'
            )
        models = await self._models(schema, relation)
        if not models:
            raise NodeNotFound(node_id)
        return models[0]

    async def _models(
        self, schema: str, relation: str | None
    ) -> list[RelationModel]:
        relations = await self._query(_RELATIONS, schema, relation, "c.relname")
        if not relations:
            return []

        columns = await self._query(_COLUMNS, schema, relation, "c.relname")
        by_relation: dict[str, list[Column]] = {}
        for row in sorted(columns, key=lambda item: int(item["position"])):
            by_relation.setdefault(str(row["relation"]), []).append(_column(row))

        return [
            _relation_model(schema, row, by_relation.get(str(row["name"]), []))
            for row in relations
        ]

    async def _query(
        self, statement: str, schema: str, relation: str | None, column: str
    ) -> list[dict[str, Any]]:
        """Run one of the catalog queries, narrowed to a relation when asked.

        The predicate is appended rather than baked in, which is what keeps a
        whole schema one argument away. `column` names the pg_class alias the
        statement uses; it is a literal from this module, never client input.
        """
        params: list[Any] = [schema]
        text = statement
        if relation is not None:
            text += f" AND {column} = %s"
            params.append(relation)
        return await self._session.query(text, tuple(params))


def _column(row: dict[str, Any]) -> Column:
    generated = row.get("generated")
    identity = row.get("identity")
    # A generated column keeps its expression in pg_attrdef, the same place a
    # default lives; they are different things and must not both be reported.
    expression = row.get("default_expression")
    return Column(
        position=int(row["position"]),
        name=str(row["name"]),
        type=build_column_type(row),
        nullable=bool(row["nullable"]),
        storage=_STORAGE.get(str(row["storage"]), "plain"),
        comment=row.get("comment"),
        default=None if generated == "s" else expression,
        generated=expression if generated == "s" else None,
        identity={"a": "always", "d": "by_default"}.get(str(identity or "")),
        collation=row.get("collation"),
    )


def _relation_model(
    schema: str, row: dict[str, Any], columns: list[Column]
) -> RelationModel:
    name = str(row["name"])
    estimate = row.get("row_estimate")
    return RelationModel(
        node_id=f"{schema}.{name}",
        schema_name=schema,
        name=name,
        kind=_KINDS[str(row["relkind"])],
        owner=str(row["owner"]),
        persistence=_PERSISTENCE.get(str(row["persistence"]), "permanent"),
        comment=row.get("comment"),
        # -1 means the relation has never been analysed, which is not a count.
        row_estimate=None if estimate is None or estimate < 0 else int(estimate),
        size_bytes=row.get("size_bytes"),
        columns=columns,
    )
```

`psycopg.sql` is not needed here and is not imported: no identifier is substituted into these queries — the schema name and the relation name go as values through placeholders.

- [ ] **Step 5: Wire it into the adapter**

In `backend/app/adapters/postgres/adapter.py`:

```python
from app.adapters.postgres.relation import PostgresRelation
from app.adapters.relation import RelationModel
```

in `__init__`, after `self._fetch = PostgresFetch(self._session)`:

```python
        self._relation = PostgresRelation(self._session)
```

and a method beside `fetch`:

```python
    async def relation_model(self, node_id: str) -> RelationModel:
        return await self._relation.relation_model(node_id)
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q`
Expected: 9 passed. The round trip through DDL — `test_the_type_of_every_column_can_be_written_back_into_ddl` — is green.

- [ ] **Step 7: Make sure the round trip through DDL actually catches something**

Temporarily replace the line `sql = str(row["sql_type"])` in `column_type.py` with `sql = str(row["type_name"])` and run the same test.
Expected: FAIL — `CREATE TABLE` fails on `_int4`. Put the line back and make sure it PASSes again. A check that has never gone red proves nothing.

- [ ] **Step 8: Commit**

```bash
git add backend/app/adapters/postgres/relation.py backend/app/adapters/postgres/adapter.py backend/tests/utils/relation_fixture.py backend/tests/adapters/test_postgres_relation.py && git commit -m "feat(postgres): a relation describes its columns, types included"
```

---

### Task 4: Constraints

**Files:**
- Modify: `backend/app/adapters/postgres/relation.py`
- Modify: `backend/tests/adapters/test_postgres_relation.py`

**Interfaces:**
- Consumes: `_query`, `_models` from Task 3.
- Produces: `constraints` filled in `RelationModel`.

- [ ] **Step 1: Add the failing tests**

At the end of `backend/tests/adapters/test_postgres_relation.py`:

```python
from app.adapters.relation import (
    CheckConstraint,
    ForeignKey,
    PrimaryKey,
    UniqueConstraint,
)


async def test_a_composite_foreign_key_is_one_constraint_in_key_order(
    schema: str,
) -> None:
    """The old model split this into two independent one-column links."""
    model = await _relation().relation_model(f"{schema}.customers")

    keys = [c for c in model.constraints if isinstance(c, ForeignKey)]
    assert len(keys) == 1
    key = keys[0]
    assert key.name == "customers_region_fkey"
    assert key.columns == ["region_id", "region_code"]
    assert key.target_columns == ["id", "code"]
    assert key.on_update == "cascade"
    assert key.on_delete == "restrict"


async def test_a_foreign_key_names_its_target_the_way_the_catalog_does(
    schema: str,
) -> None:
    """The client never builds a node id, so the adapter hands one over."""
    model = await _relation().relation_model(f"{schema}.customers")

    key = next(c for c in model.constraints if isinstance(c, ForeignKey))
    assert key.target_node_id == f"{schema}.regions"


async def test_the_primary_key_of_the_target_is_composite_and_ordered(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.regions")

    key = next(c for c in model.constraints if isinstance(c, PrimaryKey))
    assert key.columns == ["id", "code"]


async def test_unique_and_check_are_reported_with_their_own_shape(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")

    unique = next(c for c in model.constraints if isinstance(c, UniqueConstraint))
    assert unique.name == "customers_name_unique"
    assert unique.columns == ["name"]

    check = next(c for c in model.constraints if isinstance(c, CheckConstraint))
    assert check.name == "customers_balance_check"
    assert "balance" in check.expression
    assert check.columns == ["balance"]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q -k constraint or foreign or unique or primary`
Expected: FAIL — `constraints` is empty, `next()` raises `StopIteration`.

- [ ] **Step 3: Write the query and the assembly**

In `backend/app/adapters/postgres/relation.py` add the query:

```python
_CONSTRAINTS = """
SELECT c.relname                                       AS relation,
       con.conname                                     AS name,
       con.contype                                     AS contype,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.conrelid AND att.attnum = u.attnum
       )                                               AS column_names,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = con.confrelid AND att.attnum = u.attnum
       )                                               AS target_column_names,
       fn.nspname                                      AS target_schema,
       fc.relname                                      AS target_relation,
       con.confupdtype                                 AS on_update,
       con.confdeltype                                 AS on_delete,
       con.confmatchtype                               AS match_type,
       pg_get_expr(con.conbin, con.conrelid)           AS expression,
       pg_get_constraintdef(con.oid)                   AS definition
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE n.nspname = %s
  AND con.contype IN ('p', 'u', 'f', 'c', 'x')
"""

_REF_ACTIONS: dict[str, RefAction] = {
    "a": "no_action",
    "r": "restrict",
    "c": "cascade",
    "n": "set_null",
    "d": "set_default",
}

_MATCH: dict[str, str] = {"f": "full", "p": "partial", "s": "simple"}
```

and the imports `CheckConstraint, Constraint, ExclusionConstraint, ForeignKey, PrimaryKey, RefAction, UniqueConstraint`.

The assembly — as a function beside `_column`:

```python
def _names(value: Any) -> list[str]:
    """Column names as the array subquery produced them, in key order.

    Order is the point: `conkey` lists attnums in the order the key was
    declared, and `WITH ORDINALITY` carries that order through the aggregate.
    A key whose column order is lost is a different key.
    """
    return [str(item) for item in value] if isinstance(value, list) else []


def _constraint(row: dict[str, Any]) -> Constraint | None:
    contype = str(row["contype"])
    name = str(row["name"])
    columns = _names(row.get("column_names"))

    if contype == "p":
        return PrimaryKey(name=name, columns=columns)
    if contype == "u":
        # Read off the printed definition rather than pg_index.indnullsnotdistinct,
        # which only exists from PostgreSQL 15.
        definition = str(row.get("definition") or "")
        return UniqueConstraint(
            name=name,
            columns=columns,
            nulls_not_distinct="NULLS NOT DISTINCT" in definition,
        )
    if contype == "f":
        target_schema = str(row["target_schema"])
        target_relation = str(row["target_relation"])
        return ForeignKey(
            name=name,
            columns=columns,
            target_node_id=f"{target_schema}.{target_relation}",
            target_columns=_names(row.get("target_column_names")),
            on_update=_REF_ACTIONS.get(str(row["on_update"]), "no_action"),
            on_delete=_REF_ACTIONS.get(str(row["on_delete"]), "no_action"),
            match=_MATCH.get(str(row["match_type"]), "simple"),  # type: ignore[arg-type]  # a closed set, mapped from a closed set
        )
    if contype == "c":
        return CheckConstraint(
            name=name,
            expression=str(row.get("expression") or ""),
            columns=columns,
        )
    if contype == "x":
        return ExclusionConstraint(
            name=name, expression=str(row.get("definition") or "")
        )
    return None
```

In `_models`, after the columns are assembled:

```python
        constraint_rows = await self._query(
            _CONSTRAINTS, schema, relation, "c.relname"
        )
        constraints: dict[str, list[Constraint]] = {}
        for row in constraint_rows:
            built = _constraint(row)
            if built is not None:
                constraints.setdefault(str(row["relation"]), []).append(built)
```

`_relation_model` gets a fourth argument, and the call in `return` becomes:

```python
        return [
            _relation_model(
                schema,
                row,
                by_relation.get(str(row["name"]), []),
                constraints.get(str(row["name"]), []),
            )
            for row in relations
        ]
```

In `_relation_model` itself — the parameter `constraints: list[Constraint]` and the field `constraints=constraints` in `RelationModel`.

**Why names are resolved in SQL and not in Python.** The obvious move is to build a "position → name" dictionary from the columns already read and map `conkey` and `confkey` through it. For `conkey` this works, for `confkey` it does not: the target of a foreign key may live in another schema, whose columns are not in the answer at all, and `target_columns` silently turns out empty. `unnest(...) WITH ORDINALITY` resolves both sides at the source and keeps the key order, which is the whole point of the exercise.

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q && uv run mypy app && uv run ruff check app tests`
Expected: 13 passed; mypy and ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/adapters/postgres/relation.py backend/tests/adapters/test_postgres_relation.py && git commit -m "feat(postgres): a constraint is one object with its columns in order"
```

---

### Task 5: Indexes and partitioning

**Files:**
- Modify: `backend/app/adapters/postgres/relation.py`
- Modify: `backend/tests/utils/relation_fixture.py`
- Modify: `backend/tests/adapters/test_postgres_relation.py`

**Interfaces:**
- Consumes: `_query`, `_models`.
- Produces: `indexes`, `partitioning`, `partition_of` filled.

- [ ] **Step 1: Add a partitioned table to the fixture**

In `SETUP`, before `CREATE VIEW`:

```sql
CREATE TABLE {SCHEMA}.events (
    id       integer NOT NULL,
    happened date NOT NULL
) PARTITION BY RANGE (happened);

CREATE TABLE {SCHEMA}.events_2026 PARTITION OF {SCHEMA}.events
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
```

- [ ] **Step 2: Add the failing tests**

```python
async def test_indexes_are_listed_with_their_method_and_predicate(
    schema: str,
) -> None:
    model = await _relation().relation_model(f"{schema}.customers")

    by_name = {index.name: index for index in model.indexes}
    partial = by_name["customers_name_idx"]
    assert partial.method == "btree"
    assert partial.columns == ["name"]
    assert partial.predicate is not None
    assert "balance" in partial.predicate
    assert partial.unique is False
    assert by_name["customers_pkey"].primary is True


async def test_a_partitioned_table_says_how_it_is_split(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.events")

    assert model.kind == "partitioned_table"
    assert model.partitioning is not None
    assert model.partitioning.strategy == "range"
    assert "happened" in model.partitioning.key


async def test_a_partition_names_its_parent_as_a_node_id(schema: str) -> None:
    model = await _relation().relation_model(f"{schema}.events_2026")

    assert model.partition_of is not None
    assert model.partition_of.parent_node_id == f"{schema}.events"
    assert "2026-01-01" in model.partition_of.bounds
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q -k "index or partition"`
Expected: FAIL — `indexes` is empty, `partitioning` is None.

- [ ] **Step 4: Add the index query and the partitioning fields**

The query:

```python
_INDEXES = """
SELECT c.relname                                       AS relation,
       ic.relname                                      AS name,
       am.amname                                       AS method,
       ix.indisunique                                  AS is_unique,
       ix.indisprimary                                 AS is_primary,
       ix.indisvalid                                   AS is_valid,
       (SELECT array_agg(att.attname ORDER BY u.ord)
          FROM unnest(string_to_array(ix.indkey::text, ' ')::int[])
               WITH ORDINALITY AS u(attnum, ord)
          JOIN pg_attribute att
            ON att.attrelid = ix.indrelid AND att.attnum = u.attnum
       )                                               AS column_names,
       pg_get_expr(ix.indpred, ix.indrelid)            AS predicate,
       pg_get_indexdef(ix.indexrelid)                  AS definition
FROM pg_index ix
JOIN pg_class ic ON ic.oid = ix.indexrelid
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am am ON am.oid = ic.relam
WHERE n.nspname = %s
"""
```

`_RELATIONS` gets three fields and three joins:

```sql
       pt.partstrat                               AS partition_strategy,
       pg_get_partkeydef(c.oid)                   AS partition_key,
       parent.relname                             AS parent_relation,
       pg_get_expr(c.relpartbound, c.oid)         AS partition_bounds
...
LEFT JOIN pg_partitioned_table pt ON pt.partrelid = c.oid
LEFT JOIN pg_inherits inh ON inh.inhrelid = c.oid
LEFT JOIN pg_class parent ON parent.oid = inh.inhparent
```

Index assembly:

```python
def _index(row: dict[str, Any]) -> Index:
    return Index(
        name=str(row["name"]),
        method=str(row["method"]),
        unique=bool(row["is_unique"]),
        primary=bool(row["is_primary"]),
        valid=bool(row["is_valid"]),
        # An expression key has attnum 0, joins to no attribute and so drops
        # out here: it has no column name, and the whole of it is visible in
        # the printed definition instead.
        columns=_names(row.get("column_names")),
        predicate=row.get("predicate"),
        definition=str(row["definition"]),
    )
```

In `_models` — in the same way as the constraints:

```python
        index_rows = await self._query(_INDEXES, schema, relation, "c.relname")
        indexes: dict[str, list[Index]] = {}
        for row in index_rows:
            indexes.setdefault(str(row["relation"]), []).append(_index(row))
```

and as the fifth argument to `_relation_model`, where it goes into the `indexes` field.

The imports in `relation.py` are extended with `Index`, `Partitioning`, `PartitionOf` from `app.adapters.relation`.

and in `_relation_model` — the partitioning:

```python
    strategy = row.get("partition_strategy")
    partitioning = (
        Partitioning(
            strategy={"r": "range", "l": "list", "h": "hash"}[str(strategy)],
            key=str(row.get("partition_key") or ""),
        )
        if strategy is not None
        else None
    )
    parent = row.get("parent_relation")
    partition_of = (
        PartitionOf(
            parent_node_id=f"{schema}.{parent}",
            bounds=str(row.get("partition_bounds") or ""),
        )
        if parent is not None
        else None
    )
```

- [ ] **Step 5: Run the tests**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_relation.py -q && uv run mypy app && uv run ruff check app tests`
Expected: 16 passed; mypy and ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/postgres/relation.py backend/tests/utils/relation_fixture.py backend/tests/adapters/test_postgres_relation.py && git commit -m "feat(postgres): a relation reports its indexes and how it is partitioned"
```

---

### Task 6: Capability and route

**Files:**
- Modify: `backend/app/adapters/registry.py`
- Modify: `backend/app/connectors/routes.py`
- Modify: `backend/tests/adapters/test_routes.py`
- Create: tests in `backend/tests/connectors/` — see step 1

**Interfaces:**
- Consumes: `SupportsRelationModel` (Task 1), `PostgresAdapter.relation_model` (Task 3).
- Produces: `GET /api/v1/connectors/{connector_id}/relation-model?node_id=...`, answering with `RelationModel`.

- [ ] **Step 1: Write the failing route tests**

A new file `backend/tests/connectors/test_relation_model_routes.py`, modelled on `test_fetch_routes.py` — it has no connector fixtures, it has a local helper:

```python
import uuid

from httpx import AsyncClient

from app.core.config import settings
from tests.utils.database import working_postgres_options

BASE = f"{settings.API_V1_STR}/connectors"


async def _postgres_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation {uuid.uuid4()}",
            "adapter_type": "postgres",
            "options": working_postgres_options(),
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def _file_connector(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        f"{BASE}/",
        headers=headers,
        json={
            "name": f"relation files {uuid.uuid4()}",
            "adapter_type": "file",
            "options": {"path": "."},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_describes_a_relation(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "pg_catalog.pg_class"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "pg_class"
    assert body["kind"] == "table"
    names = [column["name"] for column in body["columns"]]
    assert "relname" in names
    # The type arrives taken apart, not as one string doing three jobs.
    relname = next(c for c in body["columns"] if c["name"] == "relname")
    assert relname["type"]["sql"] == "name"
    assert relname["type"]["category"] == "string"


async def test_a_relation_that_is_gone_is_not_a_failure(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    connector_id = await _postgres_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "public.no_such_table"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 404


async def test_a_source_without_relations_says_so(
    client: AsyncClient, normal_user_token_headers: dict[str, str]
) -> None:
    """A capability the source lacks is answered, not stubbed."""
    connector_id = await _file_connector(client, normal_user_token_headers)

    response = await client.get(
        f"{BASE}/{connector_id}/relation-model",
        params={"node_id": "anything"},
        headers=normal_user_token_headers,
    )

    assert response.status_code == 501


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        f"{BASE}/{uuid.uuid4()}/relation-model", params={"node_id": "public.x"}
    )

    assert response.status_code == 401
```

If `relname["type"]["sql"]` turns out to be something other than `name`, record what the server returned rather than weakening the check to "non-empty".

And in `backend/tests/adapters/test_routes.py`, in the test `test_reports_what_a_type_can_do`:

```python
    titles = {capability["title"] for capability in types["postgres"]["capabilities"]}
    assert "Describe a relation" in titles
    file_titles = {
        capability["title"] for capability in types["file"]["capabilities"]
    }
    assert "Describe a relation" not in file_titles
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/connectors -q -k relation_model && uv run pytest tests/adapters/test_routes.py -q -k what_a_type_can_do`
Expected: FAIL — 404 on an unknown route; the capability is not named.

- [ ] **Step 3: Add the capability to the registry**

In `backend/app/adapters/registry.py`, in `capabilities_of`, after the line about `SupportsFetch`:

```python
    if issubclass(driver, SupportsRelationModel):
        found.append(Capability(group="explore", title="Describe a relation"))
```

and the import of `SupportsRelationModel` from `app.adapters.protocol`.

- [ ] **Step 4: Add the route**

In `backend/app/connectors/routes.py`, beside `read_catalog`:

```python
@router.get("/{connector_id}/relation-model", response_model=RelationModel)
async def read_relation_model(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    node_id: str,
) -> Any:
    """
    Describe one relation named by node_id: columns, constraints, indexes.

    node_id is opaque: only the adapter that produced it knows how to read it.
    A GET because it is a read, and because it changes far less often than a
    page of rows — the client caches it by URL.
    """
    adapter = await _adapter_for(session, connector_id, current_user, resources)
    if not isinstance(adapter, SupportsRelationModel):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not describe relations",
                "error_kind": "config",
            },
        )
    try:
        return await adapter.relation_model(node_id)
    except NodeNotFound as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)})
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["query", "node_id"], "msg": str(exc), "type": "value_error"}],
        )
    except AdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": exc.message, "error_kind": exc.error_kind},
        )
```

plus the imports `RelationModel` and `SupportsRelationModel`. The order of the `except` clauses matters: `NodeNotFound` is caught before `ValueError` if it inherits from it — check in `protocol.py` and put it first if needed.

- [ ] **Step 5: Run everything**

Run: `cd backend && uv run pytest tests/ -q && uv run mypy app && uv run ruff check app tests && uv run lint-imports`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add backend/app/adapters/registry.py backend/app/connectors/routes.py backend/tests && git commit -m "feat(api): ask a source to describe one of its relations"
```

---

### Task 7: The catalog stops descending into a table

**Files:**
- Modify: `backend/app/adapters/catalog.py`
- Modify: `backend/app/adapters/postgres/catalog.py`
- Modify: `backend/tests/adapters/test_catalog.py`, `test_postgres_catalog.py`
- Modify: `frontend/src/features/catalog/nodes.ts`, `nodes.spec.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CatalogNode` without `ColumnNode`; `NodeKind` without `"column"`.

- [ ] **Step 1: Adjust the tests to the new behaviour**

In `backend/tests/adapters/test_postgres_catalog.py` delete the tests that list a table's columns and replace them with one:

```python
async def test_a_table_is_a_leaf_now_that_its_columns_come_from_the_model() -> None:
    """Columns were fetched by a second query and shown to nobody.

    The catalog list gave a column the role `hidden`, so `_list_columns` cost a
    round trip for a node that never reached the screen. The structure panel
    asks the relation model instead — one description, not two.
    """
    nodes = await _adapter().list_children("public")

    table = next(node for node in nodes if isinstance(node, TableNode))
    assert table.has_children is False
```

Replace the test on `path_to` that reaches a column (line ~152) with a path ending at a table.

In `backend/tests/adapters/test_catalog.py` remove the construction of `ColumnNode` and its check in the union.

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/adapters/test_postgres_catalog.py -q`
Expected: FAIL — `has_children` is still True.

- [ ] **Step 3: Remove columns from the catalog**

In `backend/app/adapters/catalog.py` delete the class `ColumnNode`, remove it from `CatalogNode` and `"column"` from `NodeKind`.

In `backend/app/adapters/postgres/catalog.py` delete the method `_list_columns` and its call, remove the import of `ColumnNode`, set `has_children=False` where `TableNode` is built (and `ViewNode`, if it sets it). In `path_to` remove the branch that parses the third segment: an id of the form `schema.table.column` no longer exists.

- [ ] **Step 4: Adjust the frontend**

In `frontend/src/features/catalog/nodes.ts` remove `column` from `ROLES` and `ICONS`, remove the `case "column"` branch (line ~91). In `nodes.spec.ts` remove the `roleOfKind("column")` test and the object with `kind: "column"`.

- [ ] **Step 5: Regenerate the client**

```bash
docker compose up -d --build backend && bash scripts/generate-client.sh
```

- [ ] **Step 6: Run everything**

Run: `cd backend && uv run pytest tests/ -q && uv run mypy app` and `cd frontend && bun run type-check && bun run lint && bun run test:unit`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "refactor(catalog): columns are described once, by the relation model"
```

---

### Task 8: Loading the model and the screen's pure logic

**Files:**
- Create: `frontend/src/features/structure/api.ts`
- Create: `frontend/src/features/structure/model.ts`
- Create: `frontend/src/features/structure/model.spec.ts`

**Interfaces:**
- Consumes: the generated client `ConnectorsService.readRelationModel`.
- Produces: `useRelationModel(connectorId, nodeId)`; `relationModelKey`; `badgesFor(model, columnName): ColumnBadge[]`; `foreignKeyLabel(key): string`; the type `ColumnBadge = { kind: "primary_key" | "foreign_key" | "unique" | "index"; label: string; tooltip: string }`.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/structure/model.spec.ts`:

```ts
import { describe, expect, it } from "vitest"

import { badgesFor, foreignKeyLabel } from "./model"
import type { RelationModel } from "./model"

const model: RelationModel = {
  node_id: "public.customers",
  schema_name: "public",
  name: "customers",
  kind: "table",
  owner: "postgres",
  persistence: "permanent",
  columns: [],
  constraints: [
    { kind: "primary_key", name: "customers_pkey", columns: ["id"] },
    {
      kind: "foreign_key",
      name: "customers_region_fkey",
      columns: ["region_id", "region_code"],
      target_node_id: "public.regions",
      target_columns: ["id", "code"],
      on_update: "cascade",
      on_delete: "restrict",
      match: "simple",
    },
    { kind: "unique", name: "customers_name_unique", columns: ["name"], nulls_not_distinct: false },
  ],
  indexes: [
    { name: "customers_name_idx", method: "btree", unique: false, primary: false, valid: true, columns: ["name"], definition: "CREATE INDEX ..." },
  ],
  partitioning: null,
  partition_of: null,
} as RelationModel

describe("badgesFor", () => {
  it("marks the column a primary key is made of", () => {
    expect(badgesFor(model, "id").map((badge) => badge.kind)).toEqual(["primary_key"])
  })

  it("marks every column of a composite foreign key, not just the first", () => {
    expect(badgesFor(model, "region_id").map((badge) => badge.kind)).toEqual(["foreign_key"])
    expect(badgesFor(model, "region_code").map((badge) => badge.kind)).toEqual(["foreign_key"])
  })

  it("gives a column in several constraints a badge for each", () => {
    expect(badgesFor(model, "name").map((badge) => badge.kind)).toEqual(["unique", "index"])
  })

  it("gives an untouched column none", () => {
    expect(badgesFor(model, "balance")).toEqual([])
  })
})

describe("foreignKeyLabel", () => {
  it("names the target and pairs the columns in key order", () => {
    const key = model.constraints[1]
    expect(foreignKeyLabel(key as never)).toBe(
      "region_id, region_code → public.regions (id, code)"
    )
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && bun run test:unit src/features/structure/model.spec.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the pure logic**

`frontend/src/features/structure/model.ts`:

```ts
import type { connectorsReadRelationModelResponses } from "@/client"

/** The model as the API returns it. */
export type RelationModel = connectorsReadRelationModelResponses[200]
export type Constraint = RelationModel["constraints"][number]
export type ForeignKey = Extract<Constraint, { kind: "foreign_key" }>
export type Column = RelationModel["columns"][number]

export interface ColumnBadge {
  kind: "primary_key" | "foreign_key" | "unique" | "index"
  label: string
  tooltip: string
}

/**
 * What a column is marked with, gathered from the table-level constraints.
 *
 * The server reports a constraint once, with its columns in key order; the
 * screen needs the opposite view. Doing it here rather than in the component
 * is what makes it testable without mounting anything — and the old
 * application's `allConstraints`, a per-column copy assembled on the client,
 * is exactly what this replaces.
 */
export function badgesFor(model: RelationModel, columnName: string): ColumnBadge[] {
  const badges: ColumnBadge[] = []

  for (const constraint of model.constraints) {
    if (constraint.kind === "check" || constraint.kind === "exclude") continue
    if (!constraint.columns.includes(columnName)) continue
    if (constraint.kind === "primary_key") {
      badges.push({ kind: "primary_key", label: "PK", tooltip: constraint.name })
    } else if (constraint.kind === "foreign_key") {
      badges.push({
        kind: "foreign_key",
        label: "FK",
        tooltip: foreignKeyLabel(constraint),
      })
    } else {
      badges.push({ kind: "unique", label: "U", tooltip: constraint.name })
    }
  }

  for (const index of model.indexes) {
    // A primary key already has its own badge, and its index would repeat it.
    if (index.primary || index.unique) continue
    if (index.columns.includes(columnName)) {
      badges.push({ kind: "index", label: "IX", tooltip: index.name })
    }
  }

  return badges
}

/** One line describing where a foreign key points, columns paired in order. */
export function foreignKeyLabel(key: ForeignKey): string {
  return `${key.columns.join(", ")} → ${key.target_node_id} (${key.target_columns.join(", ")})`
}
```

`frontend/src/features/structure/api.ts`:

```ts
import { useQuery } from "@tanstack/vue-query"
import { computed } from "vue"
import type { Ref } from "vue"

import { ConnectorsService } from "@/client"

export const relationModelKey = (connectorId: string, nodeId: string) =>
  ["relationModel", connectorId, nodeId] as const

/**
 * The structure of one relation.
 *
 * Kept fresh for a long time on purpose: a model changes when something is
 * altered, which is far rarer than a page of rows changing. The server-side
 * cache is a later round; until then this is the whole of it.
 */
export function useRelationModel(connectorId: Ref<string>, nodeId: Ref<string>) {
  return useQuery({
    queryKey: computed(() => relationModelKey(connectorId.value, nodeId.value)),
    queryFn: async () =>
      (
        await ConnectorsService.readRelationModel({
          path: { connector_id: connectorId.value },
          query: { node_id: nodeId.value },
        })
      ).data,
    staleTime: 5 * 60_000,
  })
}
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && bun run test:unit src/features/structure/model.spec.ts && bun run type-check && bun run lint`
Expected: 5 passed; type-check and lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/structure && git commit -m "feat(structure): read a relation model and lay its constraints out per column"
```

---

### Task 9: Structure panel

**Files:**
- Create: `frontend/src/features/structure/StructureView.vue`
- Create: `frontend/src/features/workspace/panels/StructurePanel.vue`
- Modify: `frontend/src/features/workspace/panels.ts`, `panels.spec.ts`
- Modify: `frontend/src/features/workspace/state.ts`, `WorkspacePage.vue`
- Modify: `frontend/src/features/catalog/nodes.ts`, `nodes.spec.ts`, `CatalogList.vue`
- Modify: `frontend/src/features/workspace/panels/CatalogPanel.vue`

**Interfaces:**
- Consumes: `useRelationModel`, `badgesFor`, `foreignKeyLabel` (Task 8).
- Produces: the panel kind `structure` with the fields `{ id, kind: "structure", connectorId, nodeId, title, connectorName, adapterType }`; `structurePanelId(connectorId, nodeId)`; `openStructure(request)` in `workspaceActionsKey`; `describable: boolean` on `ListNode`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/features/workspace/panels.spec.ts` — modelled on the existing tests for `rows`:

```ts
it("puts structure in the column of work", () => {
  expect(roleOf({ id: "s", kind: "structure", connectorId: "c1", nodeId: "public.orders", title: "orders", connectorName: "db", adapterType: "postgres" })).toBe("work")
})

it("identifies a structure panel by what it shows", () => {
  expect(structurePanelId("c1", "public.orders")).toBe(structurePanelId("c1", "public.orders"))
  expect(structurePanelId("c1", "public.orders")).not.toBe(rowsPanelId("c1", "public.orders"))
})
```

In `frontend/src/features/catalog/nodes.spec.ts`:

```ts
it("offers structure for a relation and not for a file", () => {
  expect(listNodeOf({ kind: "table", id: "public.orders", name: "orders", has_children: false }).describable).toBe(true)
  expect(listNodeOf({ kind: "view", id: "public.v", name: "v", has_children: false }).describable).toBe(true)
  expect(listNodeOf({ kind: "file", id: "a.csv", name: "a.csv", has_children: false, size_bytes: 1, content_kind: "table" }).describable).toBe(false)
})
```

Take the name of the factory (`listNodeOf` or whatever it is called in `nodes.ts`) from the existing file.

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && bun run test:unit src/features/workspace/panels.spec.ts src/features/catalog/nodes.spec.ts`
Expected: FAIL — `structurePanelId` is not exported, `describable` does not exist.

- [ ] **Step 3: Extend the panel union**

In `frontend/src/features/workspace/panels.ts`, in `panelSchema`:

```ts
  z.object({
    id: z.string(),
    kind: z.literal("structure"),
    connectorId: z.string(),
    nodeId: z.string(),
    title: z.string(),
    connectorName: z.string(),
    adapterType: z.string(),
  }),
```

```ts
export const structurePanelId = (connectorId: string, nodeId: string) =>
  `structure:${connectorId}:${nodeId}`
```

in `roleOf` — `case "structure": return "work"`; in `lookOf`:

```ts
    case "structure":
      return {
        title: panel.title,
        icon: "account_tree",
        iconTooltip: `${panel.connectorName} · Structure`,
        reloadTooltip: "Re-read the structure",
      }
```

in `componentOf`:

```ts
    case "structure":
      return boundComponent(panel.id, () =>
        h(StructurePanelView, {
          panelId: panel.id,
          connectorId: panel.connectorId,
          nodeId: panel.nodeId,
        })
      )
```

and the import of `StructurePanelView`.

- [ ] **Step 4: Write the screen**

`frontend/src/features/structure/StructureView.vue`:

```vue
<script setup lang="ts">
import { computed, toRef } from "vue"

import { useRelationModel } from "@/features/structure/api"
import { badgesFor, foreignKeyLabel } from "@/features/structure/model"
import type { ForeignKey } from "@/features/structure/model"
import { messageOf } from "@/shared/api/errors"
import {
  AppBadge,
  AppBanner,
  AppEmptyState,
  AppSection,
  AppSpinner,
  AppTable,
  AppTooltip,
} from "@/shared/ui"

const props = defineProps<{ connectorId: string; nodeId: string }>()

const query = useRelationModel(toRef(props, "connectorId"), toRef(props, "nodeId"))

/** Exposed so the panel can answer the tab's reload button. */
defineExpose({ reload: async () => void (await query.refetch()) })

const COLUMNS = [
  { name: "name", label: "Column", field: "name", align: "left" as const },
  { name: "type", label: "Type", field: "type", align: "left" as const },
  { name: "nullable", label: "Null", field: "nullable", align: "left" as const },
  { name: "default", label: "Default", field: "default", align: "left" as const },
  { name: "keys", label: "Keys", field: "keys", align: "left" as const },
]

const rows = computed(() =>
  (query.data.value?.columns ?? []).map((column) => ({
    name: column.name,
    // The type as the source would write it in DDL: one string, not rebuilt here.
    type: column.type.sql,
    nullable: column.nullable ? "yes" : "no",
    default: column.generated ?? column.default ?? "",
    keys: query.data.value === undefined ? [] : badgesFor(query.data.value, column.name),
  }))
)

const foreignKeys = computed(
  () =>
    (query.data.value?.constraints ?? []).filter(
      (constraint) => constraint.kind === "foreign_key"
    ) as ForeignKey[]
)

const otherConstraints = computed(() =>
  (query.data.value?.constraints ?? []).filter(
    (constraint) => constraint.kind !== "foreign_key"
  )
)

const errorText = computed(() =>
  query.error.value === null
    ? ""
    : messageOf(query.error.value, "Could not read the structure")
)
</script>

<template>
  <div
    class="structure-view"
    data-testid="structure-view"
  >
    <AppBanner
      v-if="errorText"
      tone="error"
      data-testid="structure-error"
    >
      {{ errorText }}
    </AppBanner>

    <AppSpinner v-else-if="query.isPending.value" />

    <template v-else-if="query.data.value">
      <AppSection title="Columns">
        <AppTable
          :rows="rows"
          :columns="COLUMNS"
          row-key="name"
          compact
          :paged="false"
          empty-text="No columns"
        >
          <template #body-cell-keys="cellProps">
            <q-td :props="cellProps">
              <AppBadge
                v-for="badge in cellProps.value"
                :key="badge.kind"
                :label="badge.label"
                :data-testid="`structure-badge-${badge.kind}`"
              >
                <AppTooltip>{{ badge.tooltip }}</AppTooltip>
              </AppBadge>
            </q-td>
          </template>
        </AppTable>
      </AppSection>

      <AppSection title="Foreign keys">
        <AppEmptyState
          v-if="foreignKeys.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="key in foreignKeys"
            :key="key.name"
            data-testid="structure-fk"
          >
            {{ foreignKeyLabel(key) }}
          </li>
        </ul>
      </AppSection>

      <AppSection title="Constraints">
        <AppEmptyState
          v-if="otherConstraints.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="constraint in otherConstraints"
            :key="constraint.name"
          >
            {{ constraint.kind }} · {{ constraint.name }}
          </li>
        </ul>
      </AppSection>

      <AppSection title="Indexes">
        <AppEmptyState
          v-if="query.data.value.indexes.length === 0"
          text="None"
        />
        <ul
          v-else
          class="structure-view__list"
        >
          <li
            v-for="index in query.data.value.indexes"
            :key="index.name"
          >
            {{ index.name }} · {{ index.method }}
            <template v-if="index.columns.length">
              ({{ index.columns.join(", ") }})
            </template>
          </li>
        </ul>
      </AppSection>
    </template>
  </div>
</template>

<style scoped>
.structure-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: auto;
}
.structure-view__list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}
</style>
```

Check against `src/shared/ui/index.ts` that `AppBadge`, `AppSection`, `AppTooltip` accept these props; if a prop's name is different, take the one declared there rather than adding a new one.

`frontend/src/features/workspace/panels/StructurePanel.vue`:

```vue
<script setup lang="ts">
import { useTemplateRef } from "vue"

import StructureView from "@/features/structure/StructureView.vue"
import { useReloadable } from "@/features/workspace/reloadable"

/** The structure of one relation, in its own tab. */
const props = defineProps<{ panelId: string; connectorId: string; nodeId: string }>()

const view = useTemplateRef<{ reload: () => Promise<void> }>("view")

useReloadable(props.panelId, async () => {
  await view.value?.reload()
})
</script>

<template>
  <div class="structure-panel">
    <StructureView
      ref="view"
      :connector-id="connectorId"
      :node-id="nodeId"
    />
  </div>
</template>

<style scoped>
.structure-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 4px;
}
</style>
```

- [ ] **Step 5: Open the panel from the catalog**

In `nodes.ts` — a `describable` field on `ListNode`, computed from the node's kind:

```ts
/**
 * Whether this node has a structure to describe. A table and a view do; a
 * file and a directory do not, and asking would get 501 from the source.
 */
const DESCRIBABLE: Record<CatalogNode["kind"], boolean> = {
  schema: false,
  table: true,
  view: true,
  directory: false,
  file: false,
}
```

In `CatalogList.vue` — after `catalog-list__name`, before the captions:

```html
        <span
          v-if="node.describable"
          @click.stop
        >
          <AppIconButton
            icon="account_tree"
            tooltip="Show structure"
            dense
            :data-testid="`catalog-structure-${node.label}`"
            @click="emit('describe', node)"
          />
        </span>
```

plus `describe` in `defineEmits`.

In `state.ts` — `openStructure: (request: OpenStructureRequest) => void`; in `WorkspacePage.vue` — the implementation beside `openRows`, through `structurePanelId`. In `CatalogPanel.vue` — a `@describe` handler that calls `workspace.openStructure` with the same fields that `onOpen` passes to `openRows`.

- [ ] **Step 6: Run everything**

Run: `cd frontend && bun run test:unit && bun run type-check && bun run lint`
Expected: all green. The `/ui-kit` showcase test is not touched: there are no new kit components.

- [ ] **Step 7: Commit**

```bash
git add frontend/src && git commit -m "feat(structure): a relation gets a tab of its own"
```

---

### Task 10: Browser scenario

**Files:**
- Create: `frontend/tests/structure.spec.ts`

**Interfaces:**
- Consumes: everything before.
- Produces: proof that a person sees it.

**Correction during execution:** PostgreSQL's system catalogs do not declare
primary keys through `pg_constraint`, so `pg_attribute` cannot prove the
PK badge. The scenario uses `demo_lab.app_users` from the dev fixture: it has both
a PK and an FK. The structure is opened and checked first, then the rows are opened,
after which the inactive structure tab is moved into a neighbouring section. If
it is moved earlier, the new rows tab picks the work section that was created and hides
the structure again — that checks the wrong result.

- [ ] **Step 1: Write the scenario**

`frontend/tests/structure.spec.ts`:

```ts
import { expect, test } from "@playwright/test"

import { createPostgresConnector } from "./utils/connectors"
import { login } from "./utils/login"
import { openNode, pickSchema } from "./utils/catalog"
import { connectorRow, deleteConnector, openConnector } from "./utils/workspace"

test("shows the structure of a relation beside its rows", async ({ page }) => {
  const name = `e2e-structure-${Date.now()}`
  await login(page)
  await createPostgresConnector(page, name)

  await openConnector(page, name)
  // pg_catalog rather than an application table: pg_attribute is always there,
  // always has a primary key and always has columns of several types, so none
  // of the assertions below depend on data the test created.
  await pickSchema(page, "pg_catalog")

  await page.getByTestId("catalog-structure-pg_attribute").click()

  const view = page.getByTestId("structure-view")
  await expect(view).toBeVisible()
  // A column, and the type as the server would write it in DDL.
  await expect(view).toContainText("attname")
  await expect(view).toContainText("name")
  // The primary key is marked on the column it is made of.
  await expect(view.getByTestId("structure-badge-primary_key").first()).toBeVisible()

  // The rows of the same relation, in a tab of their own beside it: this is
  // the whole reason structure is a panel and not a switch inside the grid.
  await openNode(page, "pg_attribute")
  await expect(page.getByTestId("row-grid")).toBeVisible()
  await expect(view).toBeVisible()

  await deleteConnector(page, name)
  await expect(connectorRow(page, name)).toHaveCount(0)
})
```

The database host in the connector is already written by `createPostgresConnector` the way the backend sees it in the compose network — `db`, not `localhost`; the connection check runs on the server.

If `pg_attribute` in this version of PostgreSQL turns out to have no declared primary key, take `pg_class` — but do not replace the badge check with something weaker: without it the scenario stops proving that constraints reached the screen.

- [ ] **Step 2: Bring everything up and run**

```bash
docker compose up -d db backend
```

Run: `cd frontend && bunx playwright test tests/structure.spec.ts`
Expected: PASS.

- [ ] **Step 3: Make sure the scenario actually checks**

Temporarily remove `v-if="node.describable"` from the button in `CatalogList.vue` — no, that would show it everywhere. Instead, temporarily change `data-testid="structure-view"` to another name and run the scenario.
Expected: FAIL on a wait timeout. Restore the name, make sure it PASSes again.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/structure.spec.ts && git commit -m "test(e2e): the structure of a relation is on screen"
```

---

### Task 11: Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/architecture/adapters.md`

- [ ] **Step 1: Record the decision**

In the decision table of `AGENTS.md`, after D21:

```
| D22 | A source describes a relation in full, and a column type is an object | [adapters](docs/architecture/adapters.md) |
```

In "What already works", as a separate list item:

```
- A relation describes itself: columns with the type taken apart — what to
  write in DDL, and what the value is — constraints with their columns in key
  order, indexes, and how the table is partitioned. It opens in a tab of its
  own, which can sit beside the rows of the same table.
```

In `docs/architecture/adapters.md` — the home of the decision: the statement, the reasoning (the three jobs of one string, why `typname` did not get into the model, why a constraint is a top-level object, why the query is written over a set) and the known deviation: there is no server-side cache, and a whole schema is not served at once.

- [ ] **Step 2: Check**

Run: `bash scripts/check-docs.sh`
Expected: `docs ok: … AGENTS.md is <N> of 24576 bytes`

- [ ] **Step 3: Run everything at once**

```bash
cd backend && uv run pytest tests/ -q && uv run mypy app && uv run ruff check app tests && uv run lint-imports
cd ../frontend && bun run type-check && bun run lint && bun run test:unit && bunx playwright test
cd .. && bash scripts/check-docs.sh
```

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md docs/architecture/adapters.md && git commit -m "docs: a source describes a relation in full"
```

# The relation model

Date: 2026-08-24
Status: agreed
Round: 8

## Goal

The application puts its weight on databases, yet it knows four facts about a
table: the column name, the type as a string, nullable and the primary-key
flag. That is not enough for almost anything planned: the grid needs a record
key and behaviour by type, foreign-key navigation needs the links, structure
editing needs DDL, the schema diagram needs a graph.

The round introduces one thing: **a source can describe its relation in full**.
Everything listed then takes the description from here instead of obtaining it
anew.

## What was found in the old application

`GET_SYSTEM_ALL_COLUMN_INFO` is a template key that every SQL adapter has:
postgres, clickhouse, duckdb, mssql, oracle. One question, each dialect with
its own answer. This plainly asks to be a capability.

The postgres query itself, in one pass over `pg_attribute`, gives the type,
`udt_name`, physical storage, length, nullable, generatedness, the default, the
constraint kind, the foreign-key target and an aggregated list of indexes per
column. The idea is right, and it is what gets ported.

Not every decision is ported. Two places are broken, and neither may be
reproduced.

**The first is the type name.** The model returned two names, and neither is
fit for `CREATE TABLE`:

| What is in the query | `integer[]` | `varchar(50)` |
| --- | --- | --- |
| `t.typname` (`udt_name`) | `_int4` | `varchar` |
| `atttypid::regtype` | `integer[]` | `character varying` — the modifier is lost |
| `format_type(atttypid, atttypmod)` | `integer[]` | `character varying(50)` |

`_int4` is the internal name of the array in `pg_type`; it cannot be put into
DDL. The fix is visible in the code: `EXACT_DEFINITION_TYPES` with
`atttypid::regtype` is called only from `backup_utils.py`, that is, where DDL
is written, as a separate query for each column and with the table name
substituted through `.format`. A patch in exactly that place, and an incomplete
one: it turns `varchar(50)` into `character varying`.

**The second is composite keys.** `LEFT JOIN pg_constraint ON attnum = ANY(conkey)`
gives a row for each "column × constraint" pair, and a composite foreign key is
spread across columns through `array_position(conkey, attnum)`. A link of two
columns is represented as two independent ones. For navigating along such a
key this is wrong: navigation has to go by the pair of values at once.

## Decisions

### R1. Describing a relation is a separate capability

```python
@runtime_checkable
class SupportsRelationModel(Protocol):
    async def relation_model(self, node_id: str) -> RelationModel: ...
```

Next to `SupportsCatalog` and `SupportsFetch`, by the letter of D2: the
contract requires a minimum, the rest are independent capabilities. The file
source does not implement it and answers 501 with the same code it already
answers with for everything it cannot do.

Rejected: folding it into `SupportsCatalog` ("if you can show children, you
can describe a table"): a queue and an object store have a catalog and have no
relations at all.

Rejected: returning the model together with `FetchResult`: the model is heavier
than a page of rows and changes incomparably less often, and sending it with
every page means paying the full price on every scroll.

### R2. A column type is an object, not a string

One string cannot do three jobs: show to a person, decide behaviour, go into
DDL. The old application tried, and the breakage examined above is the price
of the attempt.

```
ColumnType
  sql: str        # format_type(atttypid, atttypmod) — what pg_dump writes types with
  category: Literal["number","string","boolean","datetime","binary","json",
                    "uuid","network","geometric","range","enum","composite",
                    "array","other"]
  element: ColumnType | None    # when category == "array"
  dimensions: int = 0
  enum_values: list[str] | None      # when category == "enum"
  length: int | None                 # varchar(50) -> 50
  precision: int | None              # numeric(10,2) -> 10
  scale: int | None                  # numeric(10,2) -> 2
```

`category` is the place where the grid stops parsing the type string with a
regular expression, and filters stop offering `contains` for `int`. It is
computed once on the server: the same computation on the backend and the
frontend is a defect per ENGINEERING.md.

It is taken from `pg_type.typcategory`, which already has `A` array, `B`
boolean, `C` composite, `D` date, `E` enum, `G` geometric, `I` network, `N`
number, `R` range, `S` string. What Postgres dumps into `U` is sorted out by a
separate table: `json`, `jsonb`, `uuid`, `bytea`.

`typname` is not put into the model at all. If the field exists, sooner or
later it will be put into DDL, exactly as happened in the old application. If a
real need appears, it will be added under a name that cannot be confused with a
writable one.

### R3. A constraint is a top-level object

A discriminated union by `kind`, like `CatalogNode`:

- `primary_key` — name, ordered columns;
- `unique` — name, columns, `nulls_not_distinct`;
- `foreign_key` — name, own columns, `target_node_id`, foreign columns,
  `on_update`, `on_delete`, `match`;
- `check` — name, expression, columns involved;
- `exclude` — name, expression.

Column order is taken from `conkey` as is and is never sorted — that is what
broke the composite key in the old application. The column keeps only
references to constraints, not copies of them: the gluing on the client that
lived in `allConstraints` disappears.

### R4. A foreign key carries `target_node_id`

Not a "schema + table" pair from which the client would assemble the
identifier itself. This is the letter of D21: the source says where a node
lives, the client neither parses nor assembles ids. The adapter builds it, in
the same form in which the catalog returns it.

Thanks to this one decision, navigating along a key in the grid will later
need no second design — only a screen.

### R5. The query is written over a set of relations, and called for one

A private `_models(schema, relation: str | None)`: a join through
`pg_namespace`, the filter by relation name an optional predicate. The public
`relation_model` calls it with a name and returns one model.

The short path — `WHERE attrelid = %s::regclass`, by a single oid — is
forbidden precisely because it does not generalise: a whole schema would
require rewriting the query rather than dropping a predicate. A schema at once
will come together with the cache and will be the same call without a name.

Four queries, in sequence: relations, columns, constraints, indexes. Not in
parallel — they share one pooled connection, and psycopg does not multiplex on
one connection.

Nothing is built by string formatting: identifiers through `sql.Identifier`,
values through placeholders (D2c). No relation — `NodeNotFound`, that is, 404
and not 502: the node may have been removed while the tab was open.

### R6. The catalog stops descending into a table

`ColumnNode` is built today by the `_list_columns` query and shown to nobody:
`nodes.ts` gives a column the role `hidden`, and nothing on the frontend reads
it. So it is a second query for the same facts, which can diverge from the
first, for a result that is not visible.

`_list_columns` and `ColumnNode` are removed, `TableNode.has_children` becomes
`false`. The screen does not change: a table is a `leaf` already.

`fetch._columns` stays and is commented as deliberately separate. It describes
a **result**, not a relation: a result may later be an arbitrary query that has
no model at all. These are different things, not duplication.

### R7. Structure is a separate panel kind

`structure` in the closed union of panels, its own component, its own
`structurePanelId`. A test next to `panels.ts` fails if a kind is added without
a component.

Rejected: a "Rows / Structure" switch inside the `rows` panel: it takes away
the one thing for which tabs are dragged with the mouse in this application —
the ability to put the structure next to the rows in a neighbouring column.

Rejected: "build the model, the screen later": then out of thirty fields a
person would see zero, and the working rule says it plainly — a green unit test
does not mean the result is visible. That already happened with captions in the
tree.

### R8. There is no cache in this round

The model is a pure value addressed by the pair `(connector, node_id)`, so a
cache later fits as a wrapper and rewrites nothing. On the client vue-query
caches it by itself, with a long `staleTime` (D6).

A server cache is not introduced: it brings the problem of staleness — DDL
changes the model — and there are no measurements yet that it is needed. That
is the next round, together with the schema at once from R5.

## What is done

**Server.** `app/adapters/relation.py` — the model types, no SQL; the name is
`relation`, not `model`, so it is not confused with the application database's
models. `SupportsRelationModel` in `adapters/protocol.py`.
`app/adapters/postgres/relation.py` — four queries and assembly. `_list_columns`
and `ColumnNode` out of `postgres/catalog.py` and `adapters/catalog.py`.
`GET /connectors/{id}/relation-model?node_id=...` in `connectors/routes.py`,
following `/catalog`: 501 without the capability, 404 on a vanished node, 502
on a source failure. A line in `capabilities_of`.

The model's contents: the relation — schema, name, kind, comment, owner,
persistence, row estimate, size, partitioning, parent partition; the column —
position, name, comment, type per R2, nullable, default, `identity`,
`generated` with its expression, collation, physical storage; the index —
name, columns or expression, method, uniqueness, partial predicate, validity.
`extra="forbid"` everywhere, like `CatalogNode`.

**Screen.** `features/structure/api.ts` — `useRelationModel` on vue-query;
`features/structure/model.ts` — pure functions: spread constraints over
columns, decide a column's badges, build the foreign-key caption;
`features/structure/StructureView.vue`;
`features/workspace/panels/StructurePanel.vue` plus `structure` in the union and
`structurePanelId`; `openStructure` next to `openRows` in `workspaceActionsKey`,
called from `CatalogPanel` as the second action on a table node. The client is
regenerated by `scripts/generate-client.sh`.

**Documentation.** D22 in the AGENTS.md table, its home in
`docs/architecture/adapters.md`, a line in "What already works".

There was no room for this: 142 bytes were left in AGENTS.md. The first
candidate for removal turned out to be the trap about `vue-tsc` — that is, the
budget was about to push out exactly what the file is loaded into every session
for. So the ceiling was set low, rather than the file having overgrown. It is
raised from 16 KB to 24 KB in `scripts/check-docs.sh`, as a separate change
and with a recorded reason: weakening a check on the way to a green run is what
ENGINEERING.md forbids, and a deliberate change of a wrong rule is not.

## How it is checked

The fixture is a table with a deliberately awkward structure: `integer[]`,
`varchar(50)`, `numeric(10,2)`, an enum, a generated column, `identity`, a
composite primary key and a composite foreign key.

Server:

- **a round trip through DDL**, the main test of the round: take `type.sql`
  from the model, build `CREATE TABLE`, run it, read the model of the new
  table, compare types. `_int4` does not pass it, nor does `character varying`
  without `(50)`;
- a composite foreign key arrives as one constraint with ordered columns, not
  as two links;
- `category` for an array, an enum, `jsonb`, `uuid`, `numeric`;
- the enum's `enum_values`, the array's `element` and `dimensions`;
- a view has columns and no constraints;
- a removed relation — `NodeNotFound`, the route — 404;
- the file source — 501; `capabilities_of` names the new capability;
- the existing catalog tests are green after removing `_list_columns`.

Screen:

- `model.spec.ts`: constraints are spread over columns; a column in three
  constraints gets three badges; the foreign-key caption names the target;
- Playwright, and this is the only real proof: open a table's structure from
  the catalog, see a column with its type, the primary-key badge and the
  foreign-key row with the target's name; drag the structure tab into the
  neighbouring column and see it next to the rows.

## What this round does not include

- a cache, neither a server one nor a schema at once;
- foreign-key navigation in the grid — the model only describes it;
- structure editing and any DDL;
- extension specifics: Timescale hypertables and the like are a separate
  capability;
- the file source: it has its own limits, and that is a separate round;
- triggers, rules and privileges on the relation.

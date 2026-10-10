# Catalog of source types and creating a connection

Date: 2026-08-23
Status: agreed
Subproject: 7-preparation

## Goal

Today a new connection is created like this: the "+" button opens
`ConnectorDialog`, inside which is an `AppSelect` drop-down with the source
types. While there are two types, this works. When there are eighty — and the
registry is designed for exactly that (R1: "adding a source type requires no
migration") — the drop-down stops being a choice and becomes a list in which
there is nothing to search and nothing to judge by.

What is needed is a screen that answers three questions: which source types
exist, what each of them can do, and what connecting to it looks like. The
first two — before the user has typed a single password.

## What the old application had

`myquasar/src/myapp/views/xdbview/dataplayer/` — a showcase of 84 adapters:
a sidebar of categories with counters, search, a grid of tiles, a panel sliding
in from the right with a description and capabilities, and a "Try it" button
that brought up a demo. Plus a relations tab — a graph of 19 nodes.

We carry over the form of the screen. We do not carry over:

- **the relations graph** — by the user's decision;
- **demos** — 27 of 36 demos brought up a container: generating a compose file,
  a background task, polling `docker_startup_ready`, a window with connection
  parameters. Here there is neither Docker orchestration nor a third source
  type for which a demo would make sense. A separate task, when one or the
  other appears;
- **semantic search** — `transformers.js` downloaded an embedding model into
  the browser. On two entries this is absurd, and on eighty a lexical search by
  name, category, description and capabilities is enough;
- **`connectorSearchMeta.ts`** — 931 lines of descriptions and capabilities
  written by hand on the frontend. Its own README calls this "intentional
  duplication" and lists the cost. That is not allowed here: ENGINEERING.md
  says "the same computation in the backend and the frontend is a defect, it
  belongs on the server and arrives in the response".

## Decisions

### K1. A source type describes itself, on the server

`AdapterType` in the registry gets four fields beyond the current ones:

```python
@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    category: Category            # Literal, a closed set
    description: str
    options_schema: type[BaseModel]
    adapter_class: type           # see K2
    factory: Factory
```

`Category` is `Literal["sql", "files"]`. A closed set, because a category is a
set of values, and ENGINEERING.md requires a `Literal` for that: a typo in
`@register` does not compile, rather than creating a category of one element.
The category title (`"SQL Databases"`, `"Files & Storage"`) is a table next to
the `Literal` definition, on the server, so that the frontend does not start a
second list of names.

The category icon and the type logo stay on the frontend (`adapters.ts`, where
the SVG logos already live): this is presentation, not a fact about the source,
and the server should not know about it.

### K2. Capabilities are derived, not enumerated

The list of what a type can do is not stored anywhere. It is computed from what
the driver actually implements:

| from where | what it gives |
| --- | --- |
| `issubclass(adapter_class, SupportsCatalog)` | "Browse the catalog" |
| `issubclass(adapter_class, SupportsFetch)` | "Read rows" |
| `adapter_class.action_types()` | the `title` of each action |

`issubclass` works because all three protocols are `runtime_checkable` and
consist of methods only. Of the class rather than an instance, because the
question is asked about the **type** of source: there is no connection yet, no
options, no session.

Actions are enumerated as classes rather than instances for the same reason:
`name`, `title`, `applies_to` are `ClassVar`, they need no session.
`FileActions` builds its `ActionSet` from the same tuple the registry takes the
titles from:

```python
FILE_ACTION_TYPES = (CreateFolder, Upload, Rename, Delete)
```

One tuple, two readers. A second list that can be forgotten in an update does
not exist — exactly the same construction as `secret_field_names`, which
derives the encrypted fields from `SecretStr`.

Rejected: reading the return annotation of the factory through
`get_type_hints`. No extra argument in `@register` is needed, but it is
reflection over a type hint — it breaks under `from __future__ import
annotations`, and mypy guarantees nothing about it. This is the very `hasattr`
scheme that decision R9 was written to eliminate.

This closes a known deviation from AGENTS.md: "the server does not report the
type's capabilities either".

**What the derived capabilities show.** Postgres: *Browse the catalog*,
*Read rows*. File: the same plus *New folder*, *Upload a file*, *Rename*,
*Delete*. The group is `Literal["explore", "manage"]`: the first two
capabilities answer the question "what can be looked at", actions — "what can
be changed". The ten groups of the old application will appear when there is
something to put in them.

The cost of honesty: the wording is poorer than hand-written text. "Read rows"
will not tell that Postgres can sort and paginate on the server and a file
cannot. This is a deliberate trade: a list that cannot diverge from the code is
better than a list that reads more pleasantly. When drivers start to differ
within one capability, the difference is already described in
`FetchResult.sortable` / `filterable` — that is where to take it from.

### K3. Two windows, not one with steps

The catalog is a new window of width `lg` (900px, already in `tokens.ts`). The
form is the existing `ConnectorDialog`, width `md`.

One window that changes width between steps is rejected: 900 → 520px is a
noticeable jump, and one component would carry two roles. The split also means
that editing an existing connection opens the form directly, bypassing the
catalog, without a "we did not come from the catalog" flag.

Flow:

```
"+"  →  AdapterCatalogDialog  →  pick a type  →  ConnectorDialog (type set)
                    ↑                                     │
                    └───────────── "Back" ────────────────┘

connection icon  →  ConnectorDialog (edit), no catalog
```

Both windows are owned by `WorkspacePage`, where `ConnectorDialog` lives now,
and for the same reason: both columns the window is opened from can be
collapsed, and a collapsed column renders nothing.

`editConnector(null)` stops opening the form and opens the catalog. The method
name becomes inaccurate — rename to `newConnector` / `editConnector` as two
operations.

### K4. Selecting a tile opens a panel, not the form

A click on a tile selects it and opens a panel on the right: description,
capabilities by group, a "Create connector" button. The panel is not a
dialog — the grid stays visible, and several types can be browsed in a row.

This is the place the screen exists for. A tile leading straight into the form
would turn the catalog into the same drop-down, only bigger.

A double click on a tile goes into the form at once — for someone who already
knows what they need.

### K5. The type drop-down disappears from the form

In `ConnectorDialog` the `AppSelect` with types is replaced by a line: logo,
type name, category. The type is decided in the catalog and does not change —
neither on creation nor on editing (now on editing the `AppSelect` is simply
`disable`, which leaves a non-working control on screen).

The form gets a prop `adapterType: string | null` — the type chosen in the
catalog — and a `back` event returning to the catalog. `back` is shown only
when the form was opened from the catalog.

### K6. Search is a pure function

`adapterSearch.ts` next to `adapters.ts`: the input is a list of types and a
string, the output a filtered and sorted list. Matching by name, title,
category, description and capability titles; a match in the title weighs more
than one in the description.

No components, no requests — tested without mounting, like `nodes.ts`,
`rows.ts` and `tokens.ts`.

Counting by category (`categoryCounts`) is there too, for the same reason.

### K7. There is no "Your connections" block in the panel

In the old application the panel listed connections of this type already
created. Here they are always visible in the first column of the workspace,
right behind the window. A second list of the same thing is a second home for
one command, and two homes diverge (exactly the argument from S1 by which the
connection list lost its row menu).

## What changes

### Backend

```
app/adapters/
├── registry.py      + Category, CATEGORY_TITLES, AdapterType fields,
│                      capabilities_of(); register() takes category,
│                      description, adapter_class
├── protocol.py      unchanged — the protocols are already the ones needed
├── routes.py        AdapterTypeInfo + category, category_title, description,
│                    capabilities
├── postgres/
│   └── adapter.py   @register(category="sql", description=…,
│                              adapter_class=PostgresAdapter)
└── file/
    ├── actions.py   FILE_ACTION_TYPES; FileActions builds ActionSet from it
    └── adapter.py   action_types(); @register(category="files", …)
```

### Frontend

```
frontend/src/features/connectors/
├── adapters.ts             + category icon
├── adapterSearch.ts        new: search and counting by category, pure
├── adapterSearch.spec.ts   new
├── AdapterCatalogDialog.vue new: sidebar, search, grid, panel
├── AdapterTile.vue          new
├── AdapterDetailPanel.vue   new
└── ConnectorDialog.vue      AppSelect → type line; props adapterType, back
```

`WorkspacePage.vue` owns both windows and the transitions between them.

No new components are required in `shared/ui`: a capability title is an
`AppBadge`, everything else is assembled from what exists. If one is needed,
the `/ui-kit` showcase must show it; a test checks this.

## What holds it

| Check | What it catches |
| --- | --- |
| `pytest tests/adapters/test_registry.py` | `capabilities_of` for a type with a catalog and without; action titles match `FILE_ACTION_TYPES` |
| `pytest tests/adapters/test_routes.py` | `/adapter-types/` returns the category, description and capabilities |
| `mypy app` | `Category` is closed; `adapter_class` is typed |
| `bun run test:unit` | `adapterSearch.ts`: match by capability, by description, order, counters |
| `bunx playwright test` | "+" → catalog → search → choosing a type → panel → form → "Back" → catalog |

What a green unit test does not prove is checked separately: that the
capabilities are visible on screen. The Playwright scenario reads the chips in
the panel and expects `Upload a file` among them for the `file` type and its
absence for `postgres`.

## Known deviations this adds

- **There are two categories, the sidebar is nearly empty.** "All", "SQL
  Databases" (1), "Files & Storage" (1). The form is built for the registry's
  growth, not for its size today — the same argument by which the UI kit is
  built as an alphabet.
- **Capabilities describe the type, not the connection.** The `file` driver
  declares `Delete`, but the connection root cannot be deleted — that is the
  state of a node, and only `available()` knows about it. The catalog answers
  the question "what can this type do in general", and promises a little more
  than any particular node will allow.
- **The type description is free text in `@register`.** Nothing checks that it
  exists and that it makes sense; an empty string will pass.
- **Search knows no morphology.** The Russian word for "migrations" will not
  find "migrations", the Russian word for "database" will not find "database".
  A lexical substring match, and nothing more.

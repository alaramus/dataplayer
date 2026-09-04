# Framework detection in the catalog

## Decision

D98: a schema publishes framework detections derived from its table names.
The catalog displays the detections for the selected schemas and lets each
one toggle an ordinary text filter.

## Legacy evidence

`dbwebtool/webdb/framework_analyser/check_*.py` recognizes Django, Liquibase,
WordPress and Alembic by marker tables. `core/framework_analyser.py` collects
the matches. `myquasar/src/myapp/views/ViewCatalog/ViewCatalog.vue` displays
only the first match and clicking it toggles its table pattern in the filter.

The rewrite preserves automatic detection and the clickable filter, while
showing every match. It does not port the reflection-based registry, the
Liquibase workspace inspection or the separate Django content-type row query.

## Contract and implementation

- `SchemaNode.frameworks` defaults to an empty list. Each `DetectedFramework`
  has a closed `id`, a display `title` and a literal `table_filter` supplied by
  the server. Other node kinds do not carry this field.
- The detector is a pure registry of signatures, independent of PostgreSQL.
  Django uses `django_content_type`, Alembic uses `alembic_version`, Liquibase
  uses `databasechangelog`, and WordPress uses `wp_options`. Marker matching
  ignores case. The filters are `django_`, `alembic_version`,
  `databasechangelog` and `wp_`, respectively.
- PostgreSQL obtains table names with the schema metadata query. Only ordinary
  and partitioned tables count; views and system schemas do not. No application
  rows, files or external services are read. A schema obtained through the
  node-path endpoint carries the same metadata as its root catalog entry.
- Detections use the existing catalog access rules and cache. Refreshing the
  catalog re-evaluates them; they are not saved into connector configuration.
- The UI merges detections from selected schemas by id. Clicking a label sets
  the existing catalog filter; clicking the active label clears it. Typing
  edits the same filter. The labels remain visible while filtering, so the
  active filter can always be toggled off. No framework names or table-name
  inference belong in the client.

## Limits

These are name-based hints, not proof that a framework is currently installed.
Custom marker names and WordPress prefixes are not detected. Filtering narrows
the currently selected schemas by table name; it does not identify all of a
framework's application tables or read their contents.

## Validation

Write coverage for signatures and near misses, empty inputs, multiple matches,
schema isolation, views, root/path parity, API serialization, selected-schema
aggregation, filter toggling and the visible browser workflow. Tests and checks
are deferred at the user's request.

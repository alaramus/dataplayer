# PostgreSQL schema actions

Date: 2026-08-31. Settles roadmap item 1.5's schema-command round and D56.

Sources read: the schema and relation-move methods in
`dbwebtool/webdb/data_adapter/postgre/postgres_extended_adaptor.py`, their SQL
templates, the old catalog menu, DataPlayer's D9/D21/D32/D45/D46 action
contracts, and the current grouping-based catalog screen.

## Outcome

PostgreSQL declares four operations through the existing action registry:
create, rename and drop a schema, and move a relation to a schema. There is no
PostgreSQL route and no client branch on adapter or action name.

The old implementation is evidence only. It formatted schema and relation
names into templates, quoted some identifiers as string literals and optionally
renamed indexes after a move. The new actions accept typed names only as input,
validate their boundary, confirm existing targets through `pg_namespace`, and
compose every identifier with `psycopg.sql.Identifier`. PostgreSQL moves owned
indexes and constraints with the relation; their names are identities of their
own and are not cosmetically rewritten.

## Action subjects

The original three-subject routing is superseded by
[D118](2026-09-07-action-targets-design.md): schema rename/drop receive an
independent `group` subject, so checked relations cannot replace their target.
CSV import and table creation use `destination` and open a form for one chosen
schema even when multiple schemas are displayed. `level`, `children` and `node`
keep their original roles for other actions. Standing inside a file directory
still does not select it for rename or removal.

The client asks the action-applicability route per subject. The source decides
which target or destination is eligible; the client never infers eligibility
from action names. Labels and current-name defaults follow that same subject.

## More than one changed branch

Moving `sales.orders` to `archive` removes one child from `sales` and adds one
to `archive`. A singular reload id can name only half of that fact. Reloading
the root does not fix it: a previously cached destination branch remains a
separate query.

`ActionResult.reload_node_ids` is therefore an ordered list of exact opaque
ids. The action names every branch, the query cache invalidates each one, and
the visible catalog redraws once. Existing one-branch actions return a
one-element list. Schema create/drop additionally name the schema id so a
later schema reusing that exact name cannot inherit cached children from its
predecessor.

Identity-changing operations also return D32's exact `NodeReplacement`.
Moving one relation is bounded and its open panels follow. Renaming a schema
returns the schema's replacement so the selected grouping follows, but not a
replacement per descendant: that would make one response unbounded by schema
size. The client is not allowed to synthesize descendant ids, so open relation
tabs below a renamed schema are a documented deviation.

## Operation rules

- Create is offered only at the root. It refuses `pg_`/system names and an
  existing exact name, then executes `CREATE SCHEMA`.
- Rename and drop are offered only for non-system `SchemaNode`s issued by the
  source. Rename refuses the same or a taken target and returns the grouping's
  replacement.
- Drop uses the exact `DROP SCHEMA` statement as its preview, rolled back. A
  plain drop of a non-empty schema is blocked; cascade lists PostgreSQL's own
  notices before it can be confirmed.
- Move is offered for non-system tables, partitioned tables, views and
  materialized views. The target must be an existing non-system schema and
  must not already contain a relation of that name. The source chooses the
  correct `ALTER ... SET SCHEMA` command from its own catalog node.

Every operation requires structure access. Expected privilege, dependency and
lock refusals are reduced to safe application wording; driver text never
crosses the boundary.

## Tests

Backend tests cover applicability, names over the PostgreSQL limit, conflicts,
create, rename identity, both reload branches on move, system-schema refusal,
and a rolled-back schema-drop preview. Frontend unit tests cover the third
action subject, selected-group replacement and multi-branch invalidation. The
browser scenario creates and renames a schema, moves a fixture relation into
it and back, previews the empty drop, and removes it.

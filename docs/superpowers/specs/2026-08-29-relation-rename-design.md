# Renaming a table and a view

## Goal

Rename a PostgreSQL relation without exposing raw DDL, teaching the client what
a PostgreSQL node id contains, or leaving an open rows/structure tab attached
to an identity that no longer exists.

## Action boundary

Rename is a catalog action because it is performed on a selected catalog node
and the existing action registry already carries applicability, parameter
schema, execution and the catalog branch to reload. PostgreSQL declares one
`rename_relation` action. It applies to table and view node kinds but is offered
only when the fresh node is not in a system schema.

The parameter is one `new_name`. Validation preserves the exact text, rejects
empty or surrounding whitespace and enforces PostgreSQL's 63-byte identifier
limit. The adapter reads the source node again, refuses an unchanged or occupied
name, selects the DDL form from the adapter-produced node kind and quotes both
identifiers. The client supplies neither a relation kind nor SQL.

## Identity replacement

PostgreSQL node ids include the relation name. A successful rename therefore
returns a typed `NodeReplacement` in `ActionResult`: old opaque id, new opaque
id and display title. `reload_node_id` still names the schema whose children
changed.

The workspace engine gains a general panel replacement operation. It changes
the panel object and replaces its id in the pure layout tree, including the
active tab, without changing the leaf, order or split geometry. The DataPlayer
workspace applies a node replacement to every open rows and structure panel for
that connector and old node. This is application policy above the engine; the
engine never learns what a node or relation is.

## Rejected alternatives

- Add/drop is not rename: it loses identity, data and dependencies.
- A dedicated PostgreSQL endpoint would duplicate the action registry and put
  source knowledge in the catalog UI.
- Reloading old tabs until they return 404 reports the rename as data loss.
- Mutating only `nodeId` while keeping the old panel id permits a second tab for
  the same new relation and corrupts the identity invariant.
- Closing and reopening the tab loses its placement and transient work.

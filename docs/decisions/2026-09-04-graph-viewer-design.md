# A graph viewer with 2D and 3D presentations

The first use is exploring relationships between existing tables. The user
explicitly chose a visualizer, with room for authored connections later. Moving
a node changes its layout only. No gesture creates or changes a database object.

## Boundaries

`shared/graph` accepts a typed graph: stable node and edge identities, labels,
groups, rows with optional attachment ports, and directed or undirected edges.
It imports neither the generated API client nor a feature. A node can represent
a table, service, file or task. Its rows and badges are presentation data, not
SQL types or primary/foreign-key flags. Edges may join whole nodes or ports.
Compound foreign keys remain one edge with all column pairs in its details.

The graph document and its view state are separate. Selection and filters are
shared between 2D and 3D; positions and cameras belong to each presentation.
Controlled position/selection events are the extension boundary for a future
editor. The viewer does not mutate source data or implement a persistence API.

`features/relationships` is the first producer. It reads existing relation
models, maps their fields and declared foreign keys into this vocabulary and
handles actions such as opening a table. It never parses an opaque node id or
infers a foreign key from column names. No new backend capability is needed.

## Opening and loading

The catalog offers Relationships for describable nodes. It uses the checked
selection when present, otherwise the current filtered catalog list. The panel
descriptor retains that explicit set, so a reload never silently changes the
scope. Different sets may be compared in separate workspace tabs; the existing
detach/minimize/maximize behavior applies to the panel.

At most 100 relation models are requested, with four reads in flight. Requests
use TanStack Query and abort when abandoned. Partial failures remain visible;
an unavailable table is a placeholder, never silently omitted. Foreign-key
targets outside the requested set also appear as placeholders. The UI names
the scope and distinguishes outside-selection nodes from failed reads.

The assembled graph is bounded to 300 nodes, 5,000 rows/ports and 1,000 edges.
Exceeding a bound asks for a smaller selection rather than silently dropping
relationships. Refresh reads the same set again and preserves surviving view
positions. The diagram describes declared outgoing foreign keys of the loaded
tables, not every incoming reference in the entire database.

## Interactions

2D uses draggable HTML cards and SVG edges attached to rows, with pan, pointer-
anchored zoom, fit, search, group filtering and selection. Parallel edges and
self references have distinct paths. Selection emphasizes adjacent nodes and
edges. Collapsing details retains the same edges, attached to the node header.
Dagre supplies an initial automatic layout; explicit Arrange recomputes it.

3D uses Three.js with orbit, pan, zoom, fit, labels, picking and a shared details
panel. Volumetric nodes and spatial separation follow the useful legacy
DataDiagram3D interactions. The layout starts from the 2D sketch, then uses
weak sketch forces alongside link, collision and charge forces to arrange nodes
in all three dimensions. Shift-drag moves a node on a camera-facing plane.
The viewer renders on demand, observes its actual panel size, and releases
controls, WebGL resources, observers and handlers on disposal. Hidden workspace
panels do not animate. If WebGL is unavailable, 2D remains usable.

Labels are rendered as text, never HTML supplied by a source. Colors come from
shared theme tokens in both modes. Keyboard selection and the details panel
offer an alternative to picking a small line with the pointer.

View state is versioned and validated before restoration. The relationship
feature stores only UI state in localStorage, scoped to the signed-in user,
connection and explicit node set. Relation metadata and rows are not persisted.
Storage failure is reported while
leaving the current view usable.

## Evidence and deferred validation

Legacy references: `myquasar/src/myapp/views/xdbview/components/DataDiagram.vue`,
`DataDiagram2D.vue`, `DataDiagram3D.vue` and `graphset/`. The old shared source,
mode switch and spatial navigation are useful; viewer branches on graph kind,
connector creation, duplicated database types, mutable layout data and literal
theme/layer decisions are not carried across.

dbdiagram's field attachment and readable table cards guide the first producer.
This slice does not implement DBML, schema authoring, graph sharing or a graph
document library. These require their own contracts rather than dormant UI.

Tests cover generic non-table graphs, mapping of real/composite/self references,
scope boundaries and read failures, bounded loading, deterministic geometry,
view restoration and workspace registration. Browser scenarios cover the
catalog-to-diagram workflow, 2D interactions, 3D selection, themes and detached
panels. Tests, type checks, linters and builds remain deferred by the user.

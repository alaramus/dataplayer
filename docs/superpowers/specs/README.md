# Specifications, in order

The full argument behind each decision. The decision's line is in the table in
[AGENTS.md](../../../AGENTS.md), its statement is in `docs/architecture/`, and
the argument is here.

Language: this index, and every spec from 2026-08-28 onwards, is in English.
The specs dated up to 2026-08-27 and the plans beside them are working notes
written in Russian, and are kept that way as legacy. The titles below are
translations; those files are not.

| Date | Spec | What it settled |
| --- | --- | --- |
| 2026-08-15 | [The connector registry and the adapter contract](2026-08-15-connector-registry-design.md) | D1, D2, D2b: a source type is a class in code, the contract is a Protocol. D3, D4, D6, D7: async throughout, secrets split by schema, Vue with Quasar, server state in vue-query |
| 2026-08-15 | [Breaking the flat layer up into a users module](2026-08-15-users-module-design.md) | D5: modules by area, dependencies pointing one way |
| 2026-08-15 | [The catalog of a data source](2026-08-15-catalog-design.md) | D2a: nodes differ by kind, not by source family |
| 2026-08-15 | [Reading data](2026-08-15-fetch-design.md) | D2c: a query is not assembled from client strings |
| 2026-08-21 | [The file source](2026-08-21-file-explorer-design.md) | D8, D2d: a personal directory, and an honest answer about what the source cannot do |
| 2026-08-21 | [The action registry](2026-08-21-action-registry-design.md) | D9: an action is an object, and the declaration is the callable |
| 2026-08-21 | [The connection pool](2026-08-21-connection-pool-design.md) | D10: what outlives a request belongs to the application |
| 2026-08-22 | [The workspace and the panel engine](2026-08-22-workspace-design.md) | D12: a tree of sections, and the engine knows nothing of panels |
| 2026-08-22 | [Three columns: sources, navigation, work](2026-08-22-three-column-workspace-design.md) | A column is a role, not a place |
| 2026-08-22 | [The catalog as a list, connections without a menu](2026-08-22-catalog-list-design.md) | One level instead of a tree, ticks instead of selection |
| 2026-08-22 | [The shared UI kit](2026-08-22-shared-ui-kit-design.md) | D11: a screen asks for meaning, not for a look |
| 2026-08-23 | [The explorer, the tab strip and the bottom line](2026-08-23-explorer-and-strip-design.md) | The path up as a line, tabs that wrap, the strip of a collapsed column |
| 2026-08-23 | [A column appears together with its content](2026-08-23-progressive-workspace-design.md) | The role decides what is accepted; there are as many catalogs as were opened |
| 2026-08-23 | [A tab is seen in the hand and dropped on a strip](2026-08-23-tab-drag-design.md) | The drag gesture: the strip joins, the body divides |
| 2026-08-23 | [The catalog of source types, and creating a connection](2026-08-23-adapter-catalog-design.md) | D13: a type describes itself, and what it can do is derived |
| 2026-08-23 | [The connection window: floating windows and form layout](2026-08-23-connector-window-design.md) | D14: work opens in resizable floating windows, and there are several |
| 2026-08-23 | [Ways of connecting](2026-08-23-connection-variants-design.md) | D15, D16, D17: the connection string, variants of the options, taking a pasted string apart |
| 2026-08-23 | [The theme, the window layer and three corrections to the screen](2026-08-23-theme-and-window-layer-design.md) | Colour and layer are meaning too: `theme.css` and `layers.css` |
| 2026-08-23 | [Restructuring the project documentation](2026-08-23-docs-restructure-design.md) | A core plus files by area, instead of one AGENTS.md |
| 2026-08-24 | [The socket, health and a switched-off connector](2026-08-24-realtime-and-connector-health-design.md) | D18, D19, D20: the transport knows no topic, a monitor lives while somebody watches, a switched-off connection is not a source |
| 2026-08-24 | [The reload button on a tab](2026-08-24-tab-reload-design.md) | A third handle of the same kind as T5: a panel says how to re-read it |
| 2026-08-24 | [From a table's tab to its catalog](2026-08-24-reveal-in-catalog-design.md) | The table tab's icon leads to the catalog, and the connection name moves into the tooltip |
| 2026-08-24 | [A source says for itself where a node lives](2026-08-24-node-path-design.md) | D21: the path to a node is an adapter capability, and the client does not take an id apart |
| 2026-08-24 | [The relation model](2026-08-24-relation-model-design.md) | D22: a source describes a relation in full, and a column type is an object |
| 2026-08-27 | [The data exploration grid](2026-08-27-data-grid-design.md) | D23, D24: a cell crosses as lossless text; the grid is controlled state around a headless engine |
| 2026-08-27 | [Editing data](2026-08-27-data-editing-design.md) | D25: a versioned row handle and an optimistic update of one cell |
| 2026-08-27 | [Inserting and deleting rows](2026-08-27-row-insert-delete-design.md) | D26: omitted/default/NULL, and an atomic bulk delete |
| 2026-08-27 | [Adding and dropping columns](2026-08-27-column-add-drop-design.md) | D27: source-owned types, and DDL without client SQL |
| 2026-08-28 | [Downloading the visible page, and the commands of an open table](2026-08-28-page-download-design.md) | D28: a bounded CSV page is kept in the personal folder |
| 2026-08-28 | [Column rename](2026-08-28-column-rename-design.md) | D29: rename keeps identity and source-owned dependencies |
| 2026-08-28 | [Column default](2026-08-28-column-default-design.md) | D30: an entered default is always a literal, never an SQL expression |
| 2026-08-29 | [The catalog and fetch read cache](2026-08-29-read-cache-design.md) | D31: source-owned TTL, bounded cache, coalescing and connector invalidation |
| 2026-08-29 | [Renaming a table and a view](2026-08-29-relation-rename-design.md) | D32: source-issued replacement identity, open tabs follow the rename |
| 2026-08-29 | [Sharing a connection](2026-08-29-connector-sharing-design.md) | D33, D34: an ordered grant level a route asks for, and an administrator with rights over accounts only |
| 2026-08-30 | [Charts over a bounded page](2026-08-30-bounded-page-charts-design.md) | D35: a chart is a closed view over one bounded fetch |
| 2026-08-30 | [Navigating by a foreign key](2026-08-30-reference-navigation-design.md) | D36: the source issues the target of a reference, and the predicate with it |
| 2026-08-30 | [Changing whether a column may be empty](2026-08-30-column-nullability-design.md) | D37: the rows in the way are counted, and the count is the answer |
| 2026-08-30 | [Changing a column's type](2026-08-30-column-type-change-design.md) | D38: the target is a published code, the cast is the source's, the way is checked first |
| 2026-08-30 | [Creating and dropping an index](2026-08-30-index-create-drop-design.md) | D39: no name from a client, and the method's limits come from the server |
| 2026-08-30 | [Promising uniqueness, and pointing at another relation](2026-08-30-constraint-create-drop-design.md) | D40: the target publishes what may point at it, and the data can refuse a promise |
| 2026-08-30 | [Pasting a block of cells](2026-08-30-cell-paste-design.md) | D41: rows carry the version, and unreadable values are named before anything is written |
| 2026-08-30 | [What identifies a row, and what order rows arrive in](2026-08-30-row-identity-and-order-design.md) | D42: a keyless row is versioned by its place, and every page is ordered |
| 2026-08-30 | [Bringing rows from one source into another](2026-08-30-row-import-design.md) | D43: two connectors, two permissions, one bounded all-or-nothing move |
| 2026-08-30 | [Exporting every matching row](2026-08-30-streaming-export-design.md) | D44: a source-owned row stream staged as an atomic personal download |
| 2026-08-30 | [Loading a CSV as a new table](2026-08-30-relation-create-design.md) | D45: a catalog action, and the table and its rows in one transaction |
| 2026-08-30 | [Dropping a relation, and seeing what goes with it](2026-08-30-relation-drop-design.md) | D46: an action can be asked what it would do, and the answer is the drop rolled back |
| 2026-08-30 | [Native file representations](2026-08-30-file-representations-design.md) | D47: a node declares ordered views; native content and table fetch stay separate |
| 2026-08-30 | [Editing a file in place](2026-08-30-content-editing-design.md) | D48: the source issues an opaque version, and a save must still match it |
| 2026-08-31 | [Download actions and bounded image content](2026-08-31-original-file-and-image-content-design.md) | D49: download is a source-declared action over selected nodes; image preview is bounded and verified |
| 2026-08-31 | [Markdown as a rendered document representation](2026-08-31-markdown-document-representation-design.md) | D50: rendered first and source second, with everything that becomes DOM sanitised twice |
| 2026-08-31 | [Parquet files and workbook sheets as declared datasets](2026-08-31-parquet-and-workbook-datasets-design.md) | D51: a file that states its own schema is a dataset, and a workbook is a container of them |
| 2026-08-31 | [Playing media, and reading a PDF](2026-08-31-media-and-pdf-viewers-design.md) | D52: bytes a player seeks in are a ranged stream, and a PDF is drawn by the application |
| 2026-08-31 | [Walking into an archive](2026-08-31-archive-browsing-design.md) | D53: an archive is a container of entries, and an entry name goes through the one containment rule |
| 2026-08-31 | [What the old PostgreSQL adapter does beyond the table rounds](2026-08-31-postgres-system-operations-design.md) | D54: a relation the server owns is described but never changed. D55: a source publishes reports of its own, and a report is a statement it holds |
| 2026-08-31 | [PostgreSQL schema actions](2026-08-31-postgres-schema-actions-design.md) | D56: level, shown places and selected nodes are distinct action targets; a result names every changed branch |
| 2026-08-31 | [PostgreSQL relation DDL](2026-08-31-postgres-relation-ddl-design.md) | D57: source-issued SQL is bounded read-only content, not an editable text file |
| 2026-09-01 | [Sharing a view](2026-09-01-shared-view-links-design.md) | D58, D59, D60, D61: a link is an address and not a permission, a stored record with a typed body, resolution answers a state rather than a status, and access is asked for as a durable request |
| 2026-09-01 | [The query editor](2026-09-01-query-editor-design.md) | D62, D63, D64, D65, D66: intentional source queries, encrypted documents and immutable runs, bounded asynchronous results, an editor integrated with the workspace, and explicit write transactions |
| 2026-09-02 | [A grid that re-reads itself](2026-09-02-auto-refresh-design.md) | D67: an interval the grid wears, and a pause rule both the timer and the tooltip read |
| 2026-09-02 | [Dropping several relations at once](2026-09-02-action-node-set-design.md) | D68: a set is a subject an action may have, carried in one request and one transaction |
| 2026-09-02 | [The bar at the foot of the screen](2026-09-02-connection-command-bar-design.md) | D69: the commands of a connection, offered while it is read and while it can do the thing |
| 2026-09-02 | [Commands over the rows of a relation](2026-09-02-row-commands-design.md) | D70: a relation declares what can be done to selected rows, and may ask to be re-read |
| 2026-09-02 | [Making an archive, and taking one apart](2026-09-02-archive-packing-design.md) | D71: the tar family joins ZIP for packing, and a name inside an archive goes through the one containment rule |
| 2026-09-02 | [What a page is for, said by the source](2026-09-02-page-commands-design.md) | D72: the grid's own commands are a vocabulary the source may withdraw from |
| 2026-09-02 | [The model a source published, written as code](2026-09-02-model-as-code-design.md) | D73: a download may carry a form, and the published model is written as SQLAlchemy, Django or DBML |
| 2026-09-02 | [Copying and moving files](2026-09-02-file-clipboard-design.md) | D74: Copy and Cut are the client's and change nothing; Paste is the source's, and the form fills itself by purpose |
| 2026-09-02 | [A node describes itself](2026-09-02-node-summary-design.md) | D75: what a node is, is a fourth question with a capability of its own — neither a viewer nor an action |
| 2026-09-02 | [Searching the catalog by name](2026-09-02-catalog-search-design.md) | D76: a search answers with catalog nodes, and the filter's own words are what it looks for |
| 2026-09-02 | [SQL over tabular files](2026-09-02-file-sql-design.md) | D77, D78: a file source's SQL names its own nodes, and its engine is a disposable sandbox |
| 2026-09-02 | [A database user](2026-09-02-database-user-design.md) | D79: making a role is the owner's alone, and a password DDL cannot bind travels as the driver's own literal |

Implementation plans are in [../plans/](../plans/). There are five: two for the
connector registry, and one each for the workspace, the relation model and the
grid; the other sub-projects followed their spec without a separate plan.

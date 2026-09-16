# Decision history, in order

The full argument behind each decision. The decision's line is in the table in
[AGENTS.md](../../AGENTS.md), its statement is in `docs/architecture/`, and
the argument is here.

These files are frozen history, not live documentation. `docs/architecture/` is
what the project does today; a spec below is why it was decided that way. Do
not update a spec to match later code — record the new reasoning in the
architecture file, and add a new dated entry here only when the decision
itself is revisited.

Language: this index, and every spec from 2026-08-28 onwards, is in English.
The specs dated up to 2026-08-27 and the plans beside them are working notes
written in Russian, and are kept that way as legacy. The titles below are
translations; those files are not.

| Date | Spec | What it settled |
| --- | --- | --- |
| 2026-09-14 | [The application agent](2026-09-14-application-agent-design.md) | D133–D141: agreed; AI1, AI2, AI3 and AI4 implemented, AI3b validation and AI5–AI6 pending. An agent that acts as the person through the connections they added, general tools over what sources describe, an owner's third-party transfer policy, confirmations that can last, an answer as a run with visible steps, streamed Markdown, LangChain v1 in one package, curated models and personal keys, one chat window |
| 2026-09-14 | [Monitor agent protocol: receiving what dataplayer-monitor-agent sends](2026-09-14-monitor-agent-protocol-design.md) | MA1 implemented. D127, D128, D130 restated: DPMA/1 datagrams checked by key id, HMAC, body and freshness before they are written as sent; a restart is a new agent process; hosts described; the old agent's format and data gone |
| 2026-09-13 | [Neutral window design and stable sizing](2026-09-13-window-design-and-sizing.md) | D131–D132: agreed, implementation pending; neutral compact forms with minimal borders, a saved visual example, and stable geometry for tabbed or changing content |
| 2026-09-13 | [Dashboards: metric collection, storage and display](2026-09-13-dashboards-design.md) | DB1–DB6 implemented. D125–D130: a space of its own, an installation-owned TimescaleDB store set up on first entry, one collecting process, typed sources, dashboards read through one access check, agent packets interpreted in one place (D130 replaced by the monitor agent protocol) |
| 2026-09-13 | [The backend runs as one process](2026-09-13-one-backend-process-design.md) | D124: the image names one worker, because everything the lifespan builds is correct in one process only |
| 2026-09-07 | [TimescaleDB through a PostgreSQL connection](2026-09-07-timescale-capabilities-design.md) | T1 completed on 2026-09-08, as confirmed by the user, T2 on 2026-09-11 and T3 on 2026-09-12, each with all checks green. D119–D123: composed extension support, runtime discovery, typed relational specialisation, paged reports and guarded source operations |
| 2026-09-07 | [Action targets and availability](2026-09-07-action-targets-design.md) | D118: independent grouping actions, destination workflows and explicit availability reasons |
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
| 2026-08-30 | [Loading a CSV as a new table](2026-08-30-relation-create-design.md) | D45: a catalog action, and the table and its rows in one transaction; a source that keeps files takes one as a delimited file |
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
| 2026-09-02 | [Searching the catalog by name](2026-09-02-catalog-search-design.md) | D76: a search answers with catalog nodes, and the filter's own words are what it looks for; held down, it reads the files themselves |
| 2026-09-02 | [SQL over tabular files](2026-09-02-file-sql-design.md) | D77, D78: a file source's SQL names its own nodes, and its engine is a disposable sandbox |
| 2026-09-02 | [A database user](2026-09-02-database-user-design.md) | D79: making a role is the owner's alone, and a password DDL cannot bind travels as the driver's own literal |
| 2026-09-02 | [Approved service templates](2026-09-02-service-templates-design.md) | D80: what may be started is written in code, and a client names one of them |
| 2026-09-02 | [Owned asynchronous jobs](2026-09-02-owned-jobs-design.md) | D81: long work is a row with named steps, not a request that waits or a boolean in a process |
| 2026-09-02 | [Detecting a container runtime](2026-09-02-runtime-detection-design.md) | D82: whether a server may and can start containers is asked, and the offer states the refusal |
| 2026-09-03 | [Starting a PostgreSQL and receiving a connection](2026-09-03-service-pilot-design.md) | D83: a ready service is an ordinary connector, filled from the plan its container was started with |
| 2026-09-03 | [When starting one goes wrong](2026-09-03-service-recovery-design.md) | D84: retry starts over because the password is gone, and neither deletion reaches into the other |
| 2026-09-03 | [A second service, and the first source that only connects](2026-09-03-redis-pilot-design.md) | D85: a command may carry a credential, and a type that only connects says so |
| 2026-09-03 | [What running services on the machine costs](2026-09-03-service-threat-model-design.md) | D86: the socket is the machine's power, so the call list is fixed, the limits are set and it stays off by default |
| 2026-09-03 | [Copying a database out, and putting it back](2026-09-03-backup-and-restore-design.md) | D87: pg_dump runs in the image of the server's own version, and a backup is a file in personal storage |
| 2026-09-03 | [Two ways to start a service, and what comes back](2026-09-03-service-start-modes-design.md) | D88, D89, D90: automatic or chosen, the password shown once, and an empty database filled |
| 2026-09-03 | [A key space, walked and written](2026-09-03-redis-keyspace-design.md) | D91: the tree is the colons in the names, and four actions are what people do to a key by hand |
| 2026-09-03 | [Choosing what a started service is made with](2026-09-03-service-start-choices-design.md) | D88, D89: a chosen start names the port and the password, and the password is handed over once while the address is told always |
| 2026-09-04 | [Minimizing and maximizing floating windows](2026-09-04-window-states-design.md) | D92: preserve live window contents when minimized, restore through the footer, and maximize above it |
| 2026-09-04 | [Detaching a tab into a floating window](2026-09-04-detached-tabs-design.md) | D93: move a live panel through the header, return it to a section and retain open tabs on reload |
| 2026-09-04 | [Saved tab groups](2026-09-04-tab-groups-design.md) | D94: explicit layout snapshots, header buttons, guarded replacement and a remembered warning preference |
| 2026-09-04 | [Operation progress in the footer](2026-09-04-operation-progress-design.md) | D95: measured progress, owned jobs and controls at real execution boundaries |
| 2026-09-04 | [SQL over log files](2026-09-04-log-sql-design.md) | D96: the same log projection in the grid and SQL, with bounded whole-file snapshots |
| 2026-09-04 | [A graph viewer with 2D and 3D presentations](2026-09-04-graph-viewer-design.md) | D97: a generic graph document, independent renderers and relation metadata as the first producer |
| 2026-09-04 | [Framework detection in the catalog](2026-09-04-framework-detection-design.md) | D98: schema-owned table signatures and clickable filters for every detected framework |
| 2026-09-04 | [Choosing a DataPlayer server](2026-09-04-server-profiles-design.md) | D99: per-tab server selection, independent sessions and source state, and anonymous compatibility checks |
| 2026-09-04 | [A replaceable read-cache backend](2026-09-04-cache-backend-contract-design.md) | D100: D31's cache semantics sit behind one application protocol, with memory as the default backend |
| 2026-09-04 | [The shared-cache wire format](2026-09-04-shared-cache-wire-design.md) | D101: deployment/user namespaces, typed versioned JSON and encryption of every remote cache value |
| 2026-09-04 | [An optional shared Redis cache](2026-09-04-redis-cache-design.md) | D102: shared encrypted entries, connector generations, Pub/Sub invalidation and direct-read degradation |
| 2026-09-04 | [Selecting and observing the cache backend](2026-09-04-cache-configuration-design.md) | D103: memory by default, explicit Redis settings, non-fatal health and an optional Compose profile |
| 2026-09-04 | [Redis stops at measured read caching](2026-09-04-cache-scope-design.md) | D104: observable cache outcomes and no locks, job fan-out, share acceleration or durable truth without evidence |
| 2026-09-05 | [The freshness window a connection chooses](2026-09-05-connector-cache-window-design.md) | D105: the owner of a connection sets how long its reads are kept, and every reply says how old it is |
| 2026-09-05 | [A reference the person draws](2026-09-05-declared-references-design.md) | D106, D107, D108, D109: the application keeps references no source has, checked against both ends and followed into another connection |
| 2026-09-05 | [The way back along a key](2026-09-05-arriving-references-design.md) | D110: a source says what points at a relation, asked on demand and followed by the same call |
| 2026-09-05 | [One row, read downwards](2026-09-05-row-view-design.md) | D111: the row view reads the page the grid is on, and a row is a position in it |
| 2026-09-05 | [The commands of a panel belong to the panel](2026-09-05-panel-commands-design.md) | D112: showing the node, re-reading and returning from a window stand in the panel's own row, and a tab acts on nothing |
| 2026-09-06 | [Everything that needs a person](2026-09-06-activity-centre-design.md) | D113, D114, D115: one sheet for waiting, working and recent; a message is recorded before it is shown; attention comes from sources |
| 2026-09-06 | [The row of commands above a table](2026-09-06-grid-toolbar-design.md) | D116: five named groups in the order of a working session, and a command greyed with its reason rather than hidden |
| 2026-09-06 | [Designing a table](2026-09-06-table-designer-design.md) | D117: a whole table is a typed definition the source plans, reviewed as a step of its own before anything is created |

Implementation plans are in [plans/](plans/). There are five: two for the
connector registry, and one each for the workspace, the relation model and the
grid; the other sub-projects followed their spec without a separate plan.
The plans are frozen legacy notes and stay unchanged.

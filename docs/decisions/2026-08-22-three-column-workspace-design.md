# Three columns: sources, navigation, work

Date: 2026-08-22
Status: agreed
Subproject: 7b (continuation of 7a)

## Goal

The workspace from 7a opens with a single section: the list of connections,
while the catalog and the table arrive as tabs next to it and are separated by
dragging. In practice this means the user assembles the screen by hand every
time, and until the first drag an opened table covers the tree it was opened
from.

The old application solved this with a three-column layout that always
exists: connections on the left, the catalog of one of them in the centre,
data in tabs on the right. It works because a column is not a place something
was once dragged to, but a role, and a panel itself knows which role it lands
in.

The task is to build such a layout without starting a second mechanism next to
the engine from 7a and without closing the road for sources that have no
catalog or no fetch at all.

## What changes in the decisions of 7a

Two decisions of the previous spec are refined; neither is cancelled.

**W8 stays.** "Tabs only in the fetch column" is not a second model of tabs.
The catalog section is built exactly like the data section: a tab strip with
one active tab. There is always one tab there because opening a catalog
closes the previous one, not because this section has different code. No
separate entity "a panel without tabs" appears.

**W11 is extended.** The rule "a new panel goes into the leaf that holds a
panel of the same kind" does not work while the leaf is empty: it has nothing
to hold. So a leaf gets its own role label — see T1.

## Decisions

### T1. A section carries a role, and the role is a string opaque to the engine

`LeafNode` gets a field `accepts?: string`. Placing a new panel first looks for
a leaf whose `accepts` matches the panel's role, and only then applies the W11
rules (a leaf with a panel of the same kind → the leaf with focus → the
largest).

The role is the same opaque string the engine already uses in `leafForKind`:
it compares it and never parses it. The words `sources`, `navigate`, `work`
live in `features/workspace/panels.ts`; they are not in `shared/workspace`.

The role is introduced instead of the former `kindOf === panel.kind` precisely
because adapters will diverge from here on. A Kafka table of its own, a
replication monitor, an SQL editor — these are new panel kinds with the role
`work`, and they do not touch the layout: they land as a tab in the right
column because they declared a role, not because somebody added a rule.

`accepts` is a placement rule, not a prohibition. Dragging tabs does not read
it: a tab goes where it was dropped.

### T2. A pinned section survives being emptied

`LeafNode` gets `pinned?: boolean`, and `activePanel` becomes
`PanelId | null`. `normalize` no longer throws away an empty leaf if it is
pinned; `removePanel` leaves a pinned leaf in place with `activePanel: null`.

This is the only place where the promise "three columns are always visible" is
kept. A variant with a placeholder panel in each column was considered and
rejected: a placeholder can be closed, so a "cannot be closed" flag would be
needed anyway — the same engine change, but on top of an invented panel kind,
and the state "no source selected" would move from the section into a panel,
where it does not belong.

An empty pinned section is drawn by a component the feature provides:
`WorkspaceContext.emptyOf(accepts)`. The engine knows the section is empty and
does not know what to write there.

### T3. Whether a tab closes is for the feature to say

`PanelLook` gets `closable?: boolean`. The connections panel does not set it:
it has no parameters, there is nothing to close, and an empty left column
would tell nothing. The catalog and the table close: a closed catalog leaves
the middle column with the hint "select a connection".

The flag belongs to the panel, not the section: in the data section tabs
close, and it is pinned exactly like the left one.

### T4. Opening a catalog closes the previous one, but the panel is still per connection

`open(panel, { replace: true })` closes all panels of the same role before
adding. The catalog opens this way, the table does not.

The catalog panel identifier stays `catalog:{connectorId}`. The temptation to
collapse the catalog into one panel with a constant id and a changing prop
`connectorId` is deliberately rejected: it would close the road to two
catalogs side by side for good — the panel identity would have to be reworked,
and with it the format of the saved layout. In the current form "two catalogs"
means removing the `replace` flag: `<KeepAlive>` keeps both, each has its own
expanded tree, placement by T1 finds both sections. Dragging a node from one
catalog to another is a separate task and a different layer (the server today
can do neither move nor copy), but the layout does not get in its way.

The cost of today's `replace`: the expanded tree of the previous connection is
lost on returning to it. This is accepted.

### T5. The default layout is three pinned sections

`sources` 20% / `navigate` 28% / `work` 52%, one row. `sources` holds the
connections panel; the other two are empty and show a hint.

The former default — one section — is recorded in AGENTS.md as a deliberate
decision with the reasoning "the catalog names a connection the user has not
yet selected". T2 removes that reasoning: an empty column is now possible, and
a hint in it is more useful than its absence. The entry is removed from "Known
deviations".

Dragging a data tab to the edge of its column still splits it in two — this
works by itself: `splitLeaf` leaves the original leaf its id and flags, and
gives the new neighbour neither `accepts` nor `pinned`.

### T6. A saved layout of version 1 is not migrated

`WORKSPACE_VERSION` → 2. Parsing an old layout already rejects a foreign
version entirely and falls back to the default (W9). Writing a migration for a
layout that lives in one browser's localStorage costs more than assembling the
screen once again.

### T7. The left column is a list, not a table

`ConnectorTable` is designed for the width of a page: four columns and four
buttons per row. That does not fit into a 20% column. In its place
`features/connectors/ConnectorList.vue`: a row is a type icon, a name, a status
dot; a click on the row loads the catalog; edit, check and delete are in the
row's menu.

The menu requires `q-menu`, so `AppMenu` is added to the kit — one component
that takes a list of items and keeps `q-list`/`q-item` inside itself. Three
elements are added to the forbidding ESLint rule and to the `/ui-kit` showcase.
No separate `AppList` is introduced: list rows are ordinary markup, as the
engine's tab strip already is.

**The status dot shows only this session's checks.** Checking all connections
automatically when the screen loads is not allowed: that is N connections to
other people's servers for the sake of decoration. A grey dot means not
checked, green and red are the result of the last check the user made. The
result lives in Pinia: it is something the server does not own (D6).

## Contents

### Engine, `shared/workspace/`

| File | What changes |
| --- | --- |
| `model.ts` | `accepts`, `pinned`, `activePanel: PanelId \| null`, `makeLeaf` with options |
| `tree.ts` | `normalize` and `removePanel` spare a pinned leaf |
| `placement.ts` | `accepts` is checked first |
| `persist.ts` | version 2, leaf schema, cross-check of the active panel |
| `context.ts` | `emptyOf(accepts)`, `PanelLook.closable` |
| `useWorkspace.ts` | `open(panel, { replace })`, option `empty` |
| `WorkspaceLeaf.vue` | empty section, close cross by `closable` |

### Workspace, `features/workspace/`

| File | What changes |
| --- | --- |
| `panels.ts` | `roleOf(panel)`, `closable` in `lookOf`, empty section components |
| `panels/EmptyNavigate.vue`, `panels/EmptyWork.vue` | hints |
| `WorkspacePage.vue` | layout of three pinned sections, `replace` for the catalog |
| `panels/ConnectorsPanel.vue` | a list instead of a table |

### Kit and connections

| File | What changes |
| --- | --- |
| `shared/ui/AppMenu.vue` | new |
| `features/connectors/ConnectorList.vue` | new, `ConnectorTable.vue` is deleted |
| `stores/connectorChecks.ts` | check result for the session |

## Verification

| What | By what |
| --- | --- |
| a pinned leaf survives removal of its last panel | `tree.spec.ts` |
| `accepts` outweighs the W11 rules, including for an empty leaf | `placement.spec.ts` |
| round trip of version 2; a version 1 layout → default | `persist.spec.ts` |
| every panel kind has a role and a component | `panels.spec.ts` |
| an empty pinned section draws a hint and draws no tabs | `WorkspaceLeaf.spec.ts` |
| connections tab without a cross, table tab with a cross | `WorkspaceLeaf.spec.ts` |
| `AppMenu` is in the `/ui-kit` showcase | `kit.spec.ts` |
| three columns on first visit, two of them with hints | Playwright |
| a click on a connection loads the catalog into the centre, a second click replaces the first | Playwright |
| a click on a node opens a tab on the right, a second one stands next to it | Playwright |
| tearing off a data tab splits the right column, a reload remembers it | Playwright |

The existing scenarios (`actions`, `catalog`, `connectors`, `files`, `rows`)
refer to `connector-table` and `browse-{name}`. They are rewritten to
`connector-list` and a click on the row — a mechanical edit, but it cannot be
skipped: without it a green run means nothing.

## Scope limits

Deliberately outside this work:

- **The server does not tell about the capabilities of an adapter type.** Both
  of today's sources have both a catalog and a fetch, so the branch "the source
  has no catalog" has nothing to be tested on, and a test on an invented
  adapter would test the invention. The role mechanism does not block this
  branch: a source without a catalog is a panel of role `navigate` that simply
  does not exist, and the column stays with a hint.
- **Two catalogs side by side.** The road is open by T4; the capability itself
  is not there.
- **Moving a node between sources.** Needs move/copy on the server, which does
  not exist.
- **A permanent status dot.** Requires background checks and their schedule.
- **Reordering tabs within a strip.** As in 7a.

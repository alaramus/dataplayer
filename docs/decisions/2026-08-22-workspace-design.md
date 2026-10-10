# Workspace and panel engine

Date: 2026-08-22
Status: agreed
Subproject: 7a

## Goal

Today the catalog lives in a modal dialog: `CatalogDialog.vue` — 228 lines in
which the tree, the action bar and the row grid are squeezed on top of the
connectors table. This is scaffolding. Everything that comes next — a proper
data grid, reading a file out, an SQL editor, streaming updates, an AI panel —
needs screen space and several objects open at once. Building it in a modal and
moving it later means doing the work twice.

The task is to replace the dialog with a workspace: several panels with
resizable borders, tabs, dragging. The foundation for all following
subprojects.

## What is taken from the old application

The old `myquasar` built its main page out of `XFrame` — its own panel engine:
`src/components/XFrame/`, 2438 lines in nine files, of which `XFrame.tsx` is
759 and `xFrameMovingImplement.ts` 688. The main page layout
(`pages/app-sections-main.ts`) is a tree of sections: `Connectors` 10%,
`Catalog1` 22%, `Four` 66% with a tab strip inside, plus disabled `Catalog2`,
`Six`, `B`. Content was mounted into sections through `Teleport` by name.

The ideas from there are right and are carried over:

- a tree of sections with direction `ver`/`hor` of any depth;
- named sections, content mounted into a section by name rather than set by
  the layout;
- a separator is an element of the tree in its own right, not a neighbour's
  border;
- `minSize`;
- a collapsed section goes into a strip, but its separator stays a handle for
  expanding, and the previous size is remembered.

Not carried over:

- the command language `hide | show | restore | add | remove | insert | substitute |
  complex | test | nope` with parameters `posit`, `apply`, `reflectName`, `mark`
  and a history `XHistoryItem[]`;
- `fake` sections ("a section without its own content, only subsections, to
  support special resizes");
- back references `parent` on nodes and the service bag `_context2`;
- the direction `'*'` and `Array<any>` in `sections`.

Not a single line of code is copied. See AGENTS.md, "We port ideas, not code".

## Decisions

### W1. The engine knows nothing about the domain

```
frontend/src/shared/workspace/     section tree, sizes, tabs, dragging
frontend/src/features/workspace/   which panels exist and what they show
```

The engine operates on nodes, panels with an `id`, and geometry. The words
"connector", "catalog", "rows" do not appear in `shared/workspace`. This is the
same boundary that `shared/SchemaForm` already holds: mechanics separately,
domain separately.

The panel type is a generic parameter of the engine. The domain union lives in
the feature:

```ts
type Panel =
  | { id: string; kind: "connectors" }
  | { id: string; kind: "catalog"; connectorId: string }
  | { id: string; kind: "rows"; connectorId: string; nodeId: string; title: string }
```

Next to it is a registry `kind → { component, icon, title }`. Adding an SQL
editor later means adding a variant to the union, an entry to the registry and
a component; the engine does not change. This is D1 (a registry instead of
branching on type), applied on the frontend.

### W2. The layout is a tagged union

```ts
type LayoutNode = SplitNode | LeafNode

interface SplitNode {
  kind: "split"
  id: string
  direction: "row" | "column"
  children: LayoutNode[]   // at least two
  sizes: number[]          // percentages, sum 100, length equals children
}

interface LeafNode {
  kind: "leaf"
  id: string
  panels: PanelId[]        // at least one
  activePanel: PanelId
  collapsed: boolean
}
```

Section and separator are not mixed into one list with a `kind` field, as they
were in the old code: a separator is generated between neighbours and is not a
tree node. Storing it as a node would mean keeping it consistent on every
insertion and removal — the source of `fake` separators in the old code.

### W3. The tree is immutable, every operation is a pure function

`tree.ts`: `splitLeaf`, `movePanel`, `addPanel`, `removePanel`, `resize`,
`collapse`, `expand`, `normalize`. Each takes a tree and returns a new one; the
composable swaps the reference. A node is addressed by a path `number[]`; there
are no back references to the parent.

Reasoning: it is in-place mutation together with `parent` references that made
the old engine acquire a layout history and a command language — otherwise an
operation could be neither undone nor composed. A tree of a dozen nodes is
small enough to be recreated on every frame of a drag.

This also gives the main thing for verification: all the real logic of the
engine is pure functions, tested without mounting components. The same
technique that already works in `treeNodes.ts`, `rows.ts` and `jsonSchema.ts`.

### W4. Normalization is one function, and it runs after every operation

`normalize()` brings the tree to canonical form:

- the sum of `sizes` within a split is 100;
- a split with one child is replaced by that child;
- a leaf without panels is removed;
- a nested split of the same direction is collapsed into its parent.

Without this, `fake` sections would be needed: in the old engine they exist
precisely because the tree was not brought to canonical form and an empty node
had to be left in place.

### W5. `minSize` is in pixels and is checked at the moment of dragging

"The tab strip needs 120px" cannot be expressed in percentages, and that is
exactly the constraint required. Percentages are how sizes are stored, pixels
are how they are constrained.

### W6. Collapsed is a field of the leaf, not a size of 0

In the old code `isHidden` is `visibility === 'hidden' || size === 0 || size
=== '0%'`: three ways of saying the same thing, which can diverge. Here there
is one field, `collapsed`.

The previous size is not stored in a separate field: collapsing does not touch
the parent's `sizes`, it only changes how it is drawn — a collapsed child gets
a fixed 28px, the others share the remainder in proportion to their shares.
So the previous size already lies where it belongs and cannot diverge from the
actual one.

### W7. Dragging on pointer events

Separators use `setPointerCapture`. Dragging panels uses the same mechanism,
not HTML5 drag-and-drop: two different mechanisms for one gesture will diverge
in behaviour, and the drag image in HTML5 DnD cannot be styled.

The drop zone is computed by a pure function `dropZone(rect, point)` →
`"left" | "right" | "top" | "bottom" | "center"`: an edge of a quarter of the
width or height splits the section, the centre puts the panel in as a tab.

### W8. A section is tabs, and there is no other tab entity in the application

Any leaf is a list of panels with one active. The catalog, the data table, the
future SQL editor are panels of one sort, and any of them can end up in any
leaf. A separate model "tabs only in the data panel" is rejected: that is two
different pieces of code for one concept, and dragging would have to be
described twice.

### W9. A saved layout is untrusted input

`persist.ts` keeps the layout in `localStorage` with a version number and parses
it against a schema. On a version mismatch, a broken structure or garbage — the
default layout in full. Half a restored tree is worse than the default.

Geometry is stored once per browser, not per connector: the layout is a
property of the workplace, not of the data source.

The layout is client state, so `localStorage` and Pinia, not the server. This
is D6: the server owns data, Pinia owns what the server does not.

### W10. A panel that refers to a vanished object shows an error rather than disappearing

At restore time the list of connectors is not loaded yet, so the tabs of
deleted connectors cannot be cleaned out at this step without risking erasing
the user's tabs because of a failed request. The panel itself shows an error
through `messageOf` and a close button.

The same reasoning as in D2a: an empty result and a broken request must stay
distinguishable.

### W11. Where a new panel opens is one rule, a pure function

Into the leaf that currently holds a panel of the same kind; if there is none,
into the leaf with focus; if there is none of those either, into the largest.
The rule is read from the tree itself; no separate history of "where this panel
used to be" is kept: a history can diverge from the tree, and the tree cannot
diverge from itself.

The rule behaves correctly by itself after the user has dragged a panel
elsewhere.

## Contents

### Engine, `shared/workspace/`

| File | Responsibility |
| --- | --- |
| `model.ts` | layout types, union of nodes |
| `tree.ts` | pure operations on the tree and `normalize` |
| `dropZone.ts` | rectangle and point → drop zone |
| `persist.ts` | serialization, version, parsing with fallback to default |
| `useWorkspace.ts` | reactive tree, calls of the pure functions |
| `WorkspaceRoot.vue` | recursive rendering of a node |
| `WorkspaceSplit.vue` | a row or column of children and separators between them |
| `WorkspaceLeaf.vue` | tab strip, active panel, drop zone overlay |
| `WorkspaceSeparator.vue` | dragging a border, expanding a collapsed neighbour |

### Workspace, `features/workspace/`

| File | Responsibility |
| --- | --- |
| `panels.ts` | the `Panel` union and the panel kind registry |
| `WorkspacePage.vue` | route `/`, default layout |
| `panels/ConnectorsPanel.vue` | the existing `ConnectorTable`, the create button, dialogs |
| `panels/CatalogPanel.vue` | the catalog tree of one connector |
| `panels/RowsPanel.vue` | `RowGrid` and `ActionBar` for one node |

`CatalogDialog.vue` is deleted. Its logic — a cache of nodes by identifier,
`reload` of one branch, lazy loading — moves to
`features/catalog/useCatalogTree.ts`: it was never dialog logic.

### Kit

`q-tree` is wrapped in `AppTree`, goes into `shared/ui/index.ts`, into the
`/ui-kit` showcase and into the forbidding ESLint rule. Subproject 7 was to
decide its fate — the decision: Quasar stays inside a wrapper, screens use the
wrapper.

The tab strip is our own, made of `AppIconButton` and ordinary markup: it needs
closing, dragging and an active marker, and `q-tabs` does not give that.

## Order of work

Two stages, each with its own green run.

**Stage A — the engine.** `shared/workspace` with placeholder panels on a dev
route. Connector code is not touched.

**Stage B — the workspace.** The panel registry, three real panels, deleting
the dialog, `useCatalogTree`, route `/`.

## Verification

| What | By what |
| --- | --- |
| split, move, removal, normalization, clamping by `minSize` | `tree.spec.ts` |
| drop zone boundaries | `dropZone.spec.ts` |
| round trip, foreign version and garbage → default | `persist.spec.ts` |
| every `PanelKind` has a registry entry | `panels.spec.ts` |
| a border drags, a panel collapses, everything survives a reload | Playwright |
| a table opens from the catalog as a tab and shows rows | Playwright |

The registry test follows the one that already compares the `/ui-kit`
showcase with the kit's files: a panel kind cannot be added without adding a
component.

## Scope limits

Deliberately outside this work:

- **Reordering tabs within a strip.** A separate mechanic on top of the same
  `movePanel`; cheaper to add afterwards than together.
- **Layout on the server.** Client state per W9; a workplace that moves between
  machines is a separate task with its own API.
- **Undoing a layout action.** The tree is immutable, so a history is a list of
  references, but the user does not need it yet.

# A reload button on the tab

Date: 2026-08-24
Status: agreed
Round: 7b

## Goal

Make it possible to reread a tab's content without closing it and without
reloading the page.

There is no new decision here: this is a third handle of the same kind the tab
already has (T5 — the tab icon calls what the application provided), and it
does not move the boundary between the engine and the application (D12).

## The premise that makes this more than one line

"Just call `invalidateQueries`" does not work. The three panels are built
differently:

- **Connections** are read through vue-query, and invalidation is enough.
- **The catalog** keeps the current level in its own `ref`s
  (`useCatalogLevel.ts`): what is shown, where we are on the path, what is
  ticked. The query cache there is used as a store of what has been read, and
  the list is built in local state — invalidation will not redraw it. The level
  already has its own `reload(nodeId)`, and actions use it.
- **Rows** are not a query at all but a mutation: the page lives in `RowGrid`,
  which has `load()`.

So each panel has its own "reread" operation, and it is already written. What
is missing is a way to reach it from the tab strip.

## Decisions

### R1. The tab asks the application whether there is anything to reload

`PanelLook` gets `reloadTooltip?: string`, `WorkspaceContext` gets
`onReload?(panelId)`. The button is drawn when the feature provided a tooltip,
exactly as the action icon is drawn when `iconTooltip` is given. The engine
learns no panel kind.

The button sits in the tab next to the cross and is always visible — like the
cross. Rejected: showing it on hover: room for it would have to be kept anyway
so the title does not jump, and a touch screen has no hover.

### R2. The panel says how to reread it

`useReloadable(panelId, reload)` is a composable of the workspace feature. On
mount the panel puts its function into the registry, on unmount it removes it.
`WorkspacePage` calls whatever is in the registry.

The registry is a plain object, so it is checked without mounting:
registration, removal, a call with an unknown id breaks nothing.

**A correction that came out while writing the code.** Only the active tab of a
section is mounted, and `<KeepAlive>` keeps the ones already shown. So a tab
restored from storage and never opened has registered nothing, and a click on
its button would do nothing. Such a tab is shown: a panel that has read nothing
is read by being opened. This was not in the first wording of the plan.

Rejected: references to component instances in the engine: that ties the
engine to the panels' internals, exactly what D12 avoids. Rejected as well: a
button inside each panel: the engine is then not touched, but the button's
place drifts apart across the three panels.

### R3. What is being looked at is reread

The catalog rereads the **current** level: the path and the ticks stay. Going
to the root is navigation, not a refresh, and the user did not ask for it.

Rows reread the same page with the same order.

### R4. While it runs, the icon spins and cannot be clicked

Otherwise on a slow source it is unclear whether the click registered, and a
second click starts a second round.

## How it is checked

- the registry: registration, removal on unmount, a call with an unknown id;
- `WorkspaceLeaf`: the button exists only when the feature provided
  `reloadTooltip` and the application provided `onReload`, and clicking it does
  not make the tab active;
- Playwright: a click on the catalog tab rereads the level, and the path is not
  reset; a click on the connections tab rereads the list and opens nothing; a
  click on a tab never opened shows it.

## What this round does not include

- a keyboard shortcut;
- "reload everything";
- automatic refresh on a timer.

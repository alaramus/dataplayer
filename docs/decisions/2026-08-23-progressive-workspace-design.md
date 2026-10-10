# A column appears together with its content

Date: 2026-08-23
Status: designed
Subproject: screen corrections following work in the browser

## For someone starting from a clean session

Read in this order: [AGENTS.md](../../AGENTS.md), decisions R12
(workspace) and R11 (component kit);
[2026-08-22-workspace-design.md](2026-08-22-workspace-design.md) — the engine;
[2026-08-22-three-column-workspace-design.md](2026-08-22-three-column-workspace-design.md)
— roles and three columns; [ENGINEERING.md](../../ENGINEERING.md), sections
"Frontend" and "Tests".

There is not a single line of backend here. Everything changes in
`frontend/src`, the API contract is not touched, the client does not need to be
regenerated.

What already exists and what we build on:

- The layout is a tree of sections; every edit of the tree is a pure function
  (`shared/workspace/tree.ts`), and `normalize` is called after any of them.
- A section carries `accepts` — the role of the panel that goes into it by
  default — and `pinned` — the right to stay on screen while empty. The role is
  opaque to the engine: it compares strings and never parses them.
- Where an opened panel goes is decided by `placement.ts` → `leafForKind`.
- What an empty pinned section shows is asked of the feature:
  `empty(accepts)` in `features/workspace/panels.ts`.
- A collapsed section takes `COLLAPSED_PX`, and the rest share the remainder by
  their fractions; `sizes` are not touched on collapse
  (`WorkspaceNode.vue`, `styleFor`).
- A saved layout is untrusted input: it is parsed, checked and rejected as a
  whole, and the version cuts off a foreign shape
  (`persist.ts`, `WORKSPACE_VERSION`).

One command that will be needed right away:

```bash
cd frontend && bun run dev
```

## Goal

Five things noticed while working with the screen.

1. The first run greets you with three columns, two of which are empty. The
   screen looks broken rather than empty, and does not say what to do.
2. Dragging knows nothing about roles. A data tab can be dropped into the
   connections column and break the three columns for good.
3. A single tab can be dragged onto the side of its own section. The result is
   a split where one half is empty — an action without a result that looks
   like a result.
4. Exactly one catalog is open: choose another connection and the previous one
   closes along with how far you got in it.
5. A data tab is labelled with the node name and nothing else. While there was
   one catalog, that was enough.

## What is not here

- **Keyboard shortcuts.** The application has not a single global one, and the
  scene does not promise what is not there. The layout accepts a list of "key —
  action" pairs under the actions block, but does not draw an empty frame for
  them. The shortcuts themselves are a separate subproject.
- **Help in the bottom bar.** The idea of showing the same thing behind an icon
  in the status bar once the scene is no longer on screen is postponed: the bar
  is empty today too, and what it is is a separate decision.
- **A colour label for a connection.** As in DataGrip, where a source is
  assigned a colour and it flows through the tabs. Telling apart two
  connections of the same type is done by the tab subtitle, and a colour is
  also a place where the user picks it.
- **Reordering tabs within the strip.** The deviation stays as it was.
- **Two catalogs of one connection.** A panel is still identified by what it
  shows.
- **Resizing the scene by the user.** The scene is the empty view of a column,
  not a panel: it has no tab, it cannot be closed and cannot be dragged.

## Decisions

### P1. A role is not only an opening address but also an admission

Until now `accepts` answered one question: where a newly opened panel goes. Now
it also answers a second one: what can be brought here by hand.

A drop is allowed only if the role of the dragged panel equals the `accepts` of
the target section. The role is still unknown to the engine — it already gets
`kindOf` from the feature (this is `roleOf`) and compares two opaque strings,
exactly as `leafForKind` does today. Not a single new concept.

Where a drop is impossible, the zone is not highlighted. A refusal must be
visible before the button is released: to highlight and not accept is worse
than not to highlight.

The alternative — allow everything and repair the consequences — is rejected:
the three columns are declared a property of the screen, not a habit of the
user, and a layout in which data sits in the connections column has no way to
get back.

### P2. A split-off section inherits the role but not the pinning

`splitLeaf` creates the new section with the `accepts` of the one it was split
from. Without this the very first split produces a section without a role, and
P1 would refuse everything brought to it afterwards — including the panel that
created it.

`pinned` is not inherited. Pinning is a property of a screen column, not of
every section: a split-off one must disappear when its last tab is closed,
otherwise every split would leave an empty trace behind.

### P3. A split that leaves a section empty is not a split

A side zone refuses if after it the target section would be left with nothing.
This is one rule for two cases:

- the single tab is dragged onto the side of its own section;
- anything is dragged onto the side of an empty section.

In both cases the centre remains — that is, "put here", not "split with this".

A consequence worth naming separately: **the "Connections" tab cannot be moved
anywhere, and it does not need a flag for that.** The `sources` role belongs to
one section; its side would leave it empty, and other columns do not take
another's role. The prohibition is derived from two general rules, not declared
as a third, particular one.

### P4. An empty column with nothing to say takes no space

A pinned section without panels, for which `empty(accepts)` answered `null`, is
not rendered. Its fraction goes entirely to the next neighbour in the direction
of the split; `sizes` in the tree are not touched, so the width that comes back
is exactly the one the user is used to. A separator is drawn only between two
visible neighbours.

This is the same technique already applied to the collapsed column, and for the
same reason: how a section looks now must not erase how it was made.

The fraction goes to the neighbour entirely, not shared proportionally among
all. With proportional sharing the connections column on the first run swells
from 20% to 28% — on a wide screen that is seven hundred pixels of empty list.
The "to the neighbour" rule keeps the connections column where it was put and
gives all the freed space to what it was freed for.

### P5. The scene is the empty view of the right column, and it derives the stage itself

`empty("navigate")` returns `null` **always**, without any state: the middle
column simply has no empty view, and P4 removes it from the screen.
`empty("work")` returns the scene — so the right column is always on screen.

No stage is introduced in the engine, and `empty` does not change its
signature. The scene derives the stage from what it already has: the list of
connections (vue-query) and `activeConnectorId` (from `workspaceActionsKey`).

| What is visible | Screen |
| --- | --- |
| no connections | connections ¦ scene: what this is, and `[+ Add connection]` |
| there are some, no catalog open | connections ¦ scene: choose a connection on the left |
| a catalog is open | connections ¦ catalog ¦ scene: choose a table or a file |
| a table is open | connections ¦ catalog ¦ data |

The scene carries a real button, not a reference "press the plus on the left".
Sending a person to look for a button elsewhere on the screen when it can be
given here is worse than giving it.

The hints are about the current level, not about the platform. Abstract text
about the application is read once; "check nodes with the checkboxes, and the
menu in the header will say what can be done with them" is something not
visible in the interface until you stumble on it.

### P6. As many catalogs as were opened

`{ replace: true }` when opening a catalog is removed. AGENTS.md predicted
exactly this: "allowing two catalogs side by side is dropping one flag at one
call site". The deviation *One catalog at a time* is struck out.

A repeated click on a connection does not spawn a tab: the panel is identified
by `catalog:{connectorId}`, and `open()` activates the existing one.

Switching tabs does not reset a catalog — the section keeps the inactive panel
in `<KeepAlive>`. Until now this could not be verified, because there was one
catalog.

A split inside the middle column only now makes sense: two catalogs side by
side is the scenario P1 is written for.

### P7. The active connection is read from the tree

Currently `activeConnectorId` is "the first catalog panel that comes along".
With three catalogs it will return not the one being looked at but the one
opened earliest.

It is read from the tree: sections that accept `navigate`, the focused one
preferred, its active panel. No second record that could drift from the tree is
introduced — the same reason it is already read from the panels rather than
stored beside them.

The connection list gets two states instead of one: **open** — the connection
has a catalog tab, a muted row highlight; **active** — its catalog is visible
now, full highlight. A row highlight, not a fourth badge in it: a connection
row is an icon, a name and a status dot, and there is nothing to add to it. The
collapsed strip (`ConnectorRail`) gets this for free — the row is the same,
only narrower.

### P8. A tab says whose it is

`PanelLook` gets a fourth field — a muted subtitle. Data tab: the node name,
next to it the connection name in pale, shrinking first. The icon is the source
type instead of the generic `table_chart`.

A hover tooltip is rejected: two connections of the same type are
indistinguishable by eye, and one has to hover exactly when there are many
tabs, that is, at the worst moment. A compound title `prod-db · users` is
rejected: the node name — what the eye looks for — moves to the right and is
truncated first.

The data panel starts carrying `adapterType` and the connection name — for the
same reason the catalog panel already carries them: a layout restored from
storage draws the icon before the list of connections has been read.

The panel schema changes, so `WORKSPACE_VERSION` → 3, and a saved layout is
rejected as a whole in favour of the default one. The mechanism for this exists
and was already used in the move to version 2.

## What changes

### Engine (`shared/workspace`)

- `model.ts` — `LeafOptions` already carries `accepts`; nothing is added.
- `tree.ts` — `splitLeaf` passes `accepts` to the split-off section (P2).
- `dropZone.ts` — the zone is computed with regard to the role and to "would be
  left empty" (P1, P3). A pure function, so it is tested without mounting.
- `context.ts` — `PanelLook.subtitle?: string` (P8); the context answers
  whether a section accepts what is being dragged.
- `useWorkspace.ts` — `endDrag` refuses by the same two rules: what computes
  the highlight and what applies the move must not drift apart.
- `WorkspaceNode.vue` — a hidden section is not rendered, its fraction goes to
  the neighbour, a separator only between visible ones (P4).
- `WorkspaceLeaf.vue` — a subtitle in the tab; zones that refuse are not
  highlighted.
- `persist.ts` — `WORKSPACE_VERSION` → 3.

### Screen (`features/workspace`)

- `panels.ts` — `empty("navigate")` → `null`; `empty("work")` → the scene;
  `lookOf` of the data panel gives the type icon and the subtitle; the data
  panel schema gets `adapterType` and the connection name.
- `panels/WorkspaceScene.vue` — new: three stages, a button, hints.
- `panels/EmptyNavigate.vue`, `panels/EmptyWork.vue` — deleted, their place
  is taken by the scene.
- `WorkspacePage.vue` — `{ replace: true }` removed; `activeConnectorId` is
  read from the tree; `openRows` accepts what the tab is labelled with.
- `state.ts` — `openRows` changes its signature; a set of open connections for
  the list appears.
- `panels/ConnectorsPanel.vue`, `panels/ConnectorRail.vue`,
  `features/connectors/ConnectorList.vue` — two row states.

### Component kit

- `shared/ui/theme.css` — the colour of the muted row highlight is declared by
  meaning and in both themes. Values do not appear in screens.

### Documents

- AGENTS.md: strike out *One catalog at a time*; describe the screen as
  "a column appears together with its content"; add the deviations below.

## Order of work

Test — implementation — green test, in steps, each of which leaves the screen
working.

1. **Drop rules** (P1, P2, P3) — entirely in the engine, with unit tests:
   role inheritance, refusal by role, refusal by "would be left empty".
2. **Hidden column** (P4) — a unit test on fractions and separators, then
   `WorkspaceNode.vue`.
3. **Scene** (P5) — first `empty("navigate")` → `null` and the three stages,
   then the content.
4. **Several catalogs** (P6, P7) — the removed flag, `activeConnectorId` from
   the tree, two row states.
5. **Tab label** (P8) — panel schema, version 3, subtitle.
6. **Documents** — AGENTS.md last, according to what came out.

## What holds it up

| What | By |
| --- | --- |
| the role is inherited on split | unit test `tree.spec.ts` |
| a drop of another role is rejected | unit test `dropZone.spec.ts` |
| a split leaving an empty section is rejected | unit test `dropZone.spec.ts` |
| the fraction of a hidden section goes to the neighbour | unit test on the fraction computation |
| four stages of the screen | Playwright scenario |
| two catalogs side by side, switching does not reset the path | Playwright scenario |
| "open" and "active" in the list | Playwright scenario |
| "Connections" cannot be dragged anywhere | Playwright scenario |
| a data tab names its connection | Playwright scenario |

Each new scenario is verified in reverse: the change is rolled back, the test
is run and fails. A scenario that has never gone red proves nothing.

## Known deviations this will add

- **A refusal is visible only as an absence of highlight.** The screen does
  not explain why something cannot go here: it simply does not offer it.
- **A hidden column stays in the tree.** It is visible in localStorage and in
  layout tests, although it is not on screen. That is intended — otherwise the
  width cannot be returned — but "what I see" and "what is recorded" diverge
  here.
- **The fraction goes to the neighbour on the right, not by meaning.** The rule
  is right for a row of three columns and arbitrary for a top-to-bottom split,
  where "the next neighbour" means "the one below".
- **The connection name on a tab is recorded at the moment of opening.** If the
  connection is renamed, the tab lags until reopened. Exactly the same is
  already true of the catalog tab's title.
- **A saved layout is reset once** on the move to version 3.
- **The scene knows three stages and not one more.** A source that has no
  catalog does not get into it: the middle column simply does not appear for
  it, and there is still no way to say so in words.
- **A connection row carries four signs.** Icon, name, status dot and the
  "open" highlight. On a long list with several open catalogs the list becomes
  motley, and nobody has measured this.

# The explorer, the tab strip and the bottom bar

Corrections following work with the three-column screen. Not a subproject: no
new layer, no new source capability — but four of the eight corrections change
what is recorded in
[2026-08-22-catalog-list-design.md](2026-08-22-catalog-list-design.md), and are
therefore recorded here rather than in a commit message.

## Goal

The screen is assembled, and working with it turned up eight places where it
does not behave the way the explorers the hand is used to behave.

## What changes in earlier decisions

- **S6 (menu target)** — "nothing checked — the current node" is cancelled for
  actions that change the node itself. Standing in a folder and deleting it
  from the menu is not what the user asked for; they asked to delete what is
  checked.
- **S7 (one call about the set)** — the response stops being a list of what
  applies and becomes a dictionary with an applicability flag.
- **S8 (bulk)** — does not change in substance: `bulk` still does not come out
  as a flag, it is expressed through `applicable=false` for the set.
- **S11 (collapsed section)** — a collapsed section is no longer "a chevron and
  nothing else": a feature can put something of its own in it.
- **S5 (checking and opening)** — a third gesture is added: the `..` row.

## Decisions

### V1. The menu does not change shape: the whole dictionary, applicability is a flag

`POST /connectors/{id}/actions` answers with **all** of the source's actions,
and each carries `applicable` — whether it can be done with the nodes asked
about. The client draws all rows and dims the inapplicable ones.

The former response — only what applies — gave a menu that changed its
contents at every step: two items at the root, four inside a folder, two
different ones on a checked file. A menu from which items disappear teaches
nothing: the user does not know what the source cannot do at all and what
cannot be done right now.

This does not weaken permissions. Execution still asks `available` for the
specific node (`_action_for_node`), so getting into the list does not mean
getting the right. That is exactly why the flag is safe: it is for the eyes,
not for the gate.

### V2. An action declares what it changes

`Action.acts_on: ClassVar[Literal["node", "children"]]`. `Rename` and `Delete`
are `node`, `CreateFolder` and `Upload` are `children`.

This is what lets one menu have two targets without knowing a single action
name. An item with `node` goes to the checked nodes and is dimmed while nothing
is checked; an item with `children` goes to the level being looked at and is
always live. A client that told them apart by name would have to be taught
every new action — and the whole point of D9 is that a source adds an action
and the screen does not change.

It is declared next to `applies_to`, not derived from the class: `_ActsOnNode`
is a device of the file driver, not a common contract. There is nothing here to
derive it from structurally, the way `takes_file` is derived.

The side effect, and the main result: while inside a folder, it can be neither
renamed nor deleted — it has to be reached with a check from the level above.

### V3. No actions — no three dots

A source that does not implement the capability answers 501; in that case the
menu is not drawn at all. Previously the button stood dimmed and promised what
was not there. A dimmed item means "not now"; a dimmed menu would mean "never",
and that is not a state but an absence.

### V4. Up is the first row of the list, not a button in the header

`..` is the first row, without a checkbox, with a go-up icon. The
`arrow_upward` button in the header is gone.

Every explorer works this way, and the hand is already in the list: the way up
is a place among places, not a command. The row is drawn above an empty level
too — in an empty folder the way back is needed most.

### V5. The path starts with a home button and stands on one line with the icon

The first crumb is not the connection name but a "home" button. The connection
name is already written on the tab, and a second time it tells nothing but
eats the column's width; so it is removed from the panel header altogether,
and the header became one line: source type icon, path, three dots. Three
things about one connection are not a stack of lines: a header takes height
from the list the column exists for.

No path — no pill. At the root there is nowhere to go, and a database catalog
has only one level anyway: schemas are a grouping, not a place, so a path never
appears there, and a pill with a single "home" button would promise navigation
that does not exist. We do not pay for this with header height: the line is
held by the button next to it, not by the crumbs.

The tail of the path scrolls inside the pill, while the "home" button stands
outside the scroll: a path that did not fit the column must not carry away the
only step that returns to the top.

### V6. The collapsed sources column keeps its icons

The engine gets `collapsedOf(panelId)` — symmetrical to `emptyOf(accepts)`: it
knows the section is narrow, and the feature knows what is worth that width.
Only connections answer: a type icon and a status dot, a click opens the
catalog.

It opens the catalog specifically, not the connection window: the collapsed
column is a way back into a source, and the window is reachable from the
catalog header (S9). `COLLAPSED_PX` grows from 28 to 40 — exactly so the icon
fits.

### V7. Tabs wrap, the strip can be cleared down to the current one

`overflow: hidden` on the tab strip is replaced by `flex-wrap: wrap`. A tab
that cannot be seen cannot be reached, and the column is narrow by
construction.

Next to the chevron a "close others" button appears: it closes all tabs of the
section except the active one. It is a layout operation, so it lives in the
engine; a panel to which the feature gave no close cross survives it the same
way it would survive its own cross.

### V8. The bottom bar

A `q-footer` of the same colour as the header, with an empty `status` slot.
Empty on purpose: what goes into a status bar — what is connected, what is
running, what the last query cost — arrives together with the work that
produces it. The space for it is needed now, so the layout is closed at the
bottom.

## What is not done

- **One call instead of two.** The menu asks the server twice: about the level
  (the dictionary is there) and about what is checked. Merging them into one is
  a request body that says two different things about two different sets.
- **Tab order.** Dragging within its own strip still does nothing.
- **Contents of the bottom bar.**
- **Collapsed catalog and collapsed grid.** A list of text has nothing to show
  in forty pixels; the mechanism exists, nobody wants it.

## How it is verified

| What | By |
| --- | --- |
| the response carries the whole dictionary, applicability as a flag | `uv run pytest tests/` |
| the root gives `create_folder`/`upload` as applicable, `rename`/`delete` as not | `uv run pytest tests/` |
| every file action declares `acts_on` | `uv run pytest tests/` |
| `toMenu`: while nothing is checked, everything that changes a node is dimmed | `bun run test:unit`, pure function |
| `toMenu`: an item's target is the checked nodes or the level, by `acts_on` | `bun run test:unit` |
| a collapsed section shows what the feature gave | `bun run test:unit`, WorkspaceLeaf |
| "close others" leaves the active one and the uncloseable | `bun run test:unit`, useWorkspace |
| the menu is dimmed without a check and live with one | Playwright, `aria-disabled` |
| a database has no three dots at all | Playwright |
| `..` is the first row of the list and aligned with the rows that have a checkbox | Playwright |
| home returns to the root, the path stands on one line with the icon | Playwright |
| a database and the root have no path at all | Playwright |
| the collapsed sources column opens a connection | Playwright |
| the strip is cleared down to the current tab | Playwright |
| the bottom bar is on screen | Playwright |

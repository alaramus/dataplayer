# A tab is seen in the hand, and it is dropped onto the strip

Date: 2026-08-23
Status: designed
Subproject: the tab drag gesture

## For someone starting from a clean session

Read in this order: [AGENTS.md](../../AGENTS.md), decision R12
(workspace); [2026-08-22-workspace-design.md](2026-08-22-workspace-design.md)
— the engine; [2026-08-23-progressive-workspace-design.md](2026-08-23-progressive-workspace-design.md)
— roles as admission (P1), a split leaving a section empty (P3), a column
appearing together with its content (P4); [ENGINEERING.md](../../ENGINEERING.md),
sections "Frontend" and "Tests".

There is not a single line of backend here and not a single line of a feature:
everything changes in `frontend/src/shared`, the API contract is not touched.

What already exists and what we build on:

- Dragging lives in the engine: `startDrag(panelId)` on pressing a tab,
  `endDrag(targetLeafId, zone)` on release over a section, `dragging` is the
  only record of what is happening.
- The zone is computed by the pure function `dropZoneAt(rect, x, y)` over the
  rectangle of the whole section: a quarter from each edge, the rest is the
  centre.
- What a section will accept is decided by `admissionOf` → `admittedZone`:
  another role is rejected entirely (P1), a side that leaves the target empty
  becomes the centre (P3).
- The highlight is not drawn where a drop is impossible, and that is the only
  way the screen reports a refusal.
- The threshold that tells a press from a drag already exists in the
  application: `PRESS_THRESHOLD_PX` in `WorkspaceSeparator.vue`.
- A layer on which something floats is declared by name in
  `shared/ui/layers.css`, not by a number.

One command that will be needed right away:

```bash
cd frontend && bun run dev
```

## Goal

The gesture does not show what is happening. Having grabbed a tab, the user
sees it in its old place and a translucent rectangle somewhere else; what
exactly is being dragged has to be kept in one's head. And to put a tab next to
others, one has to aim at the middle of another panel and see a highlight the
size of the whole panel — even though the tab will end up in the strip above,
not across the whole panel.

Browsers solved this long ago: a tab leaves the strip together with the cursor,
and tabs are merged by bringing one to the strip of another window. We take
this model.

## What is not here

- **Reordering tabs within the strip.** A drop on the strip always appends to
  the end, no caret is drawn between tabs. The deviation stays as it was: a
  tab's position in the strip would require an index in all tree operations and
  in the chain that leads to them.
- **Tearing a tab off into a separate window.** A window is a connection form,
  not a container of panels; the comparison with a browser ends where a browser
  gets a second window.
- **Panel content in the ghost.** The hand shows exactly what the tab shows:
  icon, title, subtitle. A scaled-down copy of the grid is a second render of
  the panel on every cursor movement.
- **Keyboard shortcuts and cancellation.** Ctrl+Z does not appear, Escape does
  not interrupt a drag — releasing outside the zones interrupts it, as now.

## Decisions

### G1. A drag starts from movement, not from a press

Currently `startDrag` is called on `pointerdown`, and the tab is activated by
the click that follows if no drag happened. While the tab stayed in place, this
cost nothing.

Now a tab disappears from the strip when a drag starts, and a press that did
not become one would make it blink on every click. So a press only remembers
the tab and the point, and `startDrag` is called from the first `pointermove`
that has moved past the threshold.

The threshold is the same as the column separator's: `PRESS_THRESHOLD_PX`, and
it moves to `model.ts` — to the other quantities that percentages cannot
express. Two identical numbers in two files are the same statement made twice.

A click on a tab does not change because of this: it still comes after a press
that did not become a drag, and still activates the tab.

### G2. A tab is seen in the hand

While `dragging` is not empty, the tab with that identifier is not drawn in its
strip — the neighbours shift, as in a browser — and a copy of it rides under
the cursor.

The body of the source section does not change: the panel stays drawn even if
the section's only tab is being dragged. The browser analogy ends here: there
the last tab carries the window away, here there is nothing to carry away, and
blinking the content for the sake of resemblance is a bad trade.

The ghost is a separate component, lives in `WorkspaceRoot` and takes the
engine's `lookOf`. It cannot live in a section: the cursor leaves its bounds in
the very first second.

### G3. A section is two rectangles, and they mean different things

The tab strip is "merge": the tab goes to the end of the strip and becomes
active. The body is "split": the section is divided, and the tab takes half.

One target for one intention. Today the centre of the body means the same as
the strip will mean, and those are two roads to one result, of which the
visible hint (a highlight over the whole panel) describes a result other than
the one that will happen.

The rectangles are measured in the same place as before — in `WorkspaceLeaf`,
which has both elements — and go into a pure function. The engine still knows
nothing about panels or about what is drawn in the strip.

### G4. The body has no neutral middle

Four edges divide the body along the diagonals: the nearest one wins, and
nearness is measured as a fraction of the side, not in pixels — otherwise on a
wide panel top and bottom would take almost everything. An exact tie (the exact
centre) is resolved in favour of the wider side; this rule is already written
for corners and simply stops being a special case.

The former quarter from each edge (`EDGE`) disappears together with the centre:
it was needed only to separate the edges from the middle.

### G5. The highlight shows the outcome, not the zone

Previously the highlight was a picture of the zone: centre — the whole panel.
Now it shows where the panel will end up:

| What will happen | What is highlighted |
| --- | --- |
| it will join the others as a tab | the strip |
| it will split the section | the half it will take |
| it will take the whole section | the whole section |

The third row is P3: a side that leaves the target empty becomes "put here".
The highlight over the whole panel remains exactly where it is truthful.

The second and third rows cannot be told apart by the zone alone — "centre" now
means both "into the strip" and "onto the whole empty section". What tells them
apart is the same thing that decides: whether the section holds anything at
all. That is already computed — `admissionOf` answers `remaining` — and there is
no reason to start a second count.

### G6. What is in the hand is seen above everything

The ghost gets its own layer, declared by name next to the others — above the
floating window: the hand cannot end up under what it passes over. Below
Quasar's menus and dialogs, like everything of ours.

A drag released entirely outside the workspace ends: the root listens for
release on the window while `dragging` is not empty. Without this the ghost
would stay hanging on the cursor and `dragging` non-empty; today this is also
the case, but invisibly.

## What changes

### Engine (`shared/workspace`)

- `model.ts` — `PRESS_THRESHOLD_PX` moves here from the separator.
- `dropZone.ts` — `dropZoneAt` takes two rectangles instead of one; the middle
  disappears, the nearest edge wins (G3, G4). A pure function.
- `WorkspaceLeaf.vue` — threshold (G1), hidden tab (G2), measuring the strip
  and the body, highlight by outcome (G5).
- `WorkspaceDragGhost.vue` — new: a copy of the tab under the cursor.
- `WorkspaceRoot.vue` — tracks the cursor, holds the ghost, ends a drag
  released anywhere (G6).
- `WorkspaceSeparator.vue` — takes the threshold from `model.ts`.

### Component kit

- `shared/ui/layers.css` — `--dp-layer-drag` above `--dp-layer-window`.

### Documents

- AGENTS.md: a consequence of R12 about the gesture; the deviations below.

## Order of work

Test — implementation — green test, in steps, each of which leaves the screen
working.

1. **Geometry** (G3, G4) — entirely in a pure function, with unit tests: strip,
   nearest edge, tie, degenerate rectangles.
2. **Threshold and the disappearing tab** (G1, G2) — unit tests on
   `WorkspaceLeaf`: a press without movement does not start a drag, the tab
   being dragged is not drawn in the strip.
3. **Highlight by outcome** (G5) — a unit test on the highlight rectangle in
   three cases.
4. **Ghost** (G2, G6) — component, layer, root.
5. **Scenario** — Playwright: grabbed, saw, dropped on the strip, dropped into
   the body, dropped onto another role.
6. **Documents** — AGENTS.md last, according to what came out.

## What holds it up

| What | By |
| --- | --- |
| the strip means "merge" | unit test `dropZone.spec.ts` |
| in the body the nearest edge wins | unit test `dropZone.spec.ts` |
| a tie is resolved by the wider side | unit test `dropZone.spec.ts` |
| a press without movement does not start a drag | unit test `WorkspaceLeaf.spec.ts` |
| the tab being dragged disappears from the strip | unit test `WorkspaceLeaf.spec.ts` |
| the highlight shows the outcome | unit test `WorkspaceLeaf.spec.ts` |
| the ghost shows the same as the tab | unit test on the component |
| the ghost is above the floating window | Playwright scenario: the layer scale is read from the browser |
| the whole gesture | Playwright scenario |

Each new scenario is verified in reverse: the change is rolled back, the test
is run and fails.

## Known deviations this will add

- **The "merge" target is a strip thirty-one pixels high.** It is harder to hit
  than half a panel, and in a narrow column it is narrow.
- **A drop on one's own strip does nothing.** It did not before either: the
  order of tabs in the strip does not change, and the section the tab was taken
  from is the same one.
- **A collapsed column remains a target.** Its strip is forty pixels with a
  handle, and the tab will go where it cannot be seen until the column is
  restored.
- **The ghost does not show content.** What exactly is being dragged is visible
  exactly to the extent it is visible on the tab; two tabs of the same node from
  different connections are told apart by the subtitle and nothing else.
- **The ghost is drawn under the cursor, not under the grab point.** The tab is
  "taken by the middle", wherever the press happened to land.
- **A drag cannot be cancelled from the keyboard.** Escape does nothing; a drop
  outside the zones is the only way to change one's mind.
- **The layer order is checked only in the browser.** A unit test sees an empty
  string in place of a `.css` file's contents — that is how Vite works — so
  "the ghost is above the window" is held by a scenario, not by a test that is
  cheaper to run.
- **The threshold is not enough for everyone.** Three pixels is the same number
  as the column separator's; on a touch screen or with a shaky hand it may turn
  out to be too small, and nobody has measured this.

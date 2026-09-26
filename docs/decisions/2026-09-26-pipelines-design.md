# Pipelines: connections laid out on a canvas, and links run between them

Date: 2026-09-26. Decisions: D175, D176. Builds on D97 (the graph viewer),
D164 (one paste answer for a pair), D165–D169 and D171 (what a paste does),
D168 (transfers as owned jobs), D129 (a stored layout kept on the server) and
D174 (the connections map), which this replaces as a screen.

## The problem

D174 draws everything every connection could give every other, all at once.
It answers "what is possible" and nothing else: a person who wants the orders
table of one database saved nightly into a folder of another does not want
forty arrows, they want to lay out those two things and say "this, into
that". The pair window does it once, for two catalogs side by side, and then
it is gone. What is missing is a place where the objects a person moves
between connections are laid out, joined, kept, and run again.

## D175. A pipeline is a named canvas of cards, kept on the server

### The space

- **"Pipelines" takes the rail slot of the connections map** (D174): a space
  beside Data, Dashboards and AI, drawn as their card — frame, head, a row of
  commands. The map stops being a screen of its own; its answer lives on as
  the canvas's hint (D176).
- **On the left, the list of connections**, as in Data: names and types, no
  catalogs.
- **On the right, the canvas** of the pipeline chosen in the head: a switcher
  of the person's pipelines, and New, Rename and Delete beside it. With none,
  the canvas offers to create one.

### Cards

- **A connection dragged from the list and dropped on the canvas** opens a
  window of that connection's catalog with ticks: the person ticks what the
  pipeline works with — tables, views, files, folders, keys, declared tables —
  or a place, a schema or a folder, where something is to arrive.
- **What was ticked becomes a card** where it was dropped: the connection's
  name in its head, one row per ticked node beneath, as a table's columns in
  D97's diagram. Cancelling the window drops nothing.
- **A card's settings button opens the window again** on what it holds; a row
  untick removes it, and the links that used it go with it after a
  confirmation naming them.
- **A connection can be on the canvas as several cards**, a source in one
  place and a destination in another.
- Cards are moved by hand and stay where they are put. The canvas pans and
  zooms; there is no 3D here, and no automatic layout unless asked for.

### Kept on the server

- **A pipeline belongs to the person who made it**: a name, its cards — each a
  connection, the node ids ticked with the labels they had, a position — and
  its links (D176). Kept like a dashboard (D129), private in this step.
- **A card names nodes, it does not hold them.** A node gone since is drawn as
  a placeholder row saying so; a connection no longer readable or switched off
  makes its card say that, and its links cannot run.
- **Bounds**: 100 pipelines a person, 50 cards and 200 links a pipeline, 100
  rows a card.

## D176. A link is drawn row to row, set in a panel below, and run from it

### Drawing one

- **Dragged from a row of one card to a row of another**, a link asks the
  server what can be done from that node into that one: the same paste kinds
  and the same answers as Paste and the pair window (D164). The destination
  row stands for both a place — a folder or a schema something arrives in —
  and a target — a table rows go into — and each kind takes the one it
  understands.
- **None fits**: no link, and why. **One or several fit**: the link is drawn,
  and the panel below opens on it.
- **Both ends in one connection** are refused in this step: copying inside a
  connection is its catalog's own Paste (D74).

### The panel below

- **It says what the link does**, in the words of its operation: "Save as CSV:
  Sales · orders → Files · reports/". Several fitting operations are a choice
  there — a file into a schema: "Create a table" or "Add rows to a table".
- **It holds the operation's choices**, the ones Paste asks: a file name, what
  to do with a taken name, the columns of a new table, the pairing of columns
  into a ticked one. Chosen once, they are the link's and are kept with it.
- **Run** runs the link by what is kept, never by what the client sends: the
  server reads the pipeline, checks both ends and the person's access again,
  and runs the operation exactly as Paste would — a transfer as its job (D168),
  a row paste in the request.
- **The result stays on the link**: running, done or failed with its sentence,
  and when. A link selected again shows it, and Run runs it again.

### The hint

- **A button of the canvas's row of commands draws, dashed, every link that
  could be made** between the rows on the canvas, labelled by what it would
  do, from one request. D174's answer by connection is its first filter, so
  only pairs of connections that can meet at all are asked about node by node.
  A dashed link clicked becomes a link, as if drawn.
- A canvas with more pairs of rows than one answer checks, 400, hints only
  the links of the card selected, and says so.

## Settled during implementation

- **Built in two passes**: the space, pipelines and cards first (D175), then
  links, the panel, Run and the hint (D176).
- **A connection pressed in the list** opens the same window as one dropped,
  and its card goes to the nearest spot clear of the others in the middle of
  the view; a dropped one lands under the pointer.
- **Groupings are walked into in the window**, not D75's filter above the
  list, so a schema can be ticked as a place. The top of a connection is
  tickable where it holds no groupings, as the top of personal storage does.
- **A card also keeps its connection's name** from when it was dropped, for a
  card whose connection is gone and can no longer say it, and each row keeps
  the names of the places above it, so two `orders` of two schemas differ.
- **A card is checked by a request of its own**, against the card as stored,
  one row after another; a source without a way to say where a node lives is
  not checked. A card taken off asks first.
- **A selection fades nothing on this canvas**, unlike D97's diagram.
- **D174 moved** to the pipelines' architecture file with its route: the map's
  screen, its pair-opening and the header's rule for a space without a first
  panel went with the screen.
- **A pressed card goes beside the others before below them**, 120 pixels
  clear, and the view pans just enough to show it: links run from a card's
  right edge to the next card's left, and a column of cards made them loop.
- **What a link can do is the pair window's answer** (`pair/offers`) with one
  tick each side, so drawing one needs no route of its own.
- **A link keeps its operation's title** beside its kind, as a row keeps its
  label, so the canvas labels it without naming kinds.
- **The last run is a row of its own**, not a field of the body: a run must
  not raise the version the next save is checked against. A transfer's
  outcome is its job's, read when the runs are read; the screen reads them
  again when such a job ends.
- **Run saves the draft first**, and a paste goes through `transfers/run.py`,
  taken out of the paste route so Paste and a link share one door.
- **The windows for a new table's columns and for a pairing** open on what
  the link kept, and their button keeps the choice rather than running.
- **The map's route went**, and with it the map for every pair of
  connections: the hint asks `open_kinds` pair by pair. With no card selected
  on a canvas past the ceiling, the hint says to select one.
- **The hint goes when pressed again**, and when a card or a link changes.

## Out of scope

- Running every link of a pipeline in one press: the next step.
- Chains — the result of one link as the source of the next — and
  transformations on the way.
- Schedules, sharing a pipeline, a history of its runs beyond the last.
- Links inside one connection.

## Known deviations, accepted with it

- **A row paste still runs in the request**, as D166's does, up to its 5,000
  rows; only transfers are jobs. "Run all", when it comes, needs them all as
  jobs.
- **Labels are kept as they were ticked.** A table renamed since keeps its old
  name on the card until the window is opened again.

## Acceptance

- A connection dragged onto the canvas opens its catalog with ticks; ticked,
  it is a card of those rows; opened again from its settings, it changes.
- The same connection lies on the canvas as two cards.
- A link drawn from a PostgreSQL table to a folder of personal storage opens
  the panel on "Save as CSV" with its name; Run saves the file as a transfer,
  the link keeps "done", and runs again.
- A link from a CSV file to a schema offers "Create a table"; to a table, "Add
  rows to a table"; from a folder to a schema, nothing, and says why.
- The hint draws the possible links among the rows on the canvas, dashed.
- A pipeline is named, kept and reopened; another person does not see it.

Tests cover the pipeline document and its bounds, access to it, what a link
asks and runs by its kept settings, the hint's answer and its ceiling, the
card and link logic as plain functions, and in the browser a card dropped and
ticked, a link drawn and run from the panel, and the hint.

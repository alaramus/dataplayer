# Two connections side by side

Date: 2026-09-25. Decision: D167. Builds on D93 (detaching a tab), D162,
D164 and D166; the paired view proposed in
[Interactions between connections](2026-09-25-cross-connector-interactions-design.md).

## The problem

Paste answers what a clipboard can become in the place it is chosen in. It
does not answer the question a person asks first, looking at two connections:
what can be done between these two at all. With five kinds of paste, and more
to come with every source type, that answer should be on the screen rather
than found by copying and trying.

## D167. A pair window holds two catalogs and what can be done between them

### Making a pair

The gesture is D93's. While a catalog tab is carried, the application header
shows a second target, **Pair**, beside **Open in a window**. Other tabs see
only the first.

- **The first drop makes a waiting pair.** Nothing opens and nothing moves:
  the catalog stays where it was, and the header shows a waiting pair — that
  catalog's connection, an empty slot and a cross. The person can go on using
  the catalog, down to the folder they want, while finding the second.
- **The second drop makes the pair.** While a catalog tab is carried, the
  empty slot is the target (Pair still is too). Dropping there opens the pair
  window, and both catalogs move into it alive, as D93 moves a panel: the
  folder each stood in, its ticks and its filter come with it.
- **Without dragging.** A catalog's row of commands (D112) offers Pair, which
  makes it the waiting one. Pressing the empty slot lists the connections;
  choosing one opens its catalog as the second side. Together these are the
  whole gesture without a pointer.
- **One waiting pair.** A new first drop replaces it. The cross cancels it;
  closing the waiting catalog clears it; it is not kept across a reload.
- **Two connections, not two catalogs.** A catalog of the waiting pair's own
  connection is not accepted — the slot does not light and says "Pick another
  connection". Within one connection Paste is the source's own (D74), and the
  pair would have nothing to show.

### The pair window

A window of the window manager (D14), opened large and maximizable, titled
with both connections: "Files and Postgres". There may be several at once.
Its two halves are the two catalog panels, unchanged: their own navigation,
menu, Copy and Paste. A **Swap sides** command exchanges them. Closing the
window returns both catalogs to the catalog column, to the places D93 would
return them to. Like a detached panel, a pair lasts for the page session; the
persisted layout holds its catalogs docked.

### The bar

Beneath the two catalogs, one bar lists what can be done between them, in
both directions at once, so there is no direction to choose first.

- **From the ticks.** For each direction, the ticked nodes of one side are
  the source, and the other side's place — and its one ticked node, when
  there is exactly one — the destination. Copy and move are both listed: in a
  pair nothing is held on a clipboard, so the mode is the item's own. Each
  item names what it does, to what and where — "Create a table in demo_lab",
  "Add rows to orders", "Save orders as CSV in reports" — with a button.
- **Unavailable items stay**, greyed, with their reason, as a Paste hint does.
- **Before anything is ticked**, the bar lists what the two connections can
  do between them at all, by kind and direction, each with what to tick:
  "Files → Postgres: Create a table — tick a file readable as rows". This is
  the discovery the window is for, and it needs no node: whether a kind serves
  a pair of connections is what the registry of D164 already decides.
- **Running an item is Paste.** The button opens exactly the windows a Paste
  of the same offer opens — Save as CSV, Create table, Bring rows in, the
  conflict window — and runs the same `/paste`. Afterwards the catalogs
  refresh as after a Paste: the destination always, the source when the
  offer changes it.

### What the server adds

- **One answer for a pair of sides.** Both sides are sent — connection, place,
  ticked nodes — and the answer is D164's offers for both directions and both
  modes, computed by the same registry and the same checks. The bar asks it
  once per change of either side rather than four times.
- **What a kind needs ticked.** Each kind states, in words, what its source
  must be ("Tick files", "Tick a table or a view"), so the bar before any tick
  and an unavailable item say it without the client naming a kind.

## Out of scope

- Dragging rows from one catalog to the other. That is the next step, and it
  will run the same offers.
- A pair of more than two, a graph of every connection, and pipelines.
- Keeping pairs across a reload.

## Acceptance

- Carrying a catalog tab shows Pair beside Open in a window; carrying a grid
  tab shows only the latter.
- The first drop leaves the catalog in place and shows the waiting pair; the
  cross and closing that catalog both clear it.
- Dropping a second catalog of another connection opens the pair window with
  both catalogs where they were; a catalog of the same connection is refused.
- Choosing a connection from the empty slot opens its catalog as the second
  side, with no dragging at all.
- With nothing ticked the bar lists the kinds for both directions and what to
  tick; ticking a CSV on the left lists "Create a table" and, with a table
  ticked on the right, "Add rows to" it and "Save … as CSV" back to the left.
- A button opens the same window as Paste and the catalogs refresh after it.
- Closing the pair window puts both catalogs back in the catalog column.

Tests cover the pair answer and the kinds' own words on the server, the
waiting pair and the bar's decisions as plain functions, the window and its
gesture in the browser.

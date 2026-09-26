# Chains: what one link makes, read by the next

Date: 2026-09-26. Decision: D178. Builds on D175, D176 and D177 (pipelines,
their links, one run of them all), D164 (one paste answer for a pair), D166
(rows pasted) and D168 (transfers). Takes up D177's "handing data from one
step to the next".

## The problem

D177 runs the links of a pipeline in order, but a row is a node ticked in a
connection: something that exists when the card is made. A person who wants a
table saved as CSV into a folder and that file then copied to a server must
run the pipeline once, tick the file the first run left, and draw the second
link from it. And when the first link keeps both names under "Keep both", the
file it makes is `orders (2).csv` while the second still reads `orders.csv`.
What a link makes is the next link's input, and the canvas has nowhere to say
so.

## D178. What a link makes is a row of its card, and the next link reads it

### The result row

- **A link that makes something draws it as a row of its target card**, just
  below the row it writes into: Save as CSV the file, Create a table the
  table, Copy and Move the file or folder carried. It is named as it will be —
  the file name kept or suggested, the table's name, the carried node's own —
  and marked by the link making it: "orders.csv ← 1". Its name follows the
  link's choices as they change.
- **Adding rows to a table makes nothing new**: the table is a row of the
  card already, and a link from it runs after (D177).
- **A result row is the link's, not ticked.** It is not in the card's window,
  it is not checked against the connection as ticked rows are (D175), and it
  goes with its link: the link taken away, or changed to an operation that
  makes something else or nothing, takes the row and the links that use it,
  after a confirmation naming them.
- **It stays the link's once the object exists.** Every run makes it again,
  and the row keeps saying which link makes it.

### Drawing from it and into it

- **A result row is joined like any other row**: dragged from, as the source
  of the next link, or onto, as the place or table a later link writes into —
  rows added to the table link 1 creates.
- **What can be done with it is asked of what the link will make**, since
  nothing may be there to read yet: a CSV file with the columns of the table
  it is saved from, a table with the columns chosen for it, a copy of the file
  or folder carried, with that one's columns — along a chain as far as it
  goes. The same kinds answer as for any row (D164), each given that
  description in place of a node, so the windows for a new table's columns
  and for a pairing open before the first run, on those columns.
- **A link cannot read, however far along, what it makes itself.** Such a
  link is refused when drawn, and says why.
- **The hint** draws links from and into result rows too (D176).

### Running

- **A link reading a result goes after the link making it**, circle or not: a
  circle is never broken at such a link (D177).
- **It reads what was made in this run**, under the name it was made with —
  `orders (2).csv` when Keep both renamed it. When the link making it made
  nothing in this run, it is not run: it never reads what an earlier run
  left.
- **Each step keeps what it made**, so the panel of a link reading a result
  and the footer's list say which one it read.
- Before anything runs, a link from or into a result is checked for its
  choices as any link is (D177).

## Out of scope

- Transformations on the way: a result is what the operation makes, as it
  makes it.
- One link per file of a folder, "for each": a folder carried is one result.
- Schedules and triggers; a history of runs beyond the last.

## Known deviations, accepted with it

- **What is said ahead is checked again when the step runs.** A table changed
  since the link was drawn, a name taken meanwhile, a file too large: the
  step fails with its sentence, as any step does (D177).
- **A result row is not checked against the connection**: whether the object
  is there now is the last run's to say.
- **A move's source is struck out after the run**, as any node gone is
  (D175); the result row of the move is where it went.

## Acceptance

- A table saved as CSV into a folder shows "orders.csv ← 1" on the folder's
  card; a Copy link drawn from it to a folder of an SSH server runs after it
  in the same Run and copies the file just made.
- With Keep both and the name taken, the file made is renamed, and the copy
  link copies the renamed file, not the old one.
- A CSV result linked into a schema offers "Create a table", and its window
  opens on the source table's columns before any run.
- Rows are added to a table another link of the same run creates.
- The link making a result taken away: its row and the links using it go,
  after a confirmation naming them.
- Two links each reading, however far along, what the other makes are
  refused.
- The link making a result failing: the link reading it is not run.

Tests cover the result row of each kind and its name, what a result is asked
as — a CSV's columns from its table, a table's from its choices, along a
chain — the refusal of a link reading its own result, the order and the node
read at run time, a renamed result, a result not made, and in the browser a
chain drawn before the first run and run by one Run.

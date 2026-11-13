# Pipelines

A pipeline lays your connections out on a canvas and draws links between what
they hold: rows of a table copied into another table, a table saved as a CSV
file in a folder, a topic read on into a table, and so on. Switched on, it runs
by itself: a link that reads a topic, a queue or a stream carries what arrives
within seconds, and the other links run on a schedule. It can also be run once
by hand.

Pipelines are in the **Pipelines** space of the switch at the top of the left
rail. A pipeline is yours alone: it is not shared.

## Making a pipeline

1. **Create a pipeline**, or **New** beside the pipeline switcher in the head.
   It is named for you; the pencil renames it.
2. Drag a connection from the list on the left onto the canvas, or press it.
   A window of its catalog opens with ticks.
3. Tick what the pipeline takes from it — tables, files, topics, keys — or a
   place for things to arrive in: a schema, a folder, the top of your storage.
   Ticks are kept when you walk into another level.
4. **Place on the canvas**. What was ticked becomes a card: the connection in
   its head, a row for each thing ticked.

A connection may be several cards. A card is moved by hand. The gear in its
head, or a double click, opens the window again to change what it holds; its
cross takes it off the pipeline. Nothing in the connection itself changes.

A card whose connection is gone, no longer shared with you or switched off is
dashed and says so. A table that no longer exists is struck out as
"not found".

## Links

- Drag a row of one card onto a row of another. While you drag, every row it
  can go to is tinted, saying what a drop there would do; the others are
  faded, saying why not. Dropping on a tinted row draws the link.
- A link is drawn ready to run where its choices can be guessed: a new table
  is named after what it comes from, with all its columns; columns are paired
  by name; keys come from a topic's key. Its panel changes any of them.
- A link that still lacks a choice is drawn in the caution colour, saying what
  it needs. The line under the canvas names it, and **Choose** opens it.
- Both ends of a link must be in different connections: within one connection,
  use **Copy** and **Paste** in its catalog.

Selecting a link opens its panel below the canvas: what it does, a choice of
**Operation** when several fit, and that operation's own choices — a **File
name** and what to do **If the name is taken** (**Stop and say so**,
**Keep both**, **Replace it**), the table to write into and how its columns
pair with the rows', or the columns of **A new table**. A link that writes
into keys of Redis is set up under **Key and values**: which column names each
key, what to put before it, and how long a key lives.

Each link is numbered in the order it runs. A link waits for every link that
writes into the card it reads from.

## Switching on

**Switch on**, in the head, saves the pipeline and starts it. A link that
reads a topic, a queue or a stream runs continuously: it carries what arrives
within seconds. Every other link runs on the schedule. **Switch off** stops
both.

- Switch on refuses before anything starts when a link lacks a choice, and
  opens that link; when links run on the schedule and none is set, it opens
  **Schedule…**.
- The line under the canvas says what the pipeline needs or does: what
  switching on will do, how long it has been on and when it last carried
  something, when the schedule comes next, or a link that keeps failing.
- A link that reads on can run on the schedule instead: **While the pipeline
  is on** in its panel. **First run reads** chooses **From the earliest
  available** or **Only what is new**; afterwards the link reads on from where
  it stopped.
- While it is on, the activity bell shows how many messages were carried, and
  a link that keeps failing is listed under **Needs you**. Stopping it there
  switches the pipeline off.

## Running once

- **Run once now**, in the menu beside **Switch on**, saves the pipeline and
  runs every link once, one after another. It refuses before anything runs
  when a link still lacks a choice, and opens that link. While the pipeline is
  on, the links that run continuously are left out.
- The first link that fails stops the run; the links after it are not run.
- While it runs, each link says **Waiting**, **Running**, **Done** or
  **Failed**, and the run is in the activity bell, where it can be stopped.
  Stopping ends the link in hand; the ones after it do not run.
- Whatever moves through a link runs with your access as it is at that moment.
  A connection you can no longer reach fails its link.

## Schedule

**Schedule…**, in the menu beside **Switch on**, sets when the scheduled links
run while the pipeline is on: either **Every so long** — a number of minutes,
hours or days — or **At times of the day**, on the days ticked. Times are the
clock of the browser that saved the schedule. The line under the canvas shows
the next run.

## History

**History**, in the **⋯** menu of the head, lists every run, newest first: when
it started, whether by hand or by the schedule, how long it took and what each
link did. Choosing a run shows it on the canvas; **Back to the last run**
returns.

## Limits

- 100 pipelines a person, 50 cards a pipeline, 100 rows a card, 200 links a
  pipeline.
- Deleting a pipeline removes its cards and history. Nothing in the
  connections changes.

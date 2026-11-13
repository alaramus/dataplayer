# Pipelines

A pipeline lays your connections out on a canvas and draws links between what
they hold: rows of a table copied into another table, a table saved as a CSV
file in a folder, a topic read on into a table, and so on. A pipeline runs when
you press **Run**, on a schedule, or — for a link that reads a topic or a queue
— continuously.

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

- Drag a row of one card onto a row of another. If something can go from one
  to the other, a link is drawn; if not, it says why.
- **Show the links that could be drawn**, in the head, draws dashed every link
  that could be made between the rows on the canvas, labelled by what it would
  do. Pressing a dashed link draws it.
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

## Running

- **Run** saves the pipeline and runs every link, one after another. It
  refuses before anything runs when a link still lacks a choice, and opens that
  link.
- The first link that fails stops the run; the links after it are not run.
- While it runs, each link says **Waiting**, **Running**, **Done** or
  **Failed**, and the run is in the activity bell, where it can be stopped.
  Stopping ends the link in hand; the ones after it do not run.
- Whatever moves through a link runs with your access as it is at that moment.
  A connection you can no longer reach fails its link.

## Schedule

The clock in the head opens **Schedule**: **Run by itself**, then either
**Every so long** — a number of minutes, hours or days — or **At times of the
day**, on the days ticked. Times are the clock of the browser that saved the
schedule. The head shows the next run.

## Following a topic or a queue

A link that reads a Kafka topic, a RabbitMQ stream or queue, or another source
of messages can be marked **Follow** in its panel. **First run reads**
chooses **From the earliest available** or **Only what is new**; afterwards the
link reads on from where it stopped.

The **Follow** switch in the head then carries what arrives within seconds,
until it is switched off. While following, the activity bell shows how many
messages were carried, and a link that keeps failing is listed under
**Needs you**.

## History

**History**, in the head, lists every run, newest first: when it started,
whether by hand or by the schedule, how long it took and what each link did.
Choosing a run shows it on the canvas; **Back to the last run** returns.

## Limits

- 100 pipelines a person, 50 cards a pipeline, 100 rows a card, 200 links a
  pipeline.
- Deleting a pipeline removes its cards and history. Nothing in the
  connections changes.

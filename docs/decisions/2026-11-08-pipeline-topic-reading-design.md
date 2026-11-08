# A topic read by a pipeline's link, only what is new

Decision D312. The second stage of the Kafka roadmap: a topic in the middle of
a pipeline. Writing into a topic already works — a topic takes rows as new
messages (D308), so Add rows into one needs nothing new. This is the way back
out: a link that reads from a topic only what arrived since its last run, and
remembers where it stopped, so that a schedule (D179) can run it again and
again.

The aim is a topic as a distribution centre: one source writes into it, and
several links read from it into several places, each at its own pace.

## Why Add rows from a topic is not enough

A topic is a source of rows (D306), so Add rows from one can be drawn today.
It does not serve a schedule:

- **Every run reads the whole topic again**, so the table gains the same rows
  each time.
- **It reads newest first, by offset.** The rows are paged by offset
  (`imports.carry_rows`), and a topic's page refuses past ten thousand
  messages deep (D306), so a larger topic fails the step. While messages
  arrive, the pages shift under the reader: some rows come twice, some never.

Paste in the catalog keeps its kinds: there a person copies what they see,
once. In a pipeline a topic is offered the new kind instead (below).

## A kind of its own: Add new messages

A new kind in the paste registry (D164), `rows_since_last`, titled "Add new
messages to a table". It writes as Add rows does — into a table that is
there, or one an earlier link of the chain makes (D178), with the columns
paired in the same window — and reads differently: only what arrived since
the last run of this link.

- **Pipelines only.** It is not offered by Paste in the catalog: "since the
  last run" means nothing to a paste made once. The registry gains a flag for
  a kind that only a link may be, beside `pipelines`.
- **Matched by a capability, not by Kafka.** The source must implement
  `SupportsReadingOn` (below); Kafka is the first to. A source that adds it
  later takes part with no change to the kind.
- **In a pipeline, a node that can be read on is offered only this kind** of
  the kinds that read rows: Add rows, Create a table and Save as CSV are left
  out for it, and so is the hint's dashed link for them (D176). A link of
  those kinds drawn from a topic before this change stays and runs as it did.
- **It makes nothing** (`made` is None), as Add rows makes nothing.
- **Read access to the topic's connection is enough**, and write access to
  the table's, as for Add rows. Keeping a position is what every Kafka
  reader does; it changes no message.
- **It always runs as a transfer** (`PastesAsJob`): it takes a transfer slot,
  reports rows as they arrive, and stops between blocks on Stop (D168).

## The capability: reading on from a bookmark

`SupportsReadingOn`, a `runtime_checkable` Protocol, says three things:

- **whether a node can be read on**: a topic can; Kafka's own topics and a
  consumer group cannot;
- **the span still unread for a reader**: from the reader's bookmark to the
  end as it stands now, with how much is in it and how much was lost before
  it was read;
- **a block of that span, as rows of the paired columns, and a bookmark
  after it**, which the kind confirms once the block is written.

A reader is named by the kind: one link, one reader.

## Kafka's reader is a consumer group of the link's own

- **The group is `dataplayer-link-<link id>`**, made by the first run. One
  group a link is what makes the topic a distribution centre: three links
  reading one topic into three places move on independently, and a slow or
  failed one holds back nobody else. The group is shown in the catalog with
  the others (D305), its lag included, so how far a link is behind is read
  where groups are read. The panel names it.
- **Partitions are assigned, never subscribed**, as a page reads them (D306):
  the group never has members, so no rebalance runs and Kafka's own rule
  that a group with consumers cannot have its positions moved never stops a
  run. Positions are read and written by the admin client
  (`list_consumer_group_offsets`, and `commit_positions` of D309, which reads
  every partition's own answer).
- **A step draws a line first**: the end of each partition when it starts.
  It reads from the group's position up to that line and no further, so it
  ends while messages keep arriving; what arrives meanwhile is the next run's.
- **It reads in blocks of five thousand rows**, as a transfer of rows does
  (D43). A block is written into the table in one transaction, and then the
  group's positions move past the block's last message in each partition.
- **Every run writes the positions, even when nothing was new.** Kafka
  forgets the positions of a group without members some time after they
  were last written (`offsets.retention.minutes`, seven days by default); a
  pipeline that runs at least that often never loses them.
- **Each message's row is built from the paired columns**, the same columns
  a page has (partition, offset, timestamp, key, value, headers and
  `value.<field>`). A paired field a message does not have is empty, so the
  reading does not depend on the sample a page's columns come from.
- **A partition added since the last run is read from its start.**

### Where the first run starts

The panel offers two starts:

- **From the beginning of the topic** (the default): the first run reads
  everything Kafka still keeps.
- **Only new messages**: the first run reads nothing and puts the group at
  the end; the second reads what came after the first.

The choice matters only while the group has no positions: once it has,
changing it changes nothing, and the panel says so. To read again from an
earlier point, the group's positions are moved in the catalog (Move
positions, D309); a link adds nothing for it.

### What a step says

"1,240 new messages added to orders", "Nothing new since the last run", or
with a loss: "1,240 new messages added to orders; 120 were deleted by Kafka
before they were read". A loss is a position older than the start of its
partition — Kafka deleted those messages by retention or by Delete messages
(D309) — and reading goes on from that start. When the group has no
positions — the first run, or Kafka forgot them — the step says no position
was kept and where it started from; it cannot tell the two apart.

## What it guarantees

**Every message at least once.** A block is written and then its positions
move; a failure or a Stop between the two leaves the block to be read again
by the next run, so that block's rows arrive twice. Nothing is skipped
except what Kafka deleted, and that is said. Exactly once would need a
transaction spanning the table and the group's positions, which two
different systems do not share; it is left for later.

Rejected:

- **A group named by the person**, or an existing group chosen: a group
  with consumers refuses moved positions, and two links sharing a group
  would each take part of what the other needed. The name is the link's.
- **Deleting the group with its link.** Kafka forgets a group without
  members by itself, and a link taken off by mistake and drawn again would
  otherwise start over.
- **A ceiling per run** with the rest left for the next run: the line drawn
  at the start already ends the step, and Stop works between blocks.
- **A cursor kept in DataPlayer's database** instead of the group: the
  group is where Kafka's own tools, its metrics (D310) and the catalog look
  for a reader's position, and it survives the pipeline being copied by
  hand to another server.

## Known deviations

- **A block can arrive twice** after a failure or a Stop between writing it
  and moving the positions.
- **Positions are lost after Kafka's retention for groups** if a link runs
  less often than that (seven days by default); the next run starts where
  the panel's choice says, and its sentence says so.
- **The start choice is not a moment in time**: "Only new messages" means
  from the first run, not from when the link was drawn.

## Out of this stage

- The latest value per key into Redis: a replacing write, not an added row,
  and a kind of its own.
- Links that run all the time rather than on a schedule.
- A Binance source.

## Where it lands

- `connectors/paste/`: the kind, the flag for a link-only kind, the refusal
  of the other row kinds for a node read on in a pipeline's offers.
- `adapters/protocol.py`: `SupportsReadingOn`.
- `adapters/kafka/`: the reader by consumer group.
- The link's body: the start choice. The panel: the choice, the group's name
  and the step's sentence. Locales for every new string.
- Documentation: D312 in `pipelines.md`, a paragraph on the reader in
  `sources/kafka.md`, the registry row in `AGENTS.md`.
- Tests: two runs read only what is new; a block written but not confirmed
  arrives again; a position behind the partition's start is counted as lost;
  a new partition is read from its start; both starts; Add rows, Create a
  table and Save as CSV not offered from a topic in a pipeline but still
  offered by Paste; the kind refused where the source cannot read on. A
  Playwright scenario: topic to table on a canvas, run twice, the second run
  adding only what was sent between.

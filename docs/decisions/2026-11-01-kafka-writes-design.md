# Writing to Kafka: messages, topics and groups

Decisions D308 and D309. The third slice of the Kafka source: what the user
chose to change in the first version — sending a message; making, deleting
and changing a topic and adding partitions; moving a consumer group's
positions; deleting the records before an offset.

## A message is a new row (D308)

Kafka appends and never changes, so of the grid's three edits only insert
means anything: a message is sent as a new row. It goes through the grid's
own insert, not a form of its own, for two reasons. A screen that already
knows how to add a row needs nothing new; and the same capability takes a
block of rows, so pasting rows into a topic and a pipeline's "Add rows" link
into a topic (D166, D177) work with no code of their own — the first step
towards the topic in the middle of a pipeline that started this source.

The columns that may be filled are partition (empty leaves it to the
partitioner, by key), timestamp (empty is now), key, value and headers, and
the `value.<field>` columns: when value is left empty and fields are given,
the value is a JSON object of them, each read as its column's JSON type, so
rows copied out of a table become JSON messages. A key or a value written as
`0x` and hex digits is those bytes — the form they are shown in — and
anything else is its UTF-8 text. Headers are a JSON object of text.

A block is read whole before anything is sent: a value that will not read
rejects the block with the cells named. It is then sent by an idempotent
producer and waited for. Rejected: a transaction around the block, which
would make it all or nothing at the broker as well — it needs a cluster with
transactions and a permission on a transactional id that a person browsing a
cluster seldom holds, and a source that worked on one cluster and not on the
next would be worse than the deviation below.

## Topics and groups are changed by actions with previews (D309)

On the Topics level:

- **New topic** — a name in Kafka's characters, partitions, a replication
  factor or the broker's default, and settings as `name=value` lines, the
  form `kafka-configs.sh` and every document about Kafka use.
- **Delete topic** — several at once; the preview says how many messages go
  and which groups read the topic.
- **Change settings** — the settings made on the topic, opened with what it
  has; a line removed returns the setting to the broker's default. The
  preview lists what is set and what returns to the default. Changed one by
  one with Kafka's incremental call, so a setting nobody named stays.
- **Add partitions** — a new total, larger than now; the preview warns that a
  key may land on a different partition from then on.
- **Delete records** — everything, or everything before a time, in each
  partition; the preview counts what goes per partition. Kafka cannot undo it.

On the Consumer groups level:

- **Move positions** — to the start, the end or a time, for every topic the
  group has positions in or for one of them; refused while the group has
  consumers, which Kafka would refuse too. The preview shows each partition's
  position now and after, and the lag after.

Deleting a group was not asked for and is not offered. Internal topics take
no action: they are Kafka's own.

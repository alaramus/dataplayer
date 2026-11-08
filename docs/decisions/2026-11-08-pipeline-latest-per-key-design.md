# The latest value per key, kept in Redis by a pipeline's link

Decision D314. The third piece of the topic as a distribution centre (D312,
D313): where a table keeps every message, a cache keeps only the newest one
for each key — the last price of each symbol, the last state of each sensor —
and lets the old ones expire.

## What there was

A Redis hash takes a row as `HSET`, which replaces the field's value, so D312's
link into a hash already keeps the newest value per field. Three things stood
in the way of using it as a cache:

- **The hash had to exist** before it could be ticked on a card.
- **Redis has no empty value**: one message without a key rejected its whole
  block, and the step failed.
- **The usual shape of a cache is a key per thing** — `price:BTC`,
  `price:ETH` — often with a time to live, and nothing wrote that.

## A link-only kind: Keep the latest per key

`rows_by_key`, titled "Keep the latest per key", drawn to a Redis database or
folder. Like D312's kinds it is a link's only: Paste in the catalog does not
offer it.

**Its window** (a workflow of its own, `keyed`) asks:

- **the key column** — whose value names the key; for a topic its `key`;
- **the prefix** — put before that value, starting as the folder's path
  (`price:` for a link drawn to the folder `price:`), empty for a database,
  and editable, since a folder that does not exist yet cannot be ticked;
- **what the key holds** — one column is a string (`SET`); several are a hash
  whose fields are named as the window names them (`HSET`). It starts with
  the topic's `value.<field>` columns as a hash when there are any, and its
  `value` as a string otherwise;
- **how long a key lives** — none, or a number of seconds from one to a year.

**Each row replaces its key whole**, in one transaction with the time to live:
a hash loses the fields the new row does not have, and a key's life starts
again at every write. Within a block only the last row for each key is
written, so a block of a thousand ticks for ten symbols is ten writes.

- **A row whose key is empty is skipped and counted**, never the reason a run
  fails. In a hash a field whose value is empty is left out; a string whose
  value is empty is skipped and counted with them.
- **A key that holds another type is left as it is and counted**: a list
  under `price:BTC` is somebody's, and replacing it because its name matched
  would destroy it. The check and the write are one script on the server, so
  nothing comes between them.
- **A value longer than a key may hold here** (64 KB, the editor's own bound)
  fails the step, naming the key, as the grid refuses it.

The step says what it did: "1,240 rows: 12 keys written under price:", with
"; 3 rows without a key skipped" and "; 1 key of another type left as it
was" when there were any.

## Where the rows come from

**Any source of rows in a pipeline.** Writing a key is the same whether it
happens once or twice, so a table read whole at every run is a fair source
for a cache, and the link needs no bookmark to be right.

**From a node read on (D312) it reads only what is new**, through the same
consumer group of its own, the same span and blocks, the same start choice in
the panel; the bookmark is kept after each block is written. A failure
between writing and keeping writes the block again, which changes nothing.

The panel shows the reader and the start choice where the source reads on,
and not otherwise: an offer says whether its source is read on (`reads_on`),
so the screen asks it rather than the kind. That holds for D312's and D313's
kinds as well.

## The capability

`SupportsKeyedWrite.write_keyed`: a place, a prefix, the rows with their key
and values as named, the time to live; it answers the keys written, the rows
without a key and the keys of another type. Redis implements it with a Lua
script per block. A SQL table could implement it as `INSERT … ON CONFLICT DO
UPDATE` by a chosen key; that is a later step, and when it comes the kind
needs nothing new.

## Known deviations

- **From a table, which row wins** among several for one key is the order the
  source pages in; from a topic it is the newest when the producer keys by the
  partitioner, which keeps a key in one partition read in order. A key sent to
  several partitions is won by the partition read last.
- **A key written by hand under the prefix is overwritten** when a row names
  it, if it holds the same type.
- **Keys are never removed** by the link: a thing that stops arriving keeps
  its last value until its time to live ends.

## Where it lands

- `connectors/paste/`: the kind, sharing D312's reading; `reads_on` on an
  offer.
- `adapters/protocol.py`: `SupportsKeyedWrite`; `adapters/redis/`: the script.
- The link's body: key column, prefix, values, time to live. The panel: the
  `keyed` window. Locales.
- Documentation: D314 in `pipelines.md`; the Redis guide page and the Kafka
  guide's pipeline section in every language.
- Tests: keys per row with a prefix, a string and a hash, the last row per key
  in a block, a hash losing fields, a time to live set, rows without a key
  skipped, a key of another type left alone, a value too long; a topic read on
  twice writing only what is new; a table source read whole; the panel's
  window. A Playwright scenario: a topic into Redis keys by a pipeline.

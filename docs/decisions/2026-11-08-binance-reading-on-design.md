# Binance read on by a pipeline's link

Decision D319. The second slice of the Binance source (D316–D318): a
symbol's trades and its candles of one interval read on from where a link
stopped, so the pipeline kinds that read on (D312–D314) and following
(D315) carry a market into the user's own stores. On the branch
`binance-adapter`.

## What is read on

- **Trades** (`…:trades`): aggregated trades by id. Ids follow each other
  without gaps, so the span is exact: from the bookmark to the newest id now.
- **Candles of an interval** (`…:candles:1h`): closed candles by open time.
  The candle still open is never read: it changes until it closes, and a
  link that took it would keep a price that was never final. The span ends
  at the last closed candle's open time.
- **Nothing else**: Tickers, Symbols and the order book are a state at a
  moment, not a log; a link takes them whole each run, as Add rows does.
  `reads_on` answers false for them, and their offers stay as they are.

The bookmark has one part, keyed `""`: a symbol's trades or candles are one
series, not partitions. Its position is the next aggregated id, or the next
candle's open time in milliseconds.

## Where the bookmark is kept

Kafka keeps a reader's position itself, in a consumer group (D312). Binance
keeps nothing for anybody, so DataPlayer keeps it:

- **A table `reading_bookmark`**: the connection, the node id, the reader's
  name, the bookmark as JSON and when it was written; one row per connection,
  node and reader; deleted with the connection. Written into the squashed
  baseline, as every new table is.
- **The adapter is handed a store**, as it is handed keys and tunnels
  (D146, D282): `AdapterContext.bookmarks`, a protocol in the adapters' layer
  that reads and writes a bookmark by node and reader for this connection,
  implemented above it over the database. A driver never reaches for the
  database itself; a draft and a check get none, and reading on without one
  is refused.
- **Deleting a link leaves its bookmark**, as Kafka keeps a deleted link's
  group until it forgets it. A bookmark is a few bytes, and a link drawn
  again under the same id does not exist; nothing reads a row nobody names.
  Removing them is cleanup for later, not a correctness question.

## Reading

- **Where a fresh reader starts** (the link's `start`): `latest` is the end
  now — the newest id plus one, or the open time after the last closed
  candle. `earliest` is not "everything Binance keeps", which is two years
  of trades and every candle since a symbol was listed: it is the last
  24 hours. A link meaning more fills the table first with a transfer or
  a query and then reads on.
- **Blocks**: one request a block, 1,000 trades or 1,000 candles on spot,
  1,000 and 1,500 on futures, within the step's block of 5,000 (D43) as
  several requests. The rows have the columns the grid shows (D318), so a
  link's pairing of columns is the same as a page's.
- **Lost**: a bookmark older than what Binance still keeps answers from
  its oldest; the ids skipped are counted as lost and said in the step's
  sentence, as a Kafka gap is.
- **Each block's bookmark is kept after it is written**, as D312 says: at
  least once. A table made by the link (D313) keys trades by id and candles
  by open time, so a block written twice arrives once.

## The rate limit while following

Following (D315) asks every marked link's span every two seconds. A span is
one request of weight 2 (the newest aggregated trade, or the last two
candles); a block of trades 4, of candles 2. With the 80% ceiling of D316 a
spot connection stays under it with about 150 trade links followed at once,
far beyond the three followers a person may run. A link refused by the
ceiling fails as any link does and is retried with D315's backoff, its
sentence saying the limit was reached.

## Known deviations, expected

- **The last 24 hours, not everything**, for `earliest`.
- **A candle is taken once it closes**: a 1d link lags by up to a day by
  design, and its sentence says nothing new until one closes.
- **Seconds, not milliseconds**: polling REST, as following does for Kafka.
  Binance's WebSocket is for the market view later, not for this.

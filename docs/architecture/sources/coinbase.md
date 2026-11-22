# Coinbase Exchange

For changing how Coinbase Exchange is reached and kept under its rate limit,
what its catalog shows of its spot products, how its feeds are read as rows,
how a link reads them on and a product is watched live, or what the
connection reports, measures and finds. What Coinbase shares with every
exchange is in [market.md](market.md); the contract every source keeps is in
[contract.md](contract.md).

Decisions here: D438, D439, D440, D441, D442.

## D438. Coinbase Exchange's public market data over REST, one budget for the address

- **Nothing changed on Coinbase.** The connection names an endpoint from a
  closed set: Coinbase Exchange (`api.exchange.coinbase.com`, its feed on
  `ws-feed.exchange.coinbase.com`) and the public sandbox
  (`api-public.sandbox.exchange.coinbase.com`). No key in this round.
- **One client a connection** on the shared session (D425): the product
  list kept an hour, the tickers ten seconds.
- **One budget for the address**: Coinbase allows ten public requests a
  second (bursts to fifteen) and sends no count, so `Kept.address` holds a
  limit of ten in windows of a second at a share of 40%, and a request over
  it waits for the next second (`paces`, D432).
- **Numbers as written.** Candles and the clock are JSON numbers; the body
  is parsed with every non-whole number kept as its text, never a float.
- **Failures are kinds.** 429 holds the address a second; 403 is `config`;
  404 on a node is that node not found — the product was checked against
  the list first; 5xx is `network`; anything else is "Coinbase refused the
  request" with the status. The message Coinbase sends is never passed on.

Known deviations:

- **The limit is Coinbase's documented one**, not read from Coinbase.
- **Tests run against a fake** (`tests/adapters/coinbase_fixture.py`), as
  every exchange's do.

Spec: [A Coinbase Exchange source](../../decisions/2026-11-22-coinbase-source-design.md)

## D439. One spot market, its feeds as rows of one meaning

- **One market**, `spot`, in the shared catalog: Tickers, Symbols, a folder
  per quote asset, products that are `online` and not disabled.
- **Tickers** are `products/stats`, every product's day in one request:
  last, change and its percent from the day's open (the shared
  `percent_change`, three places), open, high, low and volume. Coinbase
  gives no quote volume, so the column is left out and the busiest are by
  volume.
- **Symbols** say base, quote, status, price step (`quote_increment`),
  quantity step (`base_increment`) and minimum notional
  (`min_market_funds`).
- **Candles**: intervals `1m 5m 15m 1h 6h 1d`, Coinbase's only
  granularities; spans of at most 300 between `start` and `end`, both
  included; `closed` when the interval has ended. Coinbase publishes no
  candle for an interval without a trade, so twenty empty spans end a read.
  No quote volume, trade count or taker volumes.
- **Trades by id**: Coinbase numbers a product's trades from one and keeps
  them all; `after` an id answers up to a thousand before it. A page is a
  span of ids. `side` is the maker's, so `buyer_is_maker` is a `buy`.
- **The book** is `level=2`, the whole aggregated book, cut to the asked
  depth, up to 1,000 a side.

Known deviations:

- **A trade's time is not a filter**: Coinbase has nothing to find a trade
  by its time.
- **Candles oldest first without a filter** start the page's depth back
  from now: Coinbase has no way to ask for its oldest candle.

Spec: [A Coinbase Exchange source](../../decisions/2026-11-22-coinbase-source-design.md)

## D440. Candles and trades read on, nothing lost

- **`SupportsReadingOn`** for a product's trades and candle series
  (`coinbase/reading.py`), the bookmark kept by DataPlayer (D319).
- **Trades by id**: `""` the next id, the line the newest plus one, a block
  a span of ids; Coinbase keeps every trade, so nothing is ever lost. A
  fresh reader's `earliest` is the newest thousand.
- **Candles by open time**: the line is the open of the interval under way,
  from the clock rather than an answer, since a quiet interval has no
  candle; a block is one span of up to 300. `earliest` is the last day.

Spec: [A Coinbase Exchange source](../../decisions/2026-11-22-coinbase-source-design.md)

## D441. A product's market watched live from the public feed

- **The shared watch** (D323, D425). One socket a product, subscribed to
  `matches`, `level2_batch` (the book's public channel; `level2` needs a
  key), `ticker` and `heartbeat`.
- **The snapshot over REST**: the day's stats, 300 candles, the whole book
  and the newest hundred trades.
- **The candle still open is kept from the trades**: Coinbase streams no
  candles, so each match is laid over the newest candle, or opens the next.
- **The book** from the REST snapshot, the feed's `snapshot` and
  `l2update` changes laid over it, twenty levels a side at most four times a
  second. Trades the snapshot held are left out by id.

Known deviations:

- **The live candle can differ a little from Coinbase's own** until it is
  read again over REST: a trade between the candles' read and the trades'
  read is in neither.

Spec: [A Coinbase Exchange source](../../decisions/2026-11-22-coinbase-source-design.md)

## D442. The Exchange section, metrics, symbols found

- **Exchange** (`coinbase/reports.py`) is the shared section: **Status**
  (no system status on public paths), **Clock** (`/time`), **Rate limit**
  (one budget, said once, in seconds), **Markets**.
- **Metrics**: `weight` labelled `address`, `latency` and `reachable`; the
  preset is `coinbase-connection`. **Search** and the **Markets** folder are
  the shared ones.

Spec: [A Coinbase Exchange source](../../decisions/2026-11-22-coinbase-source-design.md)

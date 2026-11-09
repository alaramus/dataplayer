# A symbol's market, watched live

Decision D323. The view D316 left for later: a symbol's chart, order book and
tape on one screen, moving as the market does. The Binance source (D316–D322)
already reads each of them as rows; this is how they are watched together.

## Where it is opened

Every symbol holds a first node, **Market**, a `feed` whose only
representation is a new kind, `market` (D47). Opening it opens a tab of its
own, as a PDF or a definition does.

Rejected: the representation on the symbol node itself. A symbol is a
container — clicking it walks into Candles, Trades and Order book — and a
node that opens and also holds nodes is a workbook (D51), which would take
the walk away. A node of its own keeps both gestures.

## What travels, and how

The view is rows. A watch is told, part by part, in the columns the grid
already shows for the same feeds:

- `ticker` — the symbol's day, replaced as it changes;
- `candles` — three hundred at the chosen interval, then the open one
  updated by `open_time`;
- `order_book` — twenty levels a side, replaced;
- `trades` — the last hundred, then each new one added.

`app/adapters/live.py` states this as a capability, `SupportsLive`: a
`live_start` that refuses before anything is sent, and a `live` generator of
`LiveRows` (`part`, `mode` of `replace`, `append` or `upsert`, `columns`,
`rows`, `key`). The capability says nothing of sockets or of Binance.

### A socket of its own

`/api/v1/watch`, in `app/connectors/watch.py`. It opens unauthenticated, its
first frame carries the token, the connection, the node and the interval,
and it answers `ready` with the intervals the node offers, then `rows` until
the client goes, or `refused` / `ended` in words. Read access is enough
(`requires="read"`), as for any read of the source. A new interval is a new
socket.

Rejected: a topic of the application's socket. A topic is a name and takes
no arguments (D18), and D127 already kept arguments off the subscribe frame
for the transport every topic shares. A watch is of one node at one
interval; a terminal (D148) is the precedent for a socket of its own.

The client (`features/market/watchLink.ts`) opens a lost watch again, with a
growing delay. Unlike a terminal's, a new watch loses nothing: it starts with
the node as it stands. A refusal or an explained end is not retried.

## Binance

What a watch first says is read over REST, as the grid reads it: the day,
three hundred candles, twenty levels, a hundred trades — about thirteen
weight on spot. What changes after comes from Binance's market streams,
which cost no weight at all: `aggTrade`, `depth20` (every second on spot,
every half second on futures), `kline_<interval>` and `ticker`.

**One upstream socket per stream address and connection**, kept with the
connection's client in the resource store (D316) as a `MarketStream`. The
first watcher starts it, every watcher has a queue of its own, and the last
one to leave stops it. Two tabs on BTCUSDT at one minute are one socket to
Binance. A watcher that falls behind loses the oldest batches first: a book
or a candle is replaced by the next one anyway. A dropped upstream is opened
again after 1, 2, 5, 10, then 30 seconds; a 451 ends every watch of it in
words.

The stream is watched before the snapshot is read, so nothing between them
is missed, and a trade both hold is said once, by its id.

**USDⓈ-M splits its streams.** Its book comes from `/public/stream` and its
trades, candles and day from `/market/stream`; the plain `/stream` still
answers and carries the book alone, which is how this was found when the
slice was written. A USD-M watch holds two upstream sockets into one queue.
Spot and COIN-M take all four streams on one. The testnet answers both
forms.

Stream hosts: `stream.binance.com:9443`, `fstream.binance.com`,
`dstream.binance.com`; the market-data endpoint's spot streams are
`data-stream.binance.vision`; the testnet's `stream.testnet.binance.vision`,
`stream.binancefuture.com`, `dstream.binancefuture.com`.

COIN-M's streams count volume as its REST answers do, under other letters;
they are read into the same columns, base and USD (D321).

`websockets` becomes a direct dependency, imported by the Binance adapter
alone, by the rule every driver follows; an import contract holds it.

## The screen

`features/market/MarketPanel.vue`: the day across the top (last price,
change, high, low, volumes), the interval to choose, then the chart taking
the width — candles over their volume, ECharts, coloured by the theme's
success and error — and beside it the book above the tape. Twelve levels a
side are drawn of the twenty, each with its cumulative depth behind it as a
share of the deepest. Prices are the source's decimals with Binance's
padding taken off, never rounded. The model (`model.ts`) is plain functions:
a part replaced, added to or updated by key, and the chart's, book's and
tape's view of the parts.

## Known deviations

- **The frames are written out twice**, in `app/connectors/watch.py` and in
  `features/market/frames.ts`, for the reason the application's socket gives
  (D18): OpenAPI has no WebSocket channel.
- **A reconnect of the upstream is not a fresh snapshot.** Candles and the
  book are whole again with their next message; trades made while the
  upstream was down are not shown. A watcher's own reconnect does start with
  a snapshot.
- **Every stream lives in the process**, which D124 makes correct.

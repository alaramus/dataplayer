# A Bybit source, and what exchanges share

Decisions D425–D430. The second exchange after Binance (D316–D323, D365), and
the first of several: Coinbase and OKX are expected next. So the second use is
where the shared part of an exchange is cut out of Binance's adapter, rather
than Bybit being a copy of it.

## Facts checked

Against the live API from this machine and Bybit's v5 documentation, on
2026-11-22.

- **Hosts.** `api.bybit.com` and `api.bytick.com` answer the same; the
  testnet is `api-testnet.bybit.com`. Public streams are
  `wss://stream.bybit.com/v5/public/{spot,linear,inverse}` and
  `stream-testnet.bybit.com` for the testnet.
- **Every answer is HTTP 200 with `retCode`**: 0 is success; 10001 is a
  parameter error, an unknown symbol included ("Not supported symbols" on
  spot, "Symbol Is Invalid" on linear); 10006 and 10018 are limits; 10009 is
  a region Bybit does not serve. HTTP 403 is an IP ban (600 requests in five
  seconds) or a United States address; the ban lasts at least ten minutes.
- **No limit headers on public paths.** `X-Bapi-Limit-*` is not sent on
  market data; this application counts its own requests.
- **Categories.** `spot` (507 symbols trading, 26 quote coins), `linear`
  (939: USDT and USDC perpetuals and dated futures such as
  `BTCUSDT-27NOV26`), `inverse` (26, all quoted in USD, perpetuals and
  futures such as `BTCUSDZ26`). `instruments-info` pages linear and inverse
  by `cursor` (at most 1,000 a page); spot answers all at once and ignores
  the cursor. No symbol holds a colon; dated linear futures hold a hyphen.
- **Candles.** `kline`: intervals `1 3 5 15 30 60 120 240 360 720 D W M`, at
  most 1,000 a request, `start` and `end` in milliseconds, newest first. A
  row is start, open, high, low, close, volume, turnover — no close time, no
  trade count, no taker volumes. On inverse `volume` is in USD (contracts of
  1 USD) and `turnover` in the base coin; on spot and linear the reverse.
- **Trades.** `recent-trade` answers the newest trades only: at most 60 on
  spot, 1,000 on linear and inverse, with no cursor, id or time to page by.
  BTCUSDT's linear thousand covered thirty seconds. `execId` is a number as
  text on spot and a UUID on linear; `side` is the taker's.
- **Book.** `orderbook` takes any depth from 1 to 1,000 a side on spot,
  linear and inverse; a side is `b` or `a`.
- **Tickers.** `tickers` with no symbol answers the category. Spot has last,
  high, low, the price 24 hours ago, `price24hPcnt` as a fraction, volume and
  turnover; linear and inverse add funding and open interest. Inverse
  `volume24h` is in USD and `turnover24h` in the base coin.
- **Streams.** One socket a category; a `subscribe` names topics
  (`publicTrade.S`, `orderbook.50.S`, `kline.1.S`, `tickers.S`), and a ping
  `{"op":"ping"}` every 20 seconds keeps it open. The book arrives as a
  snapshot, then deltas (size 0 removes a level), and a new snapshot resets
  it; a linear or inverse ticker is a snapshot, then deltas of the fields
  that changed. A candle message carries `confirm`, true once it closed.

## D425. What exchanges share

`app/adapters/market/` holds what every exchange's market data has in common,
cut from Binance on this second use:

- **Values**: a decimal stays the exchange's text, a time leaves in UTC.
- **The rate limit as a mechanism** (`Budget`): a limit over a window, a
  request's weight, the exchange's own count where it reports one, the 80%
  ceiling, a hold until a ban ends. The numbers stay each exchange's.
- **The session's frame** (`MarketSession`): one client a connection in the
  resource store, each market's budget, the symbol list kept an hour and read
  by one task every asker waits on, the tickers kept ten seconds, a ping of
  every market, the check. An exchange says its hosts, weights, the shape of
  an answer and its refusals, and how a request is signed — the place a key
  goes (D322), empty for Bybit until its key comes.
- **The catalog**: ids, nodes, the Markets folder (D365), the account's
  nodes when a key reads them; `Place` carries the exchange's own market.
- **The columns of a feed**: one name and type for one meaning across
  exchanges. An exchange that has no value for a column leaves the column
  out rather than filling it with nothing.
- **The feeds read the same way**: tickers and symbols as a list read whole,
  the book by depth and side.
- **The Exchange section of reports**, its frame and its four readers
  (status, clock, rate limit, markets), in each exchange's words.
- **Metrics** (weight, latency, reachable) and **search** over the kept
  symbol list.
- **The live view's upstream socket** (`MarketStream`, the only importer of
  `websockets`) with what an exchange says on opening and to keep it alive,
  and the watch's frame: streams first, then the snapshot, then batches.
- **The adapter's frame** (`MarketAdapter`): listing, the path to a node,
  which feed a node reads, an export to its depth, the watch's checks, the
  delegations to reading on.

Each exchange keeps: its options and endpoints, hosts, weights, codes, its
symbols list's shape, how candles and trades are read and paged, its frames,
its reading on, its reports' words, its preset.

Rejected: **a shared layer drawn in advance from Binance alone**, which
would have put Binance's trade ids into it; **a client-agnostic "exchange
SDK"** such as ccxt, which normalises away exactly the volumes D321 keeps
exact, and brings hundreds of exchanges' code for two.

## D426. Bybit over v5 REST, its own count of requests

- **Endpoints**: Bybit (`api.bybit.com`), the same through `api.bytick.com`,
  and the testnet. No key in this round.
- **Requests are counted here**: Bybit sends no count on public paths. The
  limit is 600 in five seconds; the budget's window is five seconds from its
  start and its share is **40%**, so two windows side by side never pass 80%
  of any rolling five seconds. A request weighs 1.
- **Failures are kinds**: `retCode` 10001 on a symbol the list has is a
  refusal in words; 10009 and HTTP 403 for a region are `config` ("choose
  another endpoint"); an HTTP 403 ban holds the connection ten minutes;
  10006/10018 hold it five seconds; 5xx, 10016 and transport failures are
  `network`. Bybit's `retMsg` is not passed on.

## D427. Three markets in the shared catalog, columns with one meaning

- `spot`, `linear`, `inverse` — the ids are Bybit's categories, the titles
  "Spot", "USDT and USDC futures", "Inverse futures".
- **Symbols**: trading only; linear and inverse read page by page by cursor;
  a futures symbol's contract type is Bybit's word, a perpetual's delivery
  empty.
- **Volumes keep one meaning**: `volume` is the base asset's, `quote_volume`
  the quote asset's. On inverse that is Bybit's turnover and volume the
  other way round, exact, as D321 has it for COIN-M.
- **Tickers** fill symbol, last price, price change (last minus the price a
  day ago), its percent (Bybit's fraction times a hundred, exact), open,
  high, low, volume and quote volume.
- **Candles** fill open time, close time (the next candle's open less a
  millisecond, by the calendar for a week and a month), open, high, low,
  close, volume, quote volume and `closed`; they read backwards from a time
  a thousand a request, as Binance's do.
- **Trades** are the newest Bybit answers, read whole and sorted and filtered
  here: `id` is text, `buyer_is_maker` is "the taker sold".
- **The book** is read to the asked depth exactly.

## D428. Candles and trades read on

- **Candles** as Binance's (D319): the bookmark is the next open time, a
  candle is read once it closes.
- **Trades** by time, as Bybit has no id to page by: the bookmark is the time
  of the next trade to read; a block re-reads the millisecond it stopped in
  when cut there, and the made table's key, `id`, keeps a trade once. When
  the oldest trade Bybit answers is newer than the bookmark, the trades in
  between are gone: one is counted lost, as their number is not known.

## D429. A symbol watched live over Bybit's public streams

- One socket a symbol and interval, subscribing to its trades, book of 50,
  candle and ticker, pinged every 20 seconds.
- **The book is kept** from its snapshot and deltas, and sent whole, twenty
  levels a side, as Binance's is. **The ticker is kept** and a delta's fields
  laid over it.
- Trades the snapshot held are left out by time and id.

## D430. Reports, metrics, search and the Markets folder

The shared ones (D425) in Bybit's words; the clock reads `market/time`; there
is no system status on public paths; the preset is `bybit-connection`.

## Not in this round

- **A key and the account**: the second round, through the signing hook.
- **Trade history past the newest thousand**: Bybit publishes daily files
  on `public.bybit.com`, not an API.
- **Regional hosts** (`bybit.tr`, `bybit.kz` …) and **options**.

## Slices

1. The shared layer, Binance on it, its tests unchanged.
2. Bybit's connection, catalog, feeds.
3. Reading on.
4. The live view.
5. Reports, metrics, search, the Markets folder.
6. Documentation and the guide.

# Binance

For changing how Binance is reached, what its catalog shows of markets,
symbols and feeds, how a feed is read as rows, how a pipeline's link reads
trades and candles on, or what the connection reports, measures and finds. The contract every source
keeps is in [contract.md](contract.md).

Decisions here: D316, D317, D318, D319, D320, D321, D322, D323.

## D316. Binance's public market data over REST, one client a connection, under its rate limit

- **Nothing changed on Binance.** Public data needs no key; a key reads its
  account and nothing more (D322). The connection
  names an endpoint from a closed set, each a host for spot, USDⓈ-M and
  COIN-M futures (D321): Binance (`api`/`fapi`/`dapi.binance.com`), the same
  with a key, market data only
  (`data-api.binance.vision` for spot), and the testnet with or without a
  key. Only a key and its secret are secret.
- **httpx, one client a connection** (`binance/session.py`), kept in the
  resource store as `BinanceKept` with what outlives a request: each market's
  weight used this minute, a ban it is under, the symbol list (an hour) and
  the last tickers (ten seconds). A draft and a check get a client of their
  own, closed after them. `trust_env` is off.
- **The rate limit is kept under 80%.** Every answer's
  `X-MBX-USED-WEIGHT-1M` is read; a request whose weight, from Binance's
  published table in `markets.py`, would pass 80% of the market's limit is
  refused unsent, with the seconds left of the minute. A 429 or 418 holds
  the market until `Retry-After`. Nothing is retried by itself. The limit
  itself is read from `exchangeInfo`.
- **Failures are kinds.** An unknown symbol (-1121) is a 404, a 451 is
  `config` ("choose another endpoint"), futures trades older than two days
  (-4166) are a refusal in words, other 4xx are "Binance refused the request"
  with the code, 5xx and transport failures are `network`, a timeout is
  `timeout`. Binance's own text is not passed on.
- **Symbols are checked by membership**, never by a pattern: some are not
  ASCII (`币安人生USDT`), and futures carry delivery suffixes. A symbol named
  by a client is looked up in the kept list before a request is built, and
  goes into a query parameter only.
- `exchangeInfo` is asked with `symbolStatus=TRADING` on spot: unfiltered it
  is 17 MB, most of it symbols that no longer trade.

Known deviations:

- **Binance US is not offered**: it refuses requests from outside the United
  States, and it has no futures.
- **The weight table is copied from Binance's documentation**, so a change
  there is a change here; the header read from every answer corrects the
  count, not the table.
- **Tests run against a fake** (`tests/adapters/binance_fixture.py`): CI's
  address is in the United States, which Binance refuses.

Spec: [A Binance source](../../decisions/2026-11-08-binance-source-design.md)

## D317. Markets, quote assets, symbols and a node per candle interval

```
spot | usdm | coinm                 directory
  :tickers, :symbols                feed
  :quote:USDT …                     directory, fullest first
    :symbol:BTCUSDT                 symbol
      :market                       feed, opened as `market` (D323)
      :candles                      directory
        :candles:1m … :candles:1M   feed, one per interval (no 1s on futures)
      :trades, :book                feed
```

- **`symbol`** is a kind with its base and quote assets and, on futures, its
  contract type. It opens as nothing yet; the market view is meant to be its
  first representation (D47).
- **`feed`** is a kind with which feed it is (`tickers`, `symbols`,
  `candles`, `trades`, `order_book`) and a candle series' interval. It opens
  as rows. Not a `table`: nothing about it can be altered, and its rows are
  named by time or by Binance's ids.
- **A candle interval is a node** so a pipeline's link names the series it
  reads and keeps one bookmark for it.
- Only symbols trading now are listed; a quote asset with none is not shown.

Known deviations:

- **A feed is not describable and has no summary**: its columns are fixed and
  said by every page.

Spec: [A Binance source](../../decisions/2026-11-08-binance-source-design.md)

## D318. Tickers, symbols, candles, trades and the order book as read-only rows

- **Decimals stay Binance's text**, checked to be numbers, never through a
  float; times arrive in milliseconds and leave as moments in UTC.
- **Tickers and Symbols are read whole** (`feeds.py`, `listed_page`) and sort
  and filter here by any column, a number by its value. Tickers leave out
  symbols not trading, open busiest by quote volume, and refresh every ten
  seconds. A perpetual's delivery date, which Binance puts in 2100, is empty.
- **Candles** open newest first and are read a request at a time backwards
  (1,000 on spot, 1,500 on futures); sorting `open_time` ascending reads
  forwards from a time. `open_time` bounds are sent to Binance; no other
  column filters or sorts. `closed` is false for the candle still open.
- **Trades** are aggregated trades, newest first, read by id: ids follow each
  other, so offset N is N ids back. `id` and `time` bound the page; a time is
  turned into an id within the hour beside it, which is all Binance answers
  at once. Ascending starts from the oldest Binance answers: id 0 on spot,
  the first inside the two-day window on futures.
- **The order book** is bids best first, then asks, each with a running
  total. `level` (`lt`, `lte`) sets the depth, rounded up to one Binance
  accepts, 100 by default; `side` keeps one side. It refreshes every five
  seconds.
- **A page reaches at most 10,000 rows** into candles or trades, and an
  export reads to the same depth.
- Nothing is editable, inserted or deleted.

Known deviations:

- **A time with no trade within the hour beside it is refused**, and the
  page asks for an id instead.
- **Futures trades are answered for two days only**; older ids are refused
  in words.

Spec: [A Binance source](../../decisions/2026-11-08-binance-source-design.md)

## D319. Trades and closed candles read on, the bookmark kept here

- **`SupportsReadingOn`** (D312) for a symbol's trades and its candle series,
  nothing else (`binance/reading.py`); `reads_on` answers from the id alone.
- **The bookmark is kept by DataPlayer**: Binance keeps no reader's place.
  `reading_bookmark` holds one row per connection, node and reader, the
  positions as JSON, gone with the connection (`connectors/bookmarks.py`).
  The adapter is handed it as `AdapterContext.bookmarks`, a `BookmarkAccess`
  in the adapters' layer, built by `resolve_source` for a stored connection;
  a source built without it refuses to read on.
- **A bookmark's `""`** is the next aggregated trade id, or the next candle's
  open time; trades add `"time"`, the last one read, so a reader behind what
  Binance answers is checked only then, and the ids skipped are `lost`.
- **The line** is the newest trade id plus one, or the open time of the
  candle still open: a candle is read once it closes.
- **A fresh reader** starts at the line for `latest`; for `earliest`, at the
  first trade of the last hour, or the first candle of the last 24 hours. An
  hour of trades, not a day: BTCUSDT makes close to a million aggregated
  trades a day, which is near a thousand requests and most of a minute's
  limit on the first run.
- **A table a link makes** (D313) is keyed by the trade `id` or the candle
  `open_time` (`row_key`), so a block read twice arrives once.
- **A block is one request**, at most 1,000 trades or one market's candles a
  request; the step asks again until its block is full (D43).

Known deviations:

- **`earliest` is the last hour of trades or the last day of candles**, not
  everything Binance keeps; the spec said a day for both.
- **A symbol with no trade in the last hour starts from now.**
- **A bookmark outlives its link**, as a Kafka link's group does.
- **A month's count is an upper bound**: months are counted as 28 days.

Spec: [Binance read on by a pipeline's link](../../decisions/2026-11-08-binance-reading-on-design.md)

## D320. An Exchange section of reports, the connection's own use as metrics, symbols found from the kept list

- **Exchange** is a report section first at the top (`binance/reports.py`),
  as Kafka's Cluster is (D310), four setting-and-value reports: **Status**
  (the endpoint, `sapi/v1/system/status` on the main host only, each market
  pinged), **Clock** (each market's time against the middle of the request),
  **Rate limit** (each market's limit, the weight used this minute, where
  this connection stops, a hold), **Markets** (symbols trading, quote assets,
  when the list was read).
- **The weight is made current by a ping** in the same client
  (`BinanceSession.pinged`): Binance reports its address's whole minute on
  every answer, so a report or a poll that asked nothing else still says
  what the address used, and a connection built without the resource store,
  as the metrics poller builds one, is not left at nought.
- **Metrics** (`binance/metrics.py`): `weight` used and ceiling, `latency` of
  the ping and `reachable`, per market as the label; the preset
  `binance-connection`. Prices are not metrics: a pipeline's table holds
  them, and a dashboard reads it.
- **Search** (`binance/search.py`) reads the kept symbol list, so it asks
  Binance for nothing new within the hour. A symbol matches by its name, or
  by its base and quote assets at most as a word; within a market or a quote
  asset it keeps to it. `enumerate_names` gives every trading symbol of both
  markets, scoped by market, its full name the name and both assets.

Known deviations:

- **The clock's difference includes the way there and back**, halved.
- **Symbols only are searched**: feeds and quote folders are found by
  walking.

Spec: [Binance's reports, metrics, search and guide](../../decisions/2026-11-08-binance-reports-design.md)

## D321. COIN-M futures, their volumes in the base and quote asset like the rest

- **A third market**, `coinm`, from `dapi.binance.com` under `/dapi/v1` (the
  testnet's `testnet.binancefuture.com`; the market-data endpoint uses the
  main host, as for USDⓈ-M). The limit is 2400 a minute with USDⓈ-M's
  weights, trades go two days back, there are no `1s` candles. Its only quote
  asset is USD.
- **Columns keep one meaning across markets.** Binance counts COIN-M in
  contracts of a whole number of USD (`contractSize`: 100 for BTC, 10 for the
  rest) and gives the base asset's volume beside them. `volume` is that base
  volume and `quote_volume` the contracts times the size, exact; the same for
  a candle's taker volumes. `Market.in_contracts` says which market does
  this, and `feeds.in_quote` is the one conversion.
- The symbols list on COIN-M gains `contract_size`.

Known deviations:

- **A trade's and a book level's `quantity` are contracts.** Their worth in
  the base asset divides by the price, which is not exact, and those rows
  hold one quantity. The guide says so.

Spec: [Binance's COIN-M futures](../../decisions/2026-11-09-binance-coin-m-design.md)

## D322. A key reads its account, signed, and is accepted whatever else it may do

- **A key is an endpoint of its own**: `binance_key` and `testnet_key`, with
  `api_key` and `api_secret` as `SecretStr` (D4, for Redis's reason, D16).
  `HOSTS_OF` maps them to the plain endpoints' hosts.
- **Signed** by `BinanceSession.signed`: `timestamp` from this server's clock
  plus Binance's offset (measured from `time`, kept an hour), `recvWindow`
  10 s, HMAC-SHA256 of the query, the key in `X-MBX-APIKEY`. A `-1021`
  measures the clock again and sends once more — the only request sent
  twice. A refused key is `auth`, in words that name no key.
- **What the key may do** comes from `sapi/v1/account/apiRestrictions`. A key
  that cannot read fails the check; one that can also trade or move money
  passes it, and the check says so. Never refused: nothing changing is sent
  whatever the key allows. The testnet has no such path; its key is tried on
  the spot account. A report **API key** says the flags, on keyed connections.
- **Catalog**: an **Account** folder in each market — Balances, Positions on
  futures, Open orders, and on spot of the main hosts Deposits and
  Withdrawals — and a symbol's **My orders** and **My trades**, all `feed`s.
  A keyless connection has none of them.
- **Rows** (`binance/account.py`): each list read whole and sorted and
  filtered here, empty balances and positions left out, statuses in Binance's
  words, COIN-M's own trades' quote as D321 has it.
- **My trades are read on** by id (D319) and keyed on `id` in a made table.

Known deviations:

- **Orders and own trades of a symbol are one request**, the newest thousand;
  futures answer seven days unless asked.
- **One key for every market**: the testnet's spot and futures keys differ,
  so one of its markets refuses a testnet connection's key.
- **Binance's per-account weight is not counted**, only the address's.

Spec: [A Binance key and the account it reads](../../decisions/2026-11-09-binance-account-design.md)

## D323. A symbol's market watched live, over a socket of its own, from one upstream stream

- **Opened from a node**: a symbol's first child, **Market**, a `feed` whose
  representation is `market` (D47); a symbol stays a container to walk into.
- **Rows, part by part** (`app/adapters/live.py`, `SupportsLive`): `ticker`,
  `candles` (keyed by `open_time`), `order_book`, `trades`, each batch
  replacing, adding to or updating a part, in the grid's own columns.
- **A socket of its own**, `/api/v1/watch` (`app/connectors/watch.py`): the
  first frame says token, connection, node and interval; `ready` with the
  intervals, then `rows`, or `refused` / `ended` in words. Read access is
  enough. A topic takes no arguments (D18, D127); a terminal (D148) is the
  precedent. The client opens a lost watch again; a refusal it does not.
- **Binance**: the snapshot over REST; then `aggTrade`, `depth20`,
  `kline_<interval>` and `ticker` streams, which cost no weight. One
  `MarketStream` per address and connection, kept with the client (D316),
  started by the first watcher and stopped by the last, each watcher with a
  bounded queue. USDⓈ-M's book is on `/public/stream` and the rest on
  `/market/stream`; spot and COIN-M take one socket. `websockets` is imported
  by this adapter alone.

Known deviations:

- **The frames are written out twice**, Python and TypeScript, as D18's are.
- **An upstream reconnect is not a fresh snapshot**: trades made while it was
  down are not shown.

Spec: [A symbol's market, watched live](../../decisions/2026-11-09-binance-market-view-design.md)

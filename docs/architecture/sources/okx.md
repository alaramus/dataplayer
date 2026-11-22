# OKX

For changing how OKX is reached and kept under its limits, what its catalog
shows of spot, linear and inverse contracts, how its feeds are read as rows,
how a link reads them on and a symbol is watched live, or what the connection reports, measures and
finds, and what a key reads of its account. What OKX shares with
every exchange is in [market.md](market.md); the contract every source keeps
is in [contract.md](contract.md).

Decisions here: D432, D433, D434, D435, D436, D437.

## D432. OKX's public market data over v5 REST, each path under its own limit

- **Nothing changed on OKX.** The connection names an endpoint from a closed
  set: OKX (`www.okx.com`, streams on `ws.okx.com`), OKX Europe
  (`eea.okx.com`, `wseea.okx.com`: a market of its own), and demo trading
  (the main host with `x-simulated-trading: 1` on every request, streams on
  `wspap.okx.com`), each with or without a key (D437).
- **One client a connection** on the shared session (D425): the symbol list
  kept an hour, the tickers ten seconds. Every path is whole, `/api/v5/…`.
- **Each path has its own budget.** OKX limits a path, not a market or the
  address: so many requests in two seconds (`time` 10, `tickers` 20,
  `books` 40, `history-candles` 20, `history-trades` 20, `instruments` 20 for
  each instrument type, `system/status` one in five seconds). OKX sends no
  count, so each is counted here, kept in `Kept.budgets` by its path, its
  windows from their start and its share 40%, as Bybit's (D426).
- **A request over the ceiling waits** for the next window (`paces`) instead
  of being refused: a window is two seconds and a deep page of candles is a
  few dozen requests.
- **Failures are kinds.** OKX answers a `code`: 50011, 50013, 50040 and HTTP
  429 hold the path one window; 50121, 51155 and HTTP 403 are `config` (an
  address or region OKX does not serve); 51001 or 51000 on a node is that
  node not found — the symbol was checked against the list first; 50001,
  50004, 50026 and 5xx are `network`; anything else is "OKX refused the
  request" with the code. `msg` is never passed on.
- **Symbols are checked by membership**, never by a pattern.

Known deviations:

- **The limits are OKX's published ones**, not read from OKX.
- **Tests run against a fake** (`tests/adapters/okx_fixture.py`): CI's
  address is in the United States.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

## D433. Spot, linear and inverse in the shared catalog, read as rows of one meaning

```
spot | linear | inverse              directory; contracts by what they count in
  :tickers, :symbols                 feed
  :quote:USDT …                      directory, fullest first
    :symbol:BTC-USDT-SWAP            symbol
      :market                        feed, opened as `market`
      :candles                       directory
        :candles:1s … :candles:1M    feed, one per interval OKX has
      :trades, :book                 feed
```

- **Markets by contract, not by OKX's instrument type**: linear holds OKX's
  linear perpetuals (`SWAP`) and dated futures (`FUTURES`), inverse the
  inverse ones, as Bybit's categories do; each list and the tickers are read
  a type at a time. Only `live` instruments; options are not read. A
  contract's base and quote come from its instrument family (`BTC-USDT`).
- **Intervals** `1s` … `1M`, sent as OKX's; from six hours up the UTC ones
  (`6Hutc`, `1Dutc`, …), as OKX's plain `1D` opens at Hong Kong's midnight.
  No `8h`.
- **Volumes keep one meaning.** A contract's `vol` is contracts; `volCcy`,
  the base coin, is `volume`. Candles carry `volCcyQuote`, the quote asset's,
  as `quote_volume` on every market. Tickers carry none for linear
  contracts, so there the column is left out; on inverse it is the
  contracts times their worth in USD, exact.
- **Tickers** fill symbol, last price, price change and its percent (from
  the day's open: the one division, rounded to three places), open, high,
  low and the volumes. Busiest first by quote volume, or by volume where it
  is left out (the shared `tickers_page`).
- **Symbols** say base, quote, status, price step and quantity step; futures
  add OKX's instrument type (`SWAP`, `FUTURES`), the delivery and the
  listing. A linear contract's quantity step is the lot times the contract's
  worth in the coin; inverse's stays contracts, with `contract_size` beside.
  There is no minimum notional (`symbol_columns_left_out`).
- **Candles** from `history-candles`, 300 a request, newest first by
  `after`; forwards a span between `before` and `after` cut to hold no more
  than asked. `closed` is OKX's `confirm`. Oldest first without a filter
  starts at the symbol's listing.
- **Trades by id**: OKX numbers an instrument's trades one after another from
  one and answers three months of them, 100 a request; a page is a span of
  ids, a time found by OKX (`type=2`). A contract's size is said as what it
  is worth: the coin on linear, USD on inverse, where the column is
  `quote_quantity`.
- **The book** to the asked depth exactly, up to 400 a side; a contract's
  size said as what it is worth.

Known deviations:

- **On inverse the book's quantity is USD**, as Bybit's is: the shared book
  has one quantity column.
- **A ticker has no weighted price, trade count or open and close times, and
  a candle no trade count or taker volumes.**
- **Candles older than a symbol's listing** are reached only by an open
  time filter.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

## D434. Candles and trades read on, trades by their ids

- **`SupportsReadingOn`** (D312) for a symbol's trades and its candle series
  (`okx/reading.py`); the bookmark is kept by DataPlayer, as Binance's and
  Bybit's are (D319, D428).
- **Candles** as Bybit's: `""` is the next candle's open time, the line the
  open time of the candle still open (OKX's `confirm`), a block one request
  of up to 300 over a span cut to hold no more; a fresh reader's `earliest`
  is the last day.
- **Trades by id**: `""` is the id of the next trade to read, the line the
  newest id plus one, a block a span of ids. A fresh reader's `earliest` is
  the last hour of trades.
- **Lost trades are counted exactly.** When the bookmark's trade is gone —
  older than OKX's three months — the reader moves to the oldest OKX still
  has and the ids between are counted lost.
- The made table's key is `id` or `open_time` (`row_key`).

Known deviations:

- **The oldest trade is found a day inside the three months**, so a reader
  that far behind loses up to a day more than OKX deleted.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

## D435. A symbol's market watched live from OKX's public streams

- **The shared watch** (D323, D425): the symbol's Market node, rows in the
  grid's columns part by part.
- **Two sockets a symbol and interval**: `/ws/v5/public` subscribed to
  `books` and `tickers`, `/ws/v5/business` to `candle<bar>` and
  `trades-all` — OKX serves candles on the business socket only, and
  `trades` there may merge several trades into one. Each is sent a plain
  `ping` every twenty seconds and answers a plain `pong`, which the shared
  stream skips. Port 443: OKX retires 8443.
- **The snapshot over REST**: the day, 300 candles, the book of 400 and the
  newest hundred trades by id.
- **The book is kept** by each watch from the REST snapshot, OKX's updates
  laid over it (a size of 0 removes a level), reset by a snapshot from the
  stream; twenty levels a side sent whole, at most four times a second, a
  contract's size said as what it is worth.
- **Trades the snapshot held are left out** by their id.
- A 403 or 451 when a socket opens ends the watch in words.

Known deviations:

- **OKX's checksum of the book is not checked**; a book drifted by a lost
  update is right again at the next snapshot.
- **A watcher joining an open socket starts its book from REST**, as Bybit's.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

## D436. The Exchange section, the connection's own use as metrics, symbols found

- **Exchange** (`okx/reports.py`) is the shared section (D425) in OKX's
  words: **Status** (the endpoint, maintenance when OKX's
  `system/status` has trading or its sockets stopped now, each market's
  answer), **Clock**, **Rate limit** (each path asked so far, its own
  window), **Markets**.
- **Metrics**: `weight` labelled by path, `latency` and `reachable` per
  market; the preset is `okx-connection`.
- **Search** reads the kept symbol lists; `enumerate_names` gives every live
  symbol of the three markets, scoped by market. **The Markets folder**
  (D365) lists each market's symbols as their market views.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

## D437. A key with its passphrase reads the account, signed the OKX way

- **A key is an endpoint of its own**: `okx_key`, `eea_key`, `demo_key`,
  the shared `Keyed` with a third `SecretStr`, the passphrase
  (`OkxKeyed`); `HOSTS_OF` maps them to the plain hosts.
- **Signed** through the shared `MarketSession.signed`, its hook given the
  path: `OK-ACCESS-SIGN` is Base64 of HMAC-SHA256 over the time (ISO 8601 in
  UTC to the millisecond, this server's clock plus OKX's offset from
  `public/time`), `GET`, and the path with its query; the key, the time and
  the passphrase in their headers, and demo's flag on every request. 50102
  measures the clock again and sends once more. 50100–50120 and HTTP 401 are
  `auth`, in words that name no key.
- **The check** asks `account/config`. Any key passes; one whose `perm` holds
  more than `read_only` is said to trade or move money (`key_checked`). A
  report **API key** says read only, trade, withdraw, whether it is limited
  to addresses, and its label.
- **Catalog** (`okx/account.py`): an **Account** folder in each market —
  **Balances** of the trading account, the same in every market;
  **Positions** on linear and inverse; **Open orders**; on spot
  **Deposits** and **Withdrawals** — and a symbol's **My orders** (seven
  days) and **My trades** (three days, `trade/fills`).
- **Rows**: each list read whole by OKX's `after`, at most twenty pages of
  100, sorted and filtered here; positions and open orders asked by the
  market's instrument types and kept to its symbols, as a linear and an
  inverse swap share a type; a contract's size said as what it is worth, as
  the public feeds say it; a spot order sized in the quote asset leaves its
  quantity empty; states in OKX's words.
- **My trades are read on by time** (D428, D431): `""` the next own trade's
  time, a block one window of at most three days.

Known deviations:

- **OKX's per-account limits are counted per path** like the public ones,
  not per account across connections.
- **Balances repeat in every market**: OKX has one trading account for all.
- **The funding account's balances are not read**, only its deposits and
  withdrawals.
- **An own trade's unread count is a floor**, as Bybit's.
- **Untested against a real key**: the signature is checked by the fake as
  OKX documents it.

Spec: [An OKX source](../../decisions/2026-11-22-okx-source-design.md)

# OKX

For changing how OKX is reached and kept under its limits, what its catalog
shows of spot, linear and inverse contracts, how its feeds are read as rows,
or what the connection reports, measures and finds. What OKX shares with
every exchange is in [market.md](market.md); the contract every source keeps
is in [contract.md](contract.md).

Decisions here: D432, D433, D436.

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

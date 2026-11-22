# Bybit

Bybit's public market data: spot, USDT and USDC futures, and inverse futures.
You see every symbol's last day and trading rules, read a symbol's candles,
newest trades and order book as rows, and watch its market live. Nothing is
changed on Bybit, and no key is needed. How connections work in general is on
the [Connections](connections.md) page.

## What you can see

- Spot, USDT and USDC futures, inverse futures, symbols by quote asset
- Every symbol's last 24 hours: price, change, high, low and volume
- Every symbol's trading rules: price step, quantity step, minimum order
- A symbol's candles of any interval, from one minute to one month
- A symbol's newest trades: 60 on spot, 1,000 on futures
- A symbol's order book, bids and asks, with running totals
- A symbol's market live: its chart, order book and trades on one screen
- Any of them downloaded as a file
- Bybit's clock and how much of the rate limit is used
- The rate limit and Bybit's answers on a dashboard
- Symbols found by name or by asset
- A symbol's trades or candles carried by a pipeline, only what is new each run

## What you can change

- Nothing: market data is only read

## Connecting

The **Connection** page of the window asks for the **Endpoint**:

- **Bybit** — `api.bybit.com`, and its streams on `stream.bybit.com`;
- **Bybit, through bytick.com** — the same service under its second name,
  for a network that cannot reach the first;
- **Testnet** — Bybit's test network, with prices of its own.

Bybit refuses some countries, the United States among them. If the check says
Bybit does not serve this region, or refuses this address, the DataPlayer
server is in one of them, and another endpoint will not help.

## The catalog

- **Exchange** first: what Bybit and this connection say about themselves.
- **Markets**: a folder for each of the three markets listing its symbols. A
  row opens its **Market** chart at once.
- **Spot**, **USDT and USDC futures** and **Inverse futures**. Each holds
  **Tickers**, **Symbols**, and a folder per quote asset, the one with most
  symbols first.
- A quote asset holds its symbols: only those trading now. Dated futures
  carry their delivery in the name, as `BTCUSDT-27NOV26`.
- A symbol holds **Market**, **Candles** with a series per interval,
  **Trades** and **Order book**.

## Market

**Market**, the first node of every symbol, opens a tab that moves as the
market does: the day across the top, candles over their volume, the order
book with each level's depth, and the trades as they happen.

- Choose the candle interval at the top; scroll or drag the chart to look
  back.
- After the first moment everything comes from Bybit's streams, which cost
  nothing of the rate limit. Several tabs on one symbol share one stream.
- If the network drops, the tab says so and comes back by itself.

## Tables

- **Tickers**: one row per symbol, the busiest by quote volume first. Every
  column sorts and filters. It refreshes every ten seconds.
- **Symbols**: one row per symbol with its rules. Futures add Bybit's
  contract type, the delivery date of a dated future and when it was listed.
- **Candles**: newest first; sort by **open_time** to start from the oldest,
  and filter on it to choose where reading starts and stops. The candle still
  open says `closed` false.
- **Trades**: only the newest Bybit gives — 60 on spot, 1,000 on futures,
  which for a busy symbol is under a minute. Every column sorts and filters.
  Bybit has no older trades to ask for.
- **Order book**: bids best first, then asks best first. Filter **level** to
  choose how deep, up to 1,000; 100 levels by default. Filter **side** for
  one side only.
- **volume** is always in the base asset and **quote_volume** in the quote
  asset. Inverse futures count in USD, and DataPlayer puts each where it
  belongs.
- Prices and quantities are exact decimals, as Bybit writes them.

## In a pipeline

A symbol's **Trades** and each **Candles** series can be the start of a
pipeline's link that reads on: **Add new messages to a table** or **to a new
table**, or **Keep the latest per key**. Each run reads only what came since
the last one, and a pipeline switched on carries it within seconds.

- DataPlayer keeps where each link stopped; Bybit does not.
- **First run reads**: **Only what is new** starts now; **From the earliest
  available** starts with the trades Bybit still gives, or the last day of
  candles.
- A candle is read once it has closed.
- Bybit gives only its newest trades, so a link that runs less often than a
  busy symbol trades a thousand times misses some; the run says trades were
  skipped. Switch the pipeline on to carry them as they come.
- A table the link makes is keyed by the trade **id** or the candle
  **open_time**, so nothing arrives twice.

## Exchange

- **Status**: the endpoint, and whether each market answers.
- **Clock**: each market's time and how far ahead of the DataPlayer server
  it is.
- **Rate limit**: what Bybit allows this address in five seconds, what was
  used, where DataPlayer stops, and whether requests are held.
- **Markets**: how many symbols trade, in how many quote assets, and when the
  list was read; it is read again after an hour.

## Dashboards and search

- The **Bybit connection** dashboard draws the requests made in each five
  seconds against where DataPlayer stops, how long Bybit takes to answer, and
  whether each market answers. Prices are not on it: carry them into a table
  with a pipeline and draw that.
- The search finds symbols by name and by asset: `btc` finds BTCUSDT and
  ETHBTC, names first. Searching inside a quote asset keeps to it. Symbols can
  be kept for the search over everything.

## The rate limit

Bybit allows an address 600 requests in five seconds over all its markets,
and blocks an address that asks more for at least ten minutes. DataPlayer
counts its own requests and stops at 240 in any five seconds, saying how long
to wait. If Bybit blocks the address anyway, nothing is asked until the block
ends.

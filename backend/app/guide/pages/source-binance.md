# Binance

Binance's public market data: spot, USDⓈ-M and COIN-M futures. You see every symbol's
last day and trading rules, and read a symbol's candles, trades and order book
as rows. Nothing is changed on Binance, and no key is needed. How connections
work in general is on the [Connections](connections.md) page.

## What you can see

- Spot, USDⓈ-M and COIN-M futures, symbols grouped by quote asset
- Every symbol's last 24 hours: price, change, high, low and volume
- Every symbol's trading rules: price step, quantity step, minimum order
- A symbol's candles of any interval, from one second to one month
- A symbol's trades, newest first, by id or from a time
- A symbol's order book, bids and asks, with running totals
- With a key: balances, positions, orders, own trades, deposits, withdrawals
- Any of them downloaded as a file
- Binance's status, its clock, and how much of the rate limit is used
- The rate limit and Binance's answers on a dashboard
- Symbols found by name or by asset
- A symbol's trades or candles carried by a pipeline, only what is new each run

## What you can change

- Nothing: market data is only read

## Connecting

The **Connection** page of the window asks for the **Endpoint**:

- **Binance** — the main hosts, `api.binance.com`, `fapi.binance.com` and
  `dapi.binance.com`;
- **Binance, market data only** — spot from `data-api.binance.vision`, which
  serves public data alone and often answers when the main host is busy;
- **Testnet** — Binance's test network, with prices of its own.
- **Binance, with an API key** and **Testnet, with an API key** — the same
  hosts, and the account the key belongs to as well.

Binance refuses some countries. If the check says Binance does not serve this
address, the DataPlayer server is in one of them, and another endpoint will
not help.

## The catalog

- **Exchange** first: what Binance and this connection say about themselves.
- **Spot**, **USDⓈ-M futures** and **COIN-M futures**. Each holds **Tickers**, **Symbols**, and a
  folder per quote asset — **USDT**, **USDC**, **BTC** and the rest — the one
  with most symbols first.
- A quote asset holds its symbols: only those trading now.
- A symbol holds **Candles**, with a series per interval, **Trades** and
  **Order book**.

## Tables

- **Tickers**: one row per symbol, the busiest by quote volume first. Every
  column sorts and filters. It refreshes every ten seconds.
- **Symbols**: one row per symbol with its rules. Futures add the contract
  type, its delivery date and when it was listed.
- **Candles**: newest first; sort by **open_time** to start from the oldest,
  and filter on it to choose where reading starts and stops. The candle still
  open says `closed` false.
- **Trades**: Binance's aggregated trades, newest first. Filter by **id** or
  **time** to choose where reading starts. Binance keeps about two years of
  spot trades, and answers futures trades of the last two days only.
- **Order book**: bids best first, then asks best first. Filter **level** to
  choose how deep; 100 levels by default. Filter **side** for one side only.
- A page of candles or trades reaches at most ten thousand rows deep. To look
  further back, filter by time.
- Prices and quantities are exact decimals, as Binance writes them.
- **COIN-M** counts in contracts worth 100 USD for BTC and 10 USD for the
  rest. Its tickers and candles still give **volume** in the base asset and
  **quote_volume** in USD, like every market; **Symbols** add
  **contract_size**. A trade's and an order book's **quantity** are
  contracts.

## In a pipeline

A symbol's **Trades** and each **Candles** series can be the start of a
pipeline's link that reads on: **Add new messages to a table** or **to a new
table**, or **Keep the latest per key**. Each run reads only what came since
the last one, and **Follow** carries it within seconds.

- DataPlayer keeps where each link stopped; Binance does not.
- **First run reads**: **Only what is new** starts now; **From the earliest
  available** starts with the last hour of trades, or the last day of
  candles.
- A candle is read once it has closed.
- A table the link makes is keyed by the trade **id** or the candle
  **open_time**, so nothing arrives twice.
- Tickers, Symbols and the order book are a moment, not a history: a link
  takes them whole each run.

## Your account

With a key, each market holds **Account**: **Balances**, **Positions** on
futures, **Open orders**, and on spot **Deposits** and **Withdrawals** of
the last ninety days. A symbol adds **My orders** and **My trades**, the
newest thousand of each. **My trades** can start a pipeline's link, as
**Trades** can.

- Make the key on Binance with reading only. A key that may also trade or
  withdraw is accepted and the check says so: DataPlayer only reads, but a
  key that can only read is safer.
- If the key is limited to addresses, add the DataPlayer server's.
- **API key** in **Exchange** says what Binance lets the key do.
- The testnet gives spot and futures keys of their own; a connection holds
  one, so the other market refuses it.

## Exchange

- **Status**: the endpoint, Binance's own status — known on the main
  endpoint only — and whether each market answers.
- **Clock**: each market's time and how far ahead of the DataPlayer server
  it is. Times sent to Binance are the server's, so a large difference moves
  them.
- **Rate limit**: what each market allows a minute, what this address used
  this minute, where DataPlayer stops, and whether Binance holds requests.
- **Markets**: how many symbols trade, in how many quote assets, and when the
  list was read; it is read again after an hour.

## Dashboards and search

- The **Binance connection** dashboard draws the weight used each minute
  against where DataPlayer stops, how long Binance takes to answer, and
  whether each market answers. Prices are not on it: carry them into a table
  with a pipeline and draw that.
- The search finds symbols by name and by asset: `btc` finds BTCUSDT and
  ETHBTC, names first. Searching inside a quote asset keeps to it. Symbols can
  be kept for the search over everything.

## The rate limit

Binance counts what every address asks of it per minute, and blocks an
address that asks too much. DataPlayer reads the count from every answer and
stops at 80% of the limit, saying how many seconds are left of the minute. If
Binance blocks the address anyway, nothing is asked until the block ends.

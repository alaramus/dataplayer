# OKX

OKX's public market data: spot, USDT and USDC futures, and inverse futures,
perpetual and dated. You see every symbol's last day and trading rules, read
a symbol's candles, trades of the last three months and order book as rows,
and watch its market live. Nothing is changed on OKX, and no key is needed.
How connections work in general is on the [Connections](connections.md) page.

## What you can see

- Spot, USDT and USDC futures, inverse futures, symbols by quote asset
- Every symbol's last 24 hours: price, change, high, low and volume
- Every symbol's trading rules: price step and quantity step
- A symbol's candles of any interval, from one second to one month
- A symbol's trades of the last three months, by number or time
- A symbol's order book, bids and asks, with running totals
- A symbol's market live: its chart, order book and trades on one screen
- Any of them downloaded as a file
- OKX's clock, its maintenance and how much of each limit is used
- The limits and OKX's answers on a dashboard
- Symbols found by name or by asset
- A symbol's trades or candles carried by a pipeline, only what is new each run
- With a key: balances, positions, orders, own trades, deposits, withdrawals

## What you can change

- Nothing: market data is only read

## Connecting

The **Connection** page of the window asks for the **Endpoint**:

- **OKX** — `www.okx.com`, and its streams on `ws.okx.com`;
- **OKX Europe** — `eea.okx.com`, OKX's European service: a market of its
  own, with its own prices and trades;
- **Demo trading** — OKX's demo market, with prices of its own.
- **OKX, with an API key**, **OKX Europe, with an API key** and **Demo
  trading, with an API key** — the same, and the account the key belongs to
  as well. They ask for the key, its secret and the passphrase chosen when
  the key was made.

OKX does not serve some countries, the United States among them. If the
check says OKX does not serve this address or region, the DataPlayer server
is in one of them; OKX Europe serves only the European Economic Area.

## The catalog

- **Exchange** first: what OKX and this connection say about themselves.
- **Markets**: a folder for each of the three markets listing its symbols. A
  row opens its **Market** chart at once.
- **Spot**, **USDT and USDC futures** and **Inverse futures**. The futures
  hold OKX's perpetual swaps and dated futures together. Each market holds
  **Tickers**, **Symbols**, and a folder per quote asset, the one with most
  symbols first.
- A quote asset holds its symbols: only those trading now. A perpetual ends
  in `-SWAP`, as `BTC-USDT-SWAP`; a dated future in its date, as
  `BTC-USDT-261225`.
- A symbol holds **Market**, **Candles** with a series per interval,
  **Trades** and **Order book**.

## Market

**Market**, the first node of every symbol, opens a tab that moves as the
market does: the day across the top, candles over their volume, the order
book with each level's depth, and the trades as they happen.

- Choose the candle interval at the top; scroll or drag the chart to look
  back.
- After the first moment everything comes from OKX's streams, which cost
  nothing of its limits. Several tabs on one symbol share them.
- If the network drops, the tab says so and comes back by itself.

## Tables

- **Tickers**: one row per symbol, the busiest first. Every column sorts and
  filters. It refreshes every ten seconds. OKX gives no quote volume for
  USDT and USDC futures, so there the column is missing and the busiest are
  those with most volume in the coin.
- **Symbols**: one row per symbol with its rules. Futures add OKX's type —
  `SWAP` for a perpetual, `FUTURES` for a dated one — the delivery date of a
  dated future and when it was listed. Inverse futures add what one contract
  is worth in USD.
- **Candles**: newest first; sort by **open_time** to start from the oldest,
  and filter on it to choose where reading starts and stops. The candle still
  open says `closed` false. Days and weeks open at midnight UTC.
- **Trades**: newest first. OKX numbers a symbol's trades one after another
  and keeps three months of them: filter on **id** or **time** to choose
  where to look, and sort by **id** to start from the oldest.
- **Order book**: bids best first, then asks best first. Filter **level** to
  choose how deep, up to 400; 100 levels by default. Filter **side** for one
  side only.
- **volume** is always in the base asset and **quote_volume** in the quote
  asset. OKX counts futures in contracts; DataPlayer says each as what it is
  worth. On inverse futures a trade's size is in USD, so the column there is
  **quote_quantity**, and the order book's quantity is in USD too.
- Prices and quantities are exact decimals, as OKX writes them.

## In a pipeline

A symbol's **Trades** and each **Candles** series can be the start of a
pipeline's link that reads on: **Add new messages to a table** or **to a new
table**, or **Keep the latest per key**. Each run reads only what came since
the last one, and a pipeline switched on carries it within seconds.

- DataPlayer keeps where each link stopped; OKX does not.
- **First run reads**: **Only what is new** starts now; **From the earliest
  available** starts with the last hour of trades, or the last day of
  candles.
- A candle is read once it has closed.
- A link that has not run for more than three months finds its oldest trades
  gone from OKX; the run says how many were skipped.
- A table the link makes is keyed by the trade **id** or the candle
  **open_time**, so nothing arrives twice.

## Your account

With a key, each market holds **Account**: **Balances** of the trading
account, the same in every market; **Positions** on futures; **Open
orders**; and on spot **Deposits** and **Withdrawals**. A symbol adds **My
orders** of the last seven days and **My trades** of the last three. **My
trades** can start a pipeline's link, as **Trades** can.

- Make the key on OKX with only the **Read** permission. A key that may also
  trade or withdraw is accepted and the check says so: DataPlayer only reads,
  but a read-only key is safer.
- If the key is limited to addresses, add the DataPlayer server's.
- **API key** in **Exchange** says what OKX lets the key do.

## Exchange

- **Status**: the endpoint, whether OKX says trading is under maintenance,
  and whether each market answers.
- **Clock**: each market's time and how far ahead of the DataPlayer server
  it is.
- **Rate limit**: for each kind of request asked so far, what OKX allows in
  its window, what was used, where DataPlayer stops, and whether requests
  are held.
- **Markets**: how many symbols trade, in how many quote assets, and when the
  list was read; it is read again after an hour.
- **API key**: whether the key is read-only, whether it may trade or
  withdraw, and whether it is limited to addresses.

## Dashboards and search

- The **OKX connection** dashboard draws the requests made of each kind in
  its window against where DataPlayer stops, how long OKX takes to answer,
  and whether each market answers. Prices are not on it: carry them into a
  table with a pipeline and draw that.
- The search finds symbols by name and by asset: `btc` finds BTC-USDT and
  ETH-BTC, names first. Searching inside a quote asset keeps to it. Symbols
  can be kept for the search over everything.

## The rate limit

OKX limits each kind of request on its own: so many in two seconds — 20 for
candles, 20 for trades, 40 for the order book. DataPlayer counts its own
requests and stops at 40% of each, so it never passes 80% of any two
seconds; a request past that waits for the next two seconds rather than
failing, so a long download takes a few seconds more. If OKX refuses the
address anyway, that kind of request waits two seconds.

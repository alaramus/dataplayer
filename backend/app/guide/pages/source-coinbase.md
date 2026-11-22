# Coinbase Exchange

Coinbase Exchange's public market data: its spot products. You see every
product's last day and trading rules, read a product's candles, every trade
it ever had and its order book as rows, and watch its market live. Nothing is
changed on Coinbase, and no key is needed. How connections work in general is
on the [Connections](connections.md) page.

## What you can see

- Spot products by quote asset
- Every product's last 24 hours: price, change, high, low and volume
- Every product's trading rules: price step, quantity step, minimum order
- A product's candles: 1 and 5 minutes, 15 minutes, 1 and 6 hours, a day
- Every trade of a product since it was listed, by number
- A product's order book, bids and asks, with running totals
- A product's market live: its chart, order book and trades on one screen
- Any of them downloaded as a file
- Coinbase's clock and how much of the rate limit is used
- The rate limit and Coinbase's answers on a dashboard
- Products found by name or by asset
- A product's trades or candles carried by a pipeline, only what is new
- With a key: balances, open orders, your orders and own trades

## What you can change

- Nothing: market data is only read

## Connecting

The **Connection** page of the window asks for the **Endpoint**:

- **Coinbase Exchange** — `api.exchange.coinbase.com`, and its feed on
  `ws-feed.exchange.coinbase.com`;
- **Sandbox** — Coinbase's public sandbox, with prices of its own.
- **Coinbase Exchange, with an API key** — the same, and your Coinbase
  account as well. It asks for the key's **name** and its **private key**,
  as the Coinbase Developer Platform gives them.

## The catalog

- **Exchange** first: what Coinbase and this connection say about
  themselves.
- **Markets**: a folder listing every product. A row opens its **Market**
  chart at once.
- **Spot** holds **Tickers**, **Symbols**, and a folder per quote asset, the
  one with most products first.
- A quote asset holds its products: only those trading now, as `BTC-USD`.
- A product holds **Market**, **Candles** with a series per interval,
  **Trades** and **Order book**.

## Market

**Market**, the first node of every product, opens a tab that moves as the
market does: the day across the top, candles over their volume, the order
book with each level's depth, and the trades as they happen.

- Choose the candle interval at the top; scroll or drag the chart to look
  back.
- After the first moment everything comes from Coinbase's feed, which costs
  nothing of the rate limit. Coinbase sends no candles on it, so DataPlayer
  draws the candle still open from the trades as they come.
- If the network drops, the tab says so and comes back by itself.

## Tables

- **Tickers**: one row per product, those with most volume first. Every
  column sorts and filters. It refreshes every ten seconds. Coinbase gives
  the day's volume in the base asset only, so there is no **quote_volume**.
- **Symbols**: one row per product with its rules.
- **Candles**: newest first; sort by **open_time** to start from the oldest,
  and filter on it to choose where reading starts and stops. The candle still
  open says `closed` false. Coinbase gives no candle for an interval without
  a trade.
- **Trades**: newest first. Coinbase numbers a product's trades one after
  another from the first and keeps them all: filter on **id** to choose where
  to look, and sort by **id** to start from the very first. Coinbase has no
  way to find a trade by its time, so **time** is not a filter.
- **Order book**: bids best first, then asks best first. Filter **level** to
  choose how deep, up to 1,000; 100 levels by default. Filter **side** for
  one side only.
- **volume** is always in the base asset. Prices and quantities are exact
  decimals, as Coinbase writes them.

## In a pipeline

A product's **Trades** and each **Candles** series can be the start of a
pipeline's link that reads on: **Add new messages to a table** or **to a new
table**, or **Keep the latest per key**. Each run reads only what came since
the last one, and a pipeline switched on carries it within seconds.

- DataPlayer keeps where each link stopped; Coinbase does not.
- **First run reads**: **Only what is new** starts now; **From the earliest
  available** starts with the newest thousand trades, or the last day of
  candles.
- A candle is read once its interval has ended.
- Coinbase keeps every trade, so a link that has not run for a long time
  misses none.
- A table the link makes is keyed by the trade **id** or the candle
  **open_time**, so nothing arrives twice.

## Your account

With a key, **Spot** holds **Account**: **Balances** of your Coinbase
account, and **Open orders**. A product adds **My orders** and **My trades**.
**My trades** can start a pipeline's link, as **Trades** can.

- Make the key on the Coinbase Developer Platform with the **View**
  permission only, and the **ECDSA** signature algorithm. A key that may also
  trade or move money is accepted and the check says so: DataPlayer only
  reads, but a view-only key is safer.
- Paste the private key whole, from `-----BEGIN` to the end.
- **API key** in **Exchange** says what Coinbase lets the key do.

## Exchange

- **Status**: the endpoint, and whether Coinbase answers.
- **Clock**: Coinbase's time and how far ahead of the DataPlayer server it
  is.
- **Rate limit**: what Coinbase allows this address in a second, what was
  used, where DataPlayer stops, and whether requests are held.
- **Markets**: how many products trade, in how many quote assets, and when
  the list was read; it is read again after an hour.
- **API key**: whether the key may view, trade or move money, and its
  portfolio.

## Dashboards and search

- The **Coinbase connection** dashboard draws the requests made in each
  second against where DataPlayer stops, how long Coinbase takes to answer,
  and whether it answers. Prices are not on it: carry them into a table with
  a pipeline and draw that.
- The search finds products by name and by asset: `eth` finds ETH-USD and
  ETH-BTC. Searching inside a quote asset keeps to it. Products can be kept
  for the search over everything.

## The rate limit

Coinbase allows an address ten public requests a second. DataPlayer counts
its own requests and stops at four in any second, so it never passes eight
in any second; a request past that waits for the next second rather than
failing, so a long download takes a few seconds more. If Coinbase refuses
the address anyway, requests wait a second.

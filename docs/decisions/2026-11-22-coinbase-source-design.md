# A Coinbase Exchange source

Decisions D438–D442. The fourth exchange on the shared layer (D425), built
on the branch of OKX (D432–D437), whose shared pieces it uses: pacing and
the address-wide budget. Coinbase Exchange is spot only and keeps every
trade, numbered from one; it streams no candles.

## Facts checked

Against the live API from this machine and Coinbase's Exchange
documentation, on 2026-11-22.

- **Hosts.** `api.exchange.coinbase.com`, the feed
  `wss://ws-feed.exchange.coinbase.com`; the sandbox
  `api-public.sandbox.exchange.coinbase.com` answers the same paths.
- **Limit.** Public endpoints: ten requests a second per address, bursts to
  fifteen; 429 when passed. No count is sent back.
- **Products.** `/products`: 847, `online` or `delisted`, with
  `trading_disabled`, `quote_increment`, `base_increment`,
  `min_market_funds`; thirteen quote currencies.
- **Day.** `/products/stats` answers every product's `stats_24hour` (open,
  high, low, last, volume in the base) at once; no quote volume.
- **Candles.** `/products/{id}/candles`: granularity 60, 300, 900, 3600,
  21600 or 86400 only ("Unsupported granularity" else); at most 300 a
  request (350 answered without bounds); `start` and `end` as ISO or epoch,
  both included, both or neither; rows `[time, low, high, open, close,
  volume]` as JSON numbers, newest first; none for an interval without a
  trade.
- **Trades.** `/products/{id}/trades`: up to 1,000, newest first; `after`
  an id gives older ones; ids consecutive from 1 (BTC-USD's first trades
  are from December 2014, all still answered). `side` is the maker's.
  Cursors also in `CB-BEFORE` and `CB-AFTER`.
- **Book.** `level=1` the best, `level=2` the whole aggregated book (about
  10,000 levels for BTC-USD), `level=3` every order.
- **Feed.** `matches`, `ticker`, `heartbeat` and `level2_batch` answer
  without a key (`level2_batch` is reported back as `level2_50`); `level2`
  and `full` need one. No candle channel. The book's channel sends a
  `snapshot`, then `l2update` changes of `[side, price, size]`, a size of 0
  removing a level.
- **Unknown product**: 404 `{"message": "NotFound"}`.
- **Not confirmed**: how an Exchange key signs (the documentation's pages on
  it did not answer), so no key in this round.

## What the shared layer gained

- `difference` and `percent_change` in `values.py`, on this second use
  after OKX; a difference written out, never as `1E-8`.

## Decisions

- **D438.** Endpoints as a closed set; one budget for the address, waited
  for; numbers parsed as their text.
- **D439.** One spot market; tickers in one request; candles by spans;
  trades by id; the whole book cut to depth.
- **D440.** Trades read on by id, nothing lost; candles by the clock's open.
- **D441.** One socket a product on public channels; the open candle kept
  from trades.
- **D442.** The shared reports, metrics and search.

## Plan of slices

1. Connection, catalog, feeds, reports, metrics, search (D438, D439, D442).
2. Reading on and the live view (D440, D441).
3. A key and the account, once its signing is checked.

# A Binance source

Decisions D316, D317 and D318. The first slice of a Binance source type: a
connection to Binance's public market data, its markets, symbols and their
tables in the catalog, and each table as rows. The later slices are listed at
the end; each gets its own spec and commit, on the branch `binance-adapter`.

Binance is the first source that is somebody else's service rather than a
server the user runs: nothing in it is changed, nothing is created, and what
it answers is bounded by a rate limit per address rather than by the user's
own hardware. It is read for two reasons — to look at a market, and to carry
it into the user's own stores through a pipeline — and the second is why it
is a source at all.

## Why a catalog and rows, and not a screen of its own

A market wants a chart, a live order book and a tape of trades side by side,
and the grid is none of those. A separate screen was weighed and not taken
first: pipelines (D312–D315), paste, transfer, export, search and the agent all
read a node of the catalog as rows, and a screen beside the catalog would get
none of them. So the market is nodes and rows first. Looking at one symbol as
a chart, a book and a tape is a representation of its node (D47), declared
later by the same node, not a second way in with rules of its own.

## What the user chose

Asked before the work began:

- Public market data only. No API key in the first version; a read-only key
  for balances, own trades and open orders may come as a slice of its own.
  Placing orders is not planned at all.
- Two markets: spot and USDⓈ-M futures. COIN-M later.
- A category of its own, Market data, rather than Queues & Streams: Binance is
  not a queue, and other exchanges and market APIs belong beside it.
- The market view — chart, book and tape — is a task of its own after these
  slices, not one of them.

## The client and the connection (D316)

httpx, which the backend already has, asynchronous, one client per connection
kept in the connection's resources and closed with it: a request is cheap, and
a client per request pays a TLS handshake each time. No SDK — Binance's own is
synchronous and covers trading, which is out of scope.

The connection names an endpoint from a closed set, each a pair of base URLs
for the two markets:

- **Binance** — `api.binance.com` and `fapi.binance.com`.
- **Binance, market data only** — `data-api.binance.vision` for spot, which
  serves public data alone and answers where the main host is busy, and
  `fapi.binance.com`.
- **Testnet** — `testnet.binance.vision` and `testnet.binancefuture.com`.

Binance US is not offered: it has no futures, and it refuses requests from
outside the United States (451), so it cannot be tested from here.

Nothing is secret, so nothing is encrypted. No SSH tunnel (D282): these are
public HTTPS hosts. Checking a connection asks `ping` and `time` of each
market and reports the clock's difference from the server's.

**The rate limit is the source's.** Binance weighs every request and allows
6,000 a minute for spot and 2,400 for futures per address, then answers 429
and, ignored, 418 with a ban measured in minutes to days. The client reads
`X-MBX-USED-WEIGHT-1M` from every answer and refuses to send a request that
would take a market past 80% of its limit, saying how many seconds remain of
the minute. A 429 or 418 refuses everything for that market until its
`Retry-After`. Nothing is retried by itself.

**Errors are reduced to a kind.** Binance answers `{code, msg}`: an unknown
symbol (-1121) is a 404, a parameter refused is a refusal of the request, a
451 says the endpoint is closed to this address, and everything else is
"Binance refused the request" with the code. Binance's text is not shown: it
is not secret here, but the rule that a driver's text never reaches the
caller has no exception for a source where it happens to be harmless.

**Symbols are checked against the exchange, not against a pattern.** Most
symbols are `BTCUSDT`, but some are not ASCII at all (a few dozen have
Chinese names), and futures add `_251226` delivery suffixes. A symbol named
by a client is looked up in the market's symbol list before any request is
built, and its name goes into a query parameter, never into a path.

The symbol list is `exchangeInfo` with `symbolStatus=TRADING`: unfiltered it
is 17 MB for spot, most of it 2,400 symbols that no longer trade; filtered
it is 2.5 MB and 20 weight. It is kept per connection for an hour.

## Markets, quotes and symbols in the catalog (D317)

Levels, as Kafka has them:

```
Spot                                   market
  Tickers                              feed: every symbol's last 24 hours
  Symbols                              feed: every symbol's trading rules
  USDT                                 quote asset
    BTCUSDT                            symbol
      Candles                          directory
        1m … 1M                        feed: one interval each
      Trades                           feed
      Order book                       feed
  USDC …
USDⓈ-M futures                         the same; no 1s candles
```

- **A market** is a directory. Its quote assets are its directories, the ones
  with most symbols first: spot has 26 (USDT 518, TRY 310, USDC 255…), futures
  five. A symbol list grouped this way is never long enough for the level
  ceiling; one list of 1,372 would be.
- **A symbol** is a new kind, `symbol`: its base and quote assets and, for
  futures, its contract type. It opens as nothing yet; the market view will be
  its first representation.
- **A feed** is a new kind, `feed`: a read-only table of a market, with which
  feed it is and, for candles, its interval. It opens as rows and is
  describable. Not a `table`, since nothing about it can be altered and its
  rows are named by time or by Binance's ids, not by a key.
- **Each candle interval is a node** rather than a filter, so a pipeline's
  link names the series it reads (`BTCUSDT 1m`) and keeps one bookmark for it.
- Node ids: `spot`, `usdm`; `spot:tickers`, `spot:symbols`, `spot:quote:USDT`;
  `spot:symbol:BTCUSDT`, `…:trades`, `…:book`, `…:candles`, `…:candles:1h`.
  A symbol never holds a colon, and is checked as above.

## The feeds as rows (D318)

Every value Binance gives as a decimal string stays a decimal (`numeric`);
none passes through a float. Times arrive in milliseconds and are timestamps.

- **Tickers**: symbol, last price, change, change %, weighted average, open,
  high, low, volume, quote volume, trades, open and close time. One request
  for the whole market (spot 80 weight, futures 40), kept for ten seconds.
  Rows sort and filter on the server among what was read, by any column; the
  newest quote volume first. The grid's timer (D67) refreshes them.
- **Symbols**: symbol, base, quote, status, price step, quantity step,
  minimum notional and, for futures, contract type, delivery date and listing
  date. Read from the kept list; sorts and filters as Tickers do.
- **Candles**: open time, close time, open, high, low, close, volume, quote
  volume, trades, taker buy volume, taker buy quote volume, closed. Newest
  first; ascending from a time. The page is turned by time — candles are
  regular, so offset N is N intervals back — and a filter on open time sets
  where reading starts and stops. One request reads 1,000 on spot and 1,500 on
  futures; a page is never more than one request.
- **Trades**: Binance's aggregated trades — id, price, quantity, first and
  last trade id, time, buyer is the maker. Newest first, turned by id, since
  aggregated ids follow each other without gaps; filters on id and on time.
  Binance keeps about two years of them; older ids answer from its oldest.
- **Order book**: side, level, price, quantity and the cumulative quantity
  from the best price outwards; bids best first, then asks best first. Its
  depth is a filter from Binance's own set (5 to 5,000 on spot, to 1,000 on
  futures), 100 by default, since weight grows with it.

Nothing is editable, inserted or deleted. Export reads as the page does, to
the ceiling of the grid's export (D49).

## Later slices

2. **Read on in a pipeline** (`SupportsReadingOn`, D312): Trades by the next
   aggregated id, Candles by the next closed candle's open time, so a link
   carries only what is new and following (D315) polls every two seconds
   within the rate limit. With it: one more source of the Binance → Kafka →
   stores route.
3. **Reports, metrics, search, the guide in every language**: system status,
   the clock's difference and the weight used as reports; weight used per
   minute as a metric; symbols searched by name and asset.

After them, as tasks of their own: the market view of a symbol (chart, book,
tape; live, perhaps over Binance's WebSocket), COIN-M futures, and a read-only
API key.

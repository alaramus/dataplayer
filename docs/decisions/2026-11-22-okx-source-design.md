# An OKX source

Decisions D432–D437. The third exchange on the shared layer of market data
(D425), after Binance and Bybit. What OKX does differently from both is
where its rate limit lives — on each path — and that its trades are numbered
and kept for three months, so they page by id rather than by time.

## Facts checked

Against the live API from this machine and OKX's v5 documentation, on
2026-11-22.

- **Hosts.** `www.okx.com` (also answers as `my.okx.com`, `app.okx.com`);
  `eea.okx.com` is OKX's European service and a different market (other
  trades at the same moment). Demo trading is the main host with
  `x-simulated-trading: 1`, and its prices differ. Streams are
  `wss://ws.okx.com/ws/v5/{public,business}`, `wseea.okx.com`,
  `wspap.okx.com` for demo; port 8443 answers with a notice that it will be
  retired, so 443 is used.
- **Every answer has a `code`**, `"0"` for success, the data in `data`.
  51001 is an instrument that does not exist, 51000 a parameter error, 50011
  a rate limit (HTTP 429), 50121 an address OKX does not serve, 51155 a
  region; 50102 a timestamp more than thirty seconds off; 50100–50120 a key
  refused (HTTP 401 mostly).
- **Limits are per path** and published, by address for public paths:
  `public/time` 10 in 2 s, `public/instruments` 20 in 2 s for each
  instrument type, `system/status` 1 in 5 s, `market/tickers` 20,
  `market/books` 40, `market/history-candles` 20, `market/history-trades`
  20, all in 2 s. No count is sent back.
- **Instruments.** SPOT (1,250 live), SWAP (546: linear and inverse), FUTURES
  (293: linear and inverse, dated). States `live`, `suspend`, `preopen`,
  `test`. A contract has `ctType` (`linear`, `inverse`), `ctVal` (0.01 BTC on
  BTC-USDT-SWAP, 100 USD on BTC-USD-SWAP) and `instFamily` (`BTC-USDT`);
  spot has `baseCcy` and `quoteCcy`. No instrument id holds a colon. Lots on
  inverse are fractional now (0.1 contract).
- **Tickers.** `vol24h` is base on spot, contracts on derivatives;
  `volCcy24h` is quote on spot, the base coin on derivatives. No quote volume
  for a linear contract, no percent change; `open24h` is the price 24 hours
  ago.
- **Candles.** `history-candles` answers up to 300 (the documentation says
  300; `candles` 300 too, recent only), newest first, back to 2020 for
  BTC-USDT. A row is `[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]`:
  `volCcyQuote` is the quote asset's on every market (USD on inverse);
  `confirm` 1 once closed. `after` gives older than a time, `before` newer;
  `before` alone gives the newest; both give the newest of the span. Bars
  `1s 1m 3m 5m 15m 30m 1H 2H 4H`, then `6H … 3M` at Hong Kong's open or
  `6Hutc … 3Mutc` at UTC's; `1s` on spot and contracts. A week opens on
  Monday, three days on a running count.
- **Trades.** `history-trades` answers 100 (300 when asked more, though the
  documentation says 100), three months back, newest first; `type=1` pages
  by `tradeId`, `type=2` by time (`after` only). Ids of an instrument are
  consecutive and start at 1 (a young futures contract's first trades are
  1, 2, 3). `sz` is base on spot, contracts on derivatives; `side` is the
  taker's.
- **Book.** `books` answers any `sz` up to 400 a side; a level is price,
  size, a zero and an order count.
- **Status.** `system/status` lists maintenance with `state` and
  `serviceType` (0 sockets, 5 trading, 11 copy trading…); one was ongoing
  for copy trading while trading ran.
- **Streams.** `trades`, `books`, `tickers` on `public`; candles
  (`candle1H`, `candle1Dutc`…) and `trades-all` on `business` only, a
  candle on `public` refused (60018). `trades` may aggregate (`count`);
  `trades-all` sends each trade. A plain `ping` is answered by a plain
  `pong`, not JSON. An unknown instrument in a subscription is refused alone,
  the others kept.
- **Signing.** `OK-ACCESS-SIGN` is Base64 of HMAC-SHA256 over time, method,
  path with query, and body; the time ISO 8601 in UTC to the millisecond,
  within thirty seconds; a passphrase in `OK-ACCESS-PASSPHRASE`.

## What the shared layer gained

Each of these was a second or third use; Binance and Bybit behave as before.

- **A budget chosen by the session** (`MarketSession.budget`) from the
  market, the path and the parameters, kept in `Kept.budgets` where it is
  neither the market's nor the address's.
- **Pacing** (`paces`): a request over the ceiling waits for the next
  window. Binance's minute and Bybit's five seconds refuse as before.
- **Headers on every request** (`headers`), for demo trading.
- **The path in the signing hook**, as OKX signs it.
- **A stream's `pong`**, a keep-alive answer that is not JSON.
- **Tickers busiest by volume** where an exchange has no quote volume, and
  **symbol columns left out** where it has no value for them.

## D432. The connection

Endpoints as a closed set (D316); each path's own budget, at 40% of two
seconds, waiting rather than refusing; refusals by `code` reduced to kinds.
The limit is not read from OKX: it publishes it and sends no count.

## D433. The catalog and the feeds

Markets by contract — spot, linear, inverse — rather than OKX's instrument
types, so the volumes of one market mean one thing and the shared catalog
reads them as Bybit's. Trades by id, since OKX numbers them; candles from
`history-candles`, which reaches years back. A contract's size is said as
what it is worth; where that is USD the column says so (`quote_quantity`),
except in the shared book.

## D436. Reports, metrics, search

The shared section; the rate limit and the `weight` metric said per path,
since that is what OKX limits.

## D437. A key and the account

A key is an endpoint of its own with a passphrase beside the key and its
secret. Signing goes through the shared session, its hook now given the path
OKX signs. The account's lists are read by instrument type and kept to the
market's symbols, since OKX puts linear and inverse swaps under one type.

## Plan of slices

1. Connection, catalog, feeds, reports, metrics, search (D432, D433, D436).
2. Candles and trades read on by a link (D434).
3. A symbol's market watched live (D435).
4. A key and the account it reads; the guide (D437).

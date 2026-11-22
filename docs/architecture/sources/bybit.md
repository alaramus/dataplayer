# Bybit

For changing how Bybit is reached and kept under its rate limit, what its
catalog shows of spot, linear and inverse markets, how its feeds are read as
rows, how a link reads them on, how a symbol is watched live, or what the
connection reports, measures and finds. What Bybit shares with every exchange
is in [market.md](market.md); the contract every source keeps is in
[contract.md](contract.md).

Decisions here: D426, D427, D430.

## D426. Bybit's public market data over v5 REST, its requests counted here

- **Nothing changed on Bybit, and no key yet.** The connection names an
  endpoint from a closed set: Bybit (`api.bybit.com`, streams on
  `stream.bybit.com`), the same through `api.bytick.com`, and the testnet
  (`api-testnet.bybit.com`). The options are a discriminated union already,
  so a key comes as an endpoint of its own, as Binance's did (D322).
- **One client a connection** on the shared session (D425): the symbol list
  kept an hour, the tickers ten seconds. Every path is `/v5/market/<name>`,
  the market's category a parameter (`BybitSession.ask`).
- **Requests are counted here.** Bybit sends no count on public paths and
  limits the address — 600 requests in five seconds — not each market, so
  one budget on `Kept.address` is spent by all three. Its windows are five
  seconds from their start and its share 40%, so two windows side by side
  never pass 80% of any rolling five seconds. A request weighs 1.
- **Failures are kinds.** Bybit answers HTTP 200 with a `retCode`: 10009 (a
  region it does not serve) is `config`; 10006 and 10018 hold every request
  five seconds; 10001 or 10029 on a node is that node not found — the symbol
  was checked against the list first, so it has gone since; 10016, 5xx and
  transport failures are `network`; anything else is "Bybit refused the
  request" with the code. HTTP 403 is a ban or a United States address, and
  Bybit says nothing to tell them apart: every request is held ten minutes
  and the refusal names both. `retMsg` is never passed on.
- **Symbols are checked by membership**, never by a pattern: dated linear
  futures hold a hyphen (`BTCUSDT-27NOV26`).

Known deviations:

- **A 403 is not told apart** from a ban, and holds the connection ten
  minutes either way.
- **The limit is Bybit's documented default**, not read from Bybit: it says
  nothing about an address's limit on public paths.
- **Tests run against a fake** (`tests/adapters/bybit_fixture.py`): CI's
  address is in the United States, which Bybit refuses.

Spec: [A Bybit source, and what exchanges share](../../decisions/2026-11-22-bybit-source-design.md)

## D427. Spot, linear and inverse in the shared catalog, read as rows of one meaning

```
spot | linear | inverse              directory, Bybit's categories as ids
  :tickers, :symbols                 feed
  :quote:USDT …                      directory, fullest first
    :symbol:BTCUSDT                  symbol
      :market                        feed, opened as `market`
      :candles                       directory
        :candles:1m … :candles:1M    feed, one per interval Bybit has
      :trades, :book                 feed
```

- **The catalog is the shared one** (D317, D365): Spot, "USDT and USDC
  futures" and "Inverse futures", trading symbols only, linear and inverse
  read a thousand a page by Bybit's cursor; spot answers whole.
- **Intervals** are this application's names (`1m` … `1M`), sent as Bybit's
  (`1` … `M`); Bybit has no `1s`, `8h` or `3d`.
- **Volumes keep one meaning.** `volume` is the base asset's and
  `quote_volume` the quote asset's. Inverse counts `volume` in USD (contracts
  of one USD) and `turnover` in the coin, so there the two are swapped —
  exact, nothing divided, as D321 has it.
- **Tickers** fill symbol, last price, price change (last less the price a
  day ago), its percent (Bybit's fraction moved two places, exact), open,
  high, low, volume and quote volume.
- **Symbols** say base, quote, status, price step, quantity step (spot's base
  precision) and minimum notional (spot's minimum order amount); futures add
  Bybit's contract type, the delivery (empty for a perpetual) and the listing
  time.
- **Candles** fill open and close time, open, high, low, close, the two
  volumes and `closed`: the close time is the next candle's open less a
  millisecond, a month's by the calendar. They are read newest first a
  thousand a request, or forwards from a time, to the depth of ten thousand.
- **Trades are the newest Bybit answers** — 60 on spot, 1,000 on linear and
  inverse — read whole and sorted and filtered here by any column. `id` is
  Bybit's `execId`, text; `buyer_is_maker` is true when the taker sold.
- **The book** is read to the asked depth exactly, up to 1,000 a side.

Known deviations:

- **Trades go no further back than Bybit's newest.** `recent-trade` pages
  nothing; BTCUSDT's thousand on linear is about thirty seconds. Bybit's
  history is published as daily files, not an API.
- **A ticker has no weighted price, trade count or open and close times,
  and a candle no trade count or taker volumes**: Bybit does not send them,
  and the columns are left out rather than empty.

Spec: [A Bybit source, and what exchanges share](../../decisions/2026-11-22-bybit-source-design.md)

## D430. The Exchange section, the connection's own use as metrics, symbols found

- **Exchange** (`bybit/reports.py`) is the shared section (D425) in Bybit's
  words: **Status** (the endpoint, each market's answer; Bybit has no system
  status on public paths), **Clock** (`market/time` of each market), **Rate
  limit** (one budget for all markets, said once, in five-second windows),
  **Markets**.
- **Metrics** are the shared ones: `weight` labelled `address`, as one budget
  is spent by all, and `latency` and `reachable` per market; the preset is
  `bybit-connection`.
- **Search** reads the kept symbol lists, and `enumerate_names` gives every
  trading symbol of the three markets, scoped by market.
- **The Markets folder** (D365) lists each market's symbols as their market
  views.

Spec: [A Bybit source, and what exchanges share](../../decisions/2026-11-22-bybit-source-design.md)

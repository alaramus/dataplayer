# Market data shared by exchanges

For changing what every exchange source has in common — the catalog of
markets and symbols, the columns of a feed, the rate limit's ceiling, the
Exchange reports, metrics, search, the live view's socket — or for adding an
exchange. Each exchange's own file says what is its own:
[binance.md](binance.md). The contract every source
keeps is in [contract.md](contract.md).

Decisions here: D425.

## D425. A shared layer of market data, each exchange's own client under it

`app/adapters/market/`, cut from Binance when Bybit came, the second use:

| Module | What it holds |
| --- | --- |
| `values.py` | decimals as the exchange's text, times as moments in UTC, contracts' worth (D321) |
| `shape.py` | `Market` as the shared code reads one, `Symbol`, the interval names |
| `budget.py` | the rate limit as a mechanism: a limit over a window, a weight, the exchange's own count where it reports one, the 80% ceiling, a hold |
| `session.py` | `MarketSession`: one client a connection in the resource store, each market's budget, the symbol list kept an hour, the tickers ten seconds, a ping of every market, the check; `Kept` with the live streams |
| `catalog.py` | ids, nodes and `Place` (D317), the Markets folder (D365), the account's nodes (D322) |
| `columns.py` | each feed's columns: one name and type for one meaning |
| `feeds.py` | tickers and symbols read whole, the book by depth and side |
| `reports.py` | the Exchange section and its readers of status, clock, rate limit and markets (D320) |
| `metrics.py`, `search.py` | weight, latency and reachable per market; symbols found from the kept list |
| `stream.py` | `MarketStream`, one upstream socket and its watchers; `websockets` is imported here alone |
| `live.py` | a watch's frame: streams first, then the snapshot, then batches (D323) |
| `adapter.py` | `MarketAdapter`: listing, the path to a node, which feed a node reads, export, the watch's checks; `MarketReading` |

- **An exchange overrides, the frame stays.** Its session says its hosts,
  weights, the count it reports, how an answer is refused, how its symbols
  and tickers are read, its clock, and how a request is signed — the hook a
  key's round uses (D322). Its adapter says how candles, trades and the book
  are read, the tickers' columns it fills, what it watches and how a link
  reads on. Its reports and its metrics preset are named in its own words.
- **One column, one meaning.** `volume` is the base asset's and
  `quote_volume` the quote asset's on every market of every exchange; an
  exchange that counts in contracts or swaps the two says so in its rows,
  not in the columns. A column an exchange has no value for is left out with
  `only`, never filled with nothing.
- **A market is what the shared code reads of it**: its key, title,
  intervals, whether it is futures, whether its symbols say what a contract
  is worth, its deepest book and the depth asked for a number of levels.
  `Place` carries the exchange's own market, so its code reads its own
  fields without asking which.
- **The ceiling is a share of a window.** Binance's window is the minute it
  counts by and its share 80%; an exchange whose window rolls counts in
  windows from their start at a share that keeps any two side by side under
  80% (D426).
- **A stream is kept by what it is told**: the address and the greeting
  together, so two symbols on one address are two sockets.
- **Words are the exchange's.** The shared session says its refusals with
  the exchange's sentences (`Words`), so a person reads "Bybit", not "the
  exchange".

Known deviations:

- **The trades' columns differ between exchanges**: Binance's are aggregated
  trades with numeric ids and the first and last trade they hold; Bybit's
  ids are text. Both keep `id`, `price`, `quantity`, `time` and
  `buyer_is_maker`.
- **Binance's tests patch the stream's `connect` in the shared module**, as
  that is where it is now imported.

Spec: [A Bybit source, and what exchanges share](../../decisions/2026-11-22-bybit-source-design.md)

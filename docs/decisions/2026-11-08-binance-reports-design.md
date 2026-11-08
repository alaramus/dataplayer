# Binance's reports, metrics, search and guide

Decision D320. The third slice of the Binance source (D316–D319): what the
connection says about itself, what it measures, how its symbols are found,
and its page of the user's guide in every language. On the branch
`binance-adapter`.

## Reports

A section **Exchange** first at the top, as Kafka's Cluster and ZooKeeper's
own section are (D310, D301), each report setting-and-value rows:

- **Status**: Binance's system status (normal or maintenance), the endpoint
  in use, and each market reached or not.
- **Clock**: each market's server time, this server's, and the difference.
  A difference over a second is said, since time ranges sent to Binance are
  this server's times.
- **Rate limit**: per market, the limit, the weight used in the current
  minute as last read, the 80% ceiling (D316), and whether a 429 or 418
  holds the market and until when.
- **Markets**: per market, symbols trading, quote assets, and when the
  symbol list was read.

`sapi/v1/system/status` is on the main host only; on another endpoint the
status says it is not known rather than failing the report.

## Metrics

Polled as other connections are (D127), one sample a market:

- **Weight used**, the last minute's, and the ceiling as a line to read it
  against;
- **Latency** of the `time` request;
- **Reachable**, one or nought.

A preset draws them. A metric is about the connection, not the market:
prices belong in a pipeline's table, which a dashboard already reads.

## Search

The catalog's search (D76) matches a symbol by name and by its base and quote
assets, in both markets: "btc" finds BTCUSDT, ETHBTC and the BTC quote
folder. Names come from the kept symbol list, so a search costs no request.
The owner may keep the names for the search over everything (D212), as
Kafka's topics are kept; a symbol list of a few thousand fits its bounds.

## The guide

`source-binance.md` in all eight languages: what can be seen (markets,
tickers, symbols, candles, trades, the order book), what can be changed
(nothing), reading on in a pipeline, the rate limit and what a 429 or ban
means, and the three endpoints with when to choose which. Slice 1 wrote the
English and Russian pages; this slice adds the six others and the sections
the later slices made true.

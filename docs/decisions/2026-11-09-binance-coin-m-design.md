# Binance's COIN-M futures

Decision D321. A third market of the Binance source (D316–D320), next to spot
and USDⓈ-M futures, with the same nodes and rows.

## What COIN-M is

Futures settled in the coin rather than in a stablecoin: `BTCUSD_PERP`,
`ETHUSD_250926`. Binance serves them from `dapi.binance.com` under
`/dapi/v1`, in the same shapes as USDⓈ-M: `exchangeInfo`, `ticker/24hr`,
`klines`, `aggTrades`, `depth`, `ping`, `time`. The limit is 2400 weight a
minute and the weights are USDⓈ-M's. Trades answer two days back only, with
the same -4166 refusal. The testnet serves it from
`testnet.binancefuture.com`; the market-data endpoint has no host of its own
for futures, so it uses the main one, as it already does for USDⓈ-M.

All of this was checked against the live API when the slice was written.

## Contracts, not coins

COIN-M counts in contracts: a BTC contract is worth 100 USD, any other 10
USD, given per symbol as `contractSize`. Binance's `volume` is a count of
contracts, and the base asset's volume is beside it as `baseVolume` (tickers)
or column 7 (candles). There is no quote volume at all.

Rejected: showing COIN-M's own columns (contracts, base volume). A chart or a
pipeline that reads `volume` and `quote_volume` of a spot symbol would read
something else on a COIN-M one, and sorting tickers by quote volume — how the
other markets open — would have nothing to sort by.

Taken: **the columns keep one meaning across markets.** `volume` is in the
base asset and `quote_volume` in the quote asset (USD) everywhere. On COIN-M
the first is Binance's base volume and the second the contracts times the
contract size, which is exact because the size is a whole number of USD. The
same for the taker's volumes of a candle. The symbols list on COIN-M gains a
`contract_size` column.

A trade's and an order book level's `quantity` stay in contracts, as Binance
gives them: turning them into the base asset divides by the price, which is
not exact, and those rows have no second column to hold both. This is a known
deviation, said in the guide.

## Catalog

`coinm` after `usdm` at the root, holding Tickers, Symbols and one quote
asset, USD. Everything else — symbol nodes, candle intervals (no `1s`, as on
USDⓈ-M), reports, metrics, search, reading on — iterates the markets and
needed no change of its own.

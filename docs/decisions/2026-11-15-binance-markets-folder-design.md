# Binance's Markets folder

Decision D365. A second way in to a symbol's market view (D323), beside the
walk through a market and a quote asset (D317).

## The problem

The chart of a symbol lay four levels down: a market, a quote asset, the
symbol, its Market node. To look at one chart a person opened three folders
and found the symbol among hundreds. The chart is what most people come to
Binance's source for, so it should be the shortest way in.

## What was taken

A folder, **Markets**, at the top of the connection beside Spot, USDⓈ-M and
COIN-M. It holds a folder per market, and each lists that market's trading
symbols flat; each row is the symbol's market view and opens as it, at once.

- **A row is a `feed` node of the `market` feed**, not a `symbol`. A `symbol`
  is a container to walk into (D317); here nothing is below the row, and the
  candles, trades and order book of the symbol stay where they were.
- **One name on several markets is a row in each market's folder**, so a row
  needs no market in its name. Rows are ordered by symbol.
- **Node ids** are `markets:<market>` and `markets:<market>:<symbol>`. The walk's ids are not reused:
  one id under two parents breaks a tree keyed by id and the path shown to a
  node.
- **The same checks as before**: a symbol is looked up among the market's
  trading symbols before anything is asked of Binance, and a live watch of a
  row is a watch of that symbol's Market node.

## Rejected

- **The walk's Market nodes listed under a second parent.** Same id twice.
- **Only spot.** The futures charts are the same screen; leaving them out makes
  the folder a surprise in the one place it is not meant to be one.
- **One flat list of all three markets**, the market in each name. First
  taken, then given up: a few thousand rows was too long to scroll.

## Known cost

Spot's folder is about two thousand rows in one level. The catalog sends a level whole and the tree shows it whole, as
a quote asset's already does; finding one row is the catalog's search, which
reads the connection's kept names (D320). A level split into pages would help
every source and belongs to the catalog's contract, not to this folder.

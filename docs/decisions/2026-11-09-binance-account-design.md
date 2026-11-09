# A Binance key and the account it reads

Decision D322. The Binance source (D316–D321) read public data only. A key
lets it read the account the key belongs to: balances, futures positions,
orders, the account's own trades, and the wallet's deposits and withdrawals.
Nothing is ever sent that would change anything.

## A key is an endpoint of its own

`BinanceOptions` is a union on `endpoint`. A key is added as two more
members, **Binance, with an API key** (`binance_key`) and **Testnet, with an
API key** (`testnet_key`), each with `api_key` and `api_secret` as
`SecretStr`, rather than as optional fields on the existing members. The
reason is Redis's (D16): a `SecretStr | None` is not recognised as a secret
by the schema split (D4), and a form whose key fields half its users leave
empty asks for nothing useful. A key changes who asks, not where, so
`HOSTS_OF` maps both keyed endpoints to the hosts of the plain ones. The
market-data endpoint takes no key: it serves public data alone.

Both are secret: the API key is not the one that signs, but with the secret
it is the whole credential, and Binance lists it beside the account.

## Signing

A request of the account carries `timestamp` and `recvWindow` (10 s) and an
HMAC-SHA256 of its query string under the secret, with the key in the
`X-MBX-APIKEY` header (`BinanceSession.signed`). The timestamp is this
server's clock plus Binance's offset, measured from `time` before the first
signed request of a market and again after an hour. A `-1021` (time outside
the window) measures it again and sends once more; a second `-1021` is a
configuration failure in words. This is the one place a request is sent
again: what was wrong was the clock, not the request. A refused key (`-2014`,
`-2015`, `-1022`, `-2008`, or 401) is `auth`, worded without the key.

The weight table gains the account's paths, from Binance's documentation.

## What a key may do

Binance answers `GET /sapi/v1/account/apiRestrictions` on the main hosts: a
flag each for reading, trading spot and margin, futures, margin borrowing,
options, withdrawals and two kinds of transfer, and whether the key is
limited to listed addresses.

The check asks it after pinging the markets:

- No reading: the check fails, `auth`.
- Reading and anything more: the check **passes**, and says the key may also
  trade or move money, and that a key that can only read is safer.

Rejected: refusing such a key. The owner of the key decides what it is for,
and DataPlayer sends nothing that changes anything whatever the key allows;
the warning is what the owner needs to decide. The testnet has no such path,
so a testnet key is only tried, by reading the spot account; its money is of
no worth.

A report **API key** in the Exchange section says the same flags, whether the
key is limited to addresses, and when it was made. It exists only on a keyed
connection.

## Catalog

Only with a key. Each market gains an **Account** folder after Tickers and
Symbols:

```
spot:account              Balances, Open orders, Deposits, Withdrawals
usdm:account, coinm:account   Balances, Positions, Open orders
spot:symbol:BTCUSDT       … My orders, My trades after Order book
```

Deposits and Withdrawals are the wallet's, read from `sapi` on the spot host,
and only on the main hosts: the testnet has no wallet. Every account node is
a `feed` with a new `FeedName`; a keyless connection refuses all of them as
nodes that do not exist.

## Rows

Every account list is short or cut by Binance itself, so each is read whole
and sorted and filtered here by any column, as the market's lists are:

- **Balances**: spot `asset, free, locked, total`, held ones only
  (`omitZeroBalances`); futures `asset, wallet_balance, unrealized_pnl,
  margin_balance, available_balance`, those with a balance.
- **Positions**: `symbol, side, amount, entry_price, mark_price,
  unrealized_pnl, liquidation_price, notional, update_time`, open ones only.
  USDⓈ-M uses `/fapi/v3/`; COIN-M answers every symbol and the empty ones are
  left out.
- **Open orders** of the whole market, **My orders** of a symbol (the newest
  thousand): `order_id, symbol, side, type, status, price, quantity,
  executed, average_price, stop_price, time_in_force, time, update_time`.
- **My trades** of a symbol (the newest thousand): `id, order_id, side,
  price, quantity, quote_quantity, commission, commission_asset,
  realized_pnl, is_maker, time`. On COIN-M `quote_quantity` is the contracts'
  worth, as D321 has it.
- **Deposits** and **Withdrawals** (Binance's last ninety days): id, coin,
  network, amount, fee, status in Binance's words, transaction id, address,
  times. A withdrawal's times are UTC text in Binance's answer and become
  times here.

## Reading on

**My trades** can start a pipeline's link that reads on (D319): by id from
`fromId`, the newest id plus one as the line, the earliest the first own
trade Binance still answers. Their ids are the symbol's trade ids, far apart,
so the span's count is the most there can be. A table the link makes is keyed
on `id`.

## Known deviations

- **A page of orders or own trades is one request**, the newest thousand;
  USDⓈ-M and COIN-M answer the last seven days unless asked otherwise. Deeper
  history waits for a reason.
- **One key for every market.** On the main hosts one key reads spot and
  futures. The testnet issues separate keys for spot and futures; a
  connection holds one, so the other market refuses it in words.
- **Withdrawal history weighs on Binance's per-account limit**, which is not
  counted here; only the address's weight is.

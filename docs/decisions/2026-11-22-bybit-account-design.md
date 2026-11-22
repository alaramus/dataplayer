# A Bybit key and the unified account it reads

Decision D431. The round after Bybit's public data (D426–D430), as Binance's
key followed its market data (D322).

## Facts checked

From Bybit's v5 documentation on 2026-11-22. No real key was used: every
path below is tested against a fake that checks the signature as Bybit
documents it.

- **Signing a GET**: headers `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP` (ms),
  `X-BAPI-RECV-WINDOW` (default 5,000 ms) and `X-BAPI-SIGN`, the lowercase hex
  HMAC-SHA256 of timestamp + key + window + query string, nothing between.
  The time must lie within `server - window <= t < server + 1000`.
- **Refusals**: 10002 time outside the window; 10003 unknown key; 10004 bad
  signature; 10005 permission denied; 10007 authentication failed; 10010
  address not the key's; 33004 key expired; HTTP 401 a wrong key.
- **The key**: `GET /v5/user/query-api` answers any key: `readOnly` (1 read
  only, 0 read and write), `permissions` by group (`ContractTrade`, `Spot`,
  `Wallet`, `Options`, `Derivatives`, `Exchange`, `Earn` …), `ips`,
  `createdAt`, `expiredAt` (the epoch for a key that does not expire).
- **The unified account**: `wallet-balance` takes `accountType=UNIFIED`
  only, one wallet for spot and futures. `position/list` (linear by
  `settleCoin`, up to 200 a page), `order/realtime` (open, 50 a page),
  `order/history` and `execution/list` (the last seven days unless a time is
  asked, seven days at most a request, 50 and 100 a page), deposits and
  withdrawals (the last thirty days, 50 a page; withdrawals for the main
  account's key only), each paged by `nextPageCursor`. Ids are text.
- **Limits** on these paths are the account's, per second (10 to 50), apart
  from the address's 600 in five seconds.

## D431. A key reads the unified account, signed the shared way

- **Endpoints of their own**, `bybit_key` and `testnet_key`, with the key
  and secret as `SecretStr` — the shared `Keyed` model that Binance's keyed
  endpoints now use too.
- **Signing is the shared session's**: Binance's way of measuring the clock,
  sending once more on a stale time and saying so in the exchange's words
  moves into `MarketSession.signed` on this second use; each exchange says
  how a request is signed (`signed_request`) and where its clock is.
- **The check** asks `query-api`; a key that is not read-only passes and is
  said to do more, as Binance's (D322), the verdict now shared
  (`key_checked`).
- **The catalog** is the shared one: an Account folder per market and a
  symbol's My orders and My trades. Balances is the unified wallet in every
  market; positions on linear and inverse; open orders in each; deposits and
  withdrawals on spot.
- **Rows**: each list read whole, page by page to twenty pages, and sorted
  and filtered here; on inverse an own trade's quantity and its worth are
  swapped as D427's volumes are.
- **My trades read on by time**, as trades are (D428), a window of seven
  days a block, the made table keyed on `id`.
- **A report**, API key, says what Bybit lets the key do.

Rejected: **asking each market's own wallet** — Bybit's classic accounts are
being retired and its API now answers `UNIFIED` only; **showing Balances
once, outside the markets** — the shared catalog has an Account per market,
and a person looking for USDT under futures finds it there.

## Not done

- **Classic (non-unified) accounts** and the funding wallet.
- **Bybit's per-account limits** are not counted, only the address's.
- **Orders and own trades past seven days** unless a link reads them on.

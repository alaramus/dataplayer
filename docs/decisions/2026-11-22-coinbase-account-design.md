# A Coinbase key and the account it reads

Decision D443. The Coinbase Exchange source (D438–D442) reads market data
from the exchange; this adds the owner's account. Coinbase has two kinds of
key: Coinbase Exchange's (a key, a secret and a passphrase, for the
institutional exchange) and the Coinbase Developer Platform's (a key name and
an EC private key, for Advanced Trade on an ordinary Coinbase account). The
second is what an ordinary Coinbase user has, so it is the one taken.

## Facts checked

Against Coinbase's developer documentation and its own Python SDK
(`coinbase-advanced-py`), on 2026-11-22.

- **Authentication.** `Authorization: Bearer <JWT>`, ES256, header `kid` the
  key's name and a random `nonce`; claims `sub` the key's name, `iss`
  `"cdp"`, `nbf` now, `exp` now plus 120 seconds, `uri` `"GET
  api.coinbase.com/api/v3/brokerage/accounts"`. The SDK builds `uri` from the
  path alone; the query goes with the request only. A token for every
  request.
- **Keys.** Names are `organizations/{org}/apiKeys/{id}`; the private key a
  PEM `EC PRIVATE KEY`. Coinbase's App APIs take ES256 only ("Ed25519 (EdDSA)
  keys are NOT supported"), and a key must be made with ECDSA.
- **Paths**, under `https://api.coinbase.com/api/v3/brokerage`:
  `accounts` (up to 250 a page, `cursor`, `has_next`; `currency`,
  `available_balance` and `hold` as `{value, currency}`),
  `orders/historical/batch` (`order_status`, `product_ids`, `cursor`,
  `has_next`; the order's price and size inside `order_configuration`),
  `orders/historical/fills` (`product_ids`, `start_sequence_timestamp`,
  `end_sequence_timestamp` in RFC 3339, `cursor`, no `has_next`;
  `size_in_quote` a boolean, `liquidity_indicator` MAKER or TAKER),
  `key_permissions` (`can_view`, `can_trade`, `can_transfer`,
  `portfolio_type`). Times are RFC 3339, to the nanosecond.
- **Not confirmed**: a per-second limit for these paths, and the body of a
  refusal; a 401 or 403 is taken as the key refused.

## D443

The key is an endpoint of its own on the main hosts (the sandbox has no
Advanced Trade), its name and private key `SecretStr` in the shared `Keyed`.
Requests are signed by the shared session's hook with a fresh token each;
they go to Coinbase's own host and spend the exchange address's budget. A
pasted key is read whatever happened to its line breaks. The check reads
`key_permissions` and says a key that may trade or move money. Spot holds
the account's balances and open orders; a product its orders and fills, the
fills read on by time.

"""A Bybit that answers from memory, for tests that must not reach the real one.

Bybit refuses addresses in the United States, where CI runs, so the adapter
is tested against this instead: the paths, parameters, shapes and refusals
the adapter relies on, checked against the real v5 API when the adapter was
written (D426). One trade a second and one candle an hour, counted back
from now; every answer HTTP 200 with a `retCode`, as Bybit's are.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.adapters.bybit import session as bybit_session

API_KEY = "fake-bybit-key"
API_SECRET = "fake-bybit-secret"
DAY_MS = 86_400_000
# Ages of the key's own trades of a symbol, in hours back from now.
MY_TRADE_HOURS = (1, 2, 3, 30, 200)
HOUR_MS = 3_600_000
SECOND_MS = 1000
CANDLES = 3000
TRADES = 5000

SPOT_SYMBOLS = [
    ("BTCUSDT", "BTC", "USDT", "Trading"),
    ("ETHUSDT", "ETH", "USDT", "Trading"),
    ("ETHBTC", "ETH", "BTC", "Trading"),
    ("GONEUSDT", "GONE", "USDT", "Closed"),
]

# Linear: name, base, quote, status, contract type, delivery.
LINEAR_SYMBOLS = [
    ("BTCUSDT", "BTC", "USDT", "Trading", "LinearPerpetual", 0),
    ("BTCUSDT-27NOV26", "BTC", "USDT", "Trading", "LinearFutures", 1_795_766_400_000),
    ("BTCPERP", "BTC", "USDC", "Trading", "LinearPerpetual", 0),
    ("NEWUSDT", "NEW", "USDT", "PreLaunch", "LinearPerpetual", 0),
]

INVERSE_SYMBOLS = [
    ("BTCUSD", "BTC", "USD", "Trading", "InversePerpetual", 0),
    ("BTCUSDZ26", "BTC", "USD", "Trading", "InverseFutures", 1_798_185_600_000),
]


@dataclass
class Asked:
    host: str
    path: str
    params: dict[str, str]


@dataclass
class FakeBybit:
    now_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    asked: list[Asked] = field(default_factory=list)
    # How many trades there are; raised by a test to make new ones.
    trades: int = TRADES
    # Answer every request with this status and body instead.
    refuse: tuple[int, dict[str, Any]] | None = None
    # How many symbols a page of linear instruments holds, to page by cursor.
    page: int = 2
    # How many records a page of a signed list holds, whatever was asked.
    private_page: int = 2
    # What Bybit says of the key: 1 read only, 0 read and write.
    read_only: int = 1
    # How many signed requests to refuse as carrying a stale time.
    stale: int = 0
    # The signed paths answered.
    signed: list[str] = field(default_factory=list)

    @property
    def last_trade_ms(self) -> int:
        return self.now_ms - self.now_ms % 1000

    def add_trades(self, count: int) -> None:
        """New trades, a second apart, made after the old ones and now."""
        self.trades += count
        self.now_ms += count * SECOND_MS

    def trade_ms(self, trade_id: int) -> int:
        return self.last_trade_ms - (self.trades - trade_id) * SECOND_MS

    @property
    def first_open_ms(self) -> int:
        return self.now_ms - self.now_ms % HOUR_MS - (CANDLES - 1) * HOUR_MS

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        return self.answer

    def answer(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        params = dict(parse_qsl(url.query))
        self.asked.append(Asked(url.netloc, url.path, params))
        if self.refuse is not None:
            status, body = self.refuse
            return httpx.Response(status, json=body)
        if "X-BAPI-SIGN" in request.headers:
            result = self._signed(request, url.path, url.query, params)
        else:
            result = self._result(url.path.removeprefix("/v5/market/"), params)
        if isinstance(result, tuple):
            code, message = result
            body: dict[str, Any] = {"retCode": code, "retMsg": message, "result": {}}
        else:
            body = {"retCode": 0, "retMsg": "OK", "result": result}
        body["time"] = self.now_ms
        return httpx.Response(200, content=json.dumps(body).encode())

    # --- the account of one fake key ------------------------------------------

    def _signed(
        self, request: httpx.Request, path: str, query: str, params: dict[str, str]
    ) -> Any:
        headers = request.headers
        if headers.get("X-BAPI-API-KEY") != API_KEY:
            return 10003, "API key is invalid."
        expected = hmac.new(
            API_SECRET.encode(),
            (
                headers.get("X-BAPI-TIMESTAMP", "")
                + API_KEY
                + headers.get("X-BAPI-RECV-WINDOW", "")
                + query
            ).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(headers.get("X-BAPI-SIGN", ""), expected):
            return 10004, "Error sign, please check your signature generation."
        if self.stale > 0:
            self.stale -= 1
            return 10002, "The request time exceeds the time window range."
        self.signed.append(path)
        category = params.get("category", "")
        if path == "/v5/user/query-api":
            trading = [] if self.read_only else ["Order", "Position"]
            return {
                "readOnly": self.read_only,
                "permissions": {
                    "ContractTrade": trading,
                    "Spot": [] if self.read_only else ["SpotTrade"],
                    "Wallet": [],
                },
                "ips": ["203.0.113.7"],
                "createdAt": "2026-01-02T03:04:05Z",
                "expiredAt": "1970-01-01T00:00:00Z",
                "secret": "",
            }
        if path == "/v5/account/wallet-balance":
            if params.get("accountType") != "UNIFIED":
                return 10001, "accountType only support UNIFIED."
            coins = [
                self._coin("BTC", "0.5", "0.1", "30000"),
                self._coin("USDT", "100", "0", "100"),
                self._coin("ETH", "0", "0", "0"),
            ]
            return {"list": [{"accountType": "UNIFIED", "coin": coins}]}
        if path == "/v5/position/list":
            if category == "linear" and "settleCoin" not in params:
                return 10001, "symbol or settleCoin is required"
            items = {
                ("linear", "USDT"): [
                    self._position("BTCUSDT", "Buy", "2"),
                    self._position("ETHUSDT", "", "0"),
                ],
                ("linear", "USDC"): [],
                ("inverse", ""): [self._position("BTCUSD", "Sell", "100")],
            }[(category, params.get("settleCoin", ""))]
            return self._page(items, params)
        if path == "/v5/order/realtime":
            if category == "linear" and "settleCoin" not in params:
                return 10001, "symbol or settleCoin is required"
            return self._page([self._order("o-1", "New")], params)
        if path == "/v5/order/history":
            orders = [self._order(f"o-{one}", "Filled") for one in (3, 2, 4)]
            return self._page(orders, params)
        if path == "/v5/execution/list":
            return self._executions(category, params)
        if path == "/v5/asset/deposit/query-record":
            deposit = {
                "id": "d1",
                "coin": "BTC",
                "chain": "BTC",
                "amount": "0.5",
                "txID": "tx1",
                "status": 3,
                "toAddress": "bc1q",
                "successAt": str(self.now_ms - HOUR_MS),
            }
            return self._page([deposit], params, rows="rows")
        if path == "/v5/asset/withdraw/query-record":
            withdrawal = {
                "withdrawId": "w1",
                "coin": "USDT",
                "chain": "ETH",
                "amount": "100",
                "withdrawFee": "1",
                "status": "success",
                "txID": "tx2",
                "toAddress": "0xabc",
                "createTime": str(self.now_ms - 2 * HOUR_MS),
                "updateTime": str(self.now_ms - HOUR_MS),
            }
            return self._page([withdrawal], params, rows="rows")
        return 10001, "?"

    def _page(
        self, items: list[dict[str, Any]], params: dict[str, str], rows: str = "list"
    ) -> dict[str, Any]:
        """A page of a signed list, `private_page` long, by an offset cursor."""
        start = int(params.get("cursor") or "0")
        end = start + self.private_page
        cursor = str(end) if end < len(items) else ""
        return {rows: items[start:end], "nextPageCursor": cursor}

    def _coin(self, coin: str, wallet: str, locked: str, usd: str) -> dict[str, Any]:
        return {
            "coin": coin,
            "walletBalance": wallet,
            "equity": wallet,
            "locked": locked,
            "unrealisedPnl": "0",
            "usdValue": usd,
        }

    def _position(self, symbol: str, side: str, size: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "side": side,
            "size": size,
            "avgPrice": "70000",
            "markPrice": "74000",
            "unrealisedPnl": "8000",
            "liqPrice": "",
            "positionValue": "148000",
            "updatedTime": str(self.now_ms),
        }

    def _order(self, order_id: str, status: str) -> dict[str, Any]:
        filled = status == "Filled"
        return {
            "orderId": order_id,
            "symbol": "BTCUSDT",
            "side": "Buy",
            "orderType": "Limit",
            "orderStatus": status,
            "price": "100.5",
            "qty": "2",
            "cumExecQty": "2" if filled else "0",
            "avgPrice": "100.4" if filled else "",
            "triggerPrice": "0",
            "timeInForce": "GTC",
            "createdTime": str(self.now_ms - int(order_id[2:]) * HOUR_MS),
            "updatedTime": str(self.now_ms),
        }

    def my_trade_ms(self, hours: int) -> int:
        return self.now_ms - hours * HOUR_MS

    def _executions(self, category: str, params: dict[str, str]) -> Any:
        """The key's trades, newest first, seven days at most a request."""
        end = int(params.get("endTime") or self.now_ms)
        start = int(params.get("startTime") or end - 7 * DAY_MS)
        if end - start > 7 * DAY_MS:
            return 181010, "The time range cannot exceed 7 days"
        inverse = category == "inverse"
        found = [
            {
                "execId": f"e-{hours}",
                "orderId": f"o-{hours}",
                "symbol": params.get("symbol"),
                "side": "Buy",
                "execPrice": "100.5",
                "execQty": "300" if inverse else "3",
                "execValue": "0.003" if inverse else "301.5",
                "execFee": "0.001",
                "feeCurrency": "USDT",
                "isMaker": True,
                "execTime": str(self.my_trade_ms(hours)),
            }
            for hours in MY_TRADE_HOURS
            if start <= self.my_trade_ms(hours) <= end
        ]
        return self._page(found, params)

    def _rows(self, category: str) -> list[tuple[Any, ...]]:
        return {
            "spot": SPOT_SYMBOLS,
            "linear": LINEAR_SYMBOLS,
            "inverse": INVERSE_SYMBOLS,
        }[category]

    def _result(self, name: str, params: dict[str, str]) -> Any:
        if name == "time":
            return {
                "timeSecond": str(self.now_ms // 1000),
                "timeNano": str(self.now_ms * 1_000_000),
            }
        category = params.get("category", "linear")
        if name == "instruments-info":
            return self._instruments(category, params)
        if name == "tickers":
            return self._tickers(category)
        known = {row[0] for row in self._rows(category) if row[3] == "Trading"}
        if params.get("symbol") not in known:
            if category == "spot":
                return 10001, "Not supported symbols"
            return 10001, "params error: Symbol Is Invalid"
        if name == "kline":
            return self._klines(category, params)
        if name == "recent-trade":
            return self._trades(category, params)
        if name == "orderbook":
            return self._book(params)
        return 10001, "?"

    def _instruments(self, category: str, params: dict[str, str]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for row in self._rows(category):
            if category == "spot":
                name, base, quote, status = row
                items.append(
                    {
                        "symbol": name,
                        "baseCoin": base,
                        "quoteCoin": quote,
                        "status": status,
                        "lotSizeFilter": {
                            "basePrecision": "0.000001",
                            "minOrderAmt": "5",
                        },
                        "priceFilter": {"tickSize": "0.1"},
                    }
                )
                continue
            name, base, quote, status, contract, delivery = row
            items.append(
                {
                    "symbol": name,
                    "contractType": contract,
                    "status": status,
                    "baseCoin": base,
                    "quoteCoin": quote,
                    "launchTime": "1585526400000",
                    "deliveryTime": str(delivery),
                    "priceFilter": {"tickSize": "0.10"},
                    "lotSizeFilter": {"qtyStep": "0.001", "minNotionalValue": "5"},
                }
            )
        if category == "spot":
            # Spot pages nothing and ignores a cursor.
            return {"category": "spot", "list": items}
        start = int(params.get("cursor") or "0")
        end = start + self.page
        cursor = str(end) if end < len(items) else ""
        return {
            "category": category,
            "list": items[start:end],
            "nextPageCursor": cursor,
        }

    def _tickers(self, category: str) -> dict[str, Any]:
        found = []
        for index, row in enumerate(self._rows(category)):
            item = {
                "symbol": row[0],
                "lastPrice": f"{100 + index}.5",
                "prevPrice24h": "100",
                "price24hPcnt": "0.005",
                "highPrice24h": "103",
                "lowPrice24h": "99",
                # The second symbol trades most.
                "volume24h": "9000" if index == 1 else f"{index}.5",
                "turnover24h": "900000" if index == 1 else f"{index}.25",
            }
            found.append(item)
        return {"category": category, "list": found}

    def _klines(self, category: str, params: dict[str, str]) -> Any:
        assert params["interval"] == "60", "the fake knows hourly candles only"
        limit = min(int(params.get("limit", "200")), 1000)
        opens = [self.first_open_ms + index * HOUR_MS for index in range(CANDLES)]
        if "start" in params:
            opens = [one for one in opens if one >= int(params["start"])]
        if "end" in params:
            opens = [one for one in opens if one <= int(params["end"])]
        # Bybit answers the first `limit` from a start, else the last ones,
        # newest first either way.
        opens = opens[:limit] if "start" in params else opens[-limit:]
        return {
            "symbol": params["symbol"],
            "category": category,
            "list": [
                [
                    str(one),
                    f"{100 + (one - self.first_open_ms) // HOUR_MS}",
                    "1.1",
                    "0.9",
                    "1",
                    "5",
                    "500",
                ]
                for one in reversed(opens)
            ],
        }

    def _trades(self, category: str, params: dict[str, str]) -> dict[str, Any]:
        ceiling = 60 if category == "spot" else 1000
        limit = min(
            int(params.get("limit", "60" if category == "spot" else "500")), ceiling
        )
        ids = list(range(1, self.trades + 1))[-limit:]
        return {
            "category": category,
            "list": [
                {
                    "execId": str(one) if category == "spot" else f"uuid-{one}",
                    "symbol": params["symbol"],
                    "price": f"{1000 + one}.5",
                    "size": "0.01",
                    "side": "Sell" if one % 2 == 0 else "Buy",
                    "time": str(self.trade_ms(one)),
                    "isBlockTrade": False,
                    "seq": str(10_000 + one),
                }
                for one in reversed(ids)
            ],
        }

    def _book(self, params: dict[str, str]) -> Any:
        limit = int(params.get("limit", "1"))
        if not 1 <= limit <= 1000:
            return 10001, "params error"
        return {
            "s": params["symbol"],
            "b": [[f"{100 - level / 100:.2f}", "1.5"] for level in range(limit)],
            "a": [[f"{100.01 + level / 100:.2f}", "2"] for level in range(limit)],
            "ts": self.now_ms,
            "u": 1,
        }


def install(monkeypatch: pytest.MonkeyPatch) -> FakeBybit:
    """A fake Bybit every new client of the source speaks to."""
    fake = FakeBybit()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(fake.handler()))

    monkeypatch.setattr(bybit_session, "make_client", client)
    return fake

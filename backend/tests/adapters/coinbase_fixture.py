"""A Coinbase Exchange that answers from memory, for tests that must not reach
the real one.

The paths, parameters, shapes and refusals the adapter relies on, checked
against the real Exchange API when the adapter was written (D438). One trade
a second numbered from one, one candle an hour counted back from now; candle
numbers and the clock as JSON numbers, as Coinbase sends them.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.adapters.coinbase import session as coinbase_session

HOUR_S = 3600
HOUR_MS = 3_600_000
KEY_NAME = "organizations/org-1/apiKeys/key-1"
_KEY = ec.generate_private_key(ec.SECP256R1())
# The key as Coinbase's developer platform hands it out.
PRIVATE_KEY = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
).decode()
# Ages of the key's own fills, in hours back from now.
MY_FILL_HOURS = (1, 2, 3, 30, 200)
CANDLES = 3000
TRADES = 5000

# Name, base, quote, status, trading disabled.
PRODUCTS = [
    ("BTC-USD", "BTC", "USD", "online", False),
    ("ETH-USD", "ETH", "USD", "online", False),
    ("ETH-BTC", "ETH", "BTC", "online", False),
    ("GONE-USD", "GONE", "USD", "delisted", True),
]


@dataclass
class Asked:
    host: str
    path: str
    params: dict[str, str]


@dataclass
class FakeCoinbase:
    now_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    asked: list[Asked] = field(default_factory=list)
    trades: int = TRADES
    refuse: tuple[int, str] | None = None
    # What the key may do beyond viewing.
    can_trade: bool = False
    # The paths a valid token was shown for.
    signed: list[str] = field(default_factory=list)

    @property
    def last_trade_ms(self) -> int:
        return self.now_ms - self.now_ms % 1000

    def add_trades(self, count: int) -> None:
        self.trades += count
        self.now_ms += count * 1000

    def trade_ms(self, trade_id: int) -> int:
        return self.last_trade_ms - (self.trades - trade_id) * 1000

    @property
    def first_open_s(self) -> int:
        now = self.now_ms // 1000
        return now - now % HOUR_S - (CANDLES - 1) * HOUR_S

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        return self.answer

    def answer(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        params = dict(parse_qsl(url.query))
        self.asked.append(Asked(url.netloc, url.path, params))
        if self.refuse is not None:
            status, message = self.refuse
            return httpx.Response(status, json={"message": message})
        if url.netloc == "api.coinbase.com":
            found = self._brokerage(request, url.path, params)
        else:
            found = self._result(url.path, params)
        if isinstance(found, tuple):
            status, message = found
            return httpx.Response(status, json={"message": message})
        if isinstance(found, str):
            return httpx.Response(200, content=found.encode())
        return httpx.Response(200, json=found)

    # --- Advanced Trade, for the one fake key (D443) ---------------------------

    def _brokerage(
        self, request: httpx.Request, path: str, params: dict[str, str]
    ) -> Any:
        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        try:
            header = jwt.get_unverified_header(bearer)
            claims = jwt.decode(
                bearer,
                _KEY.public_key(),
                algorithms=["ES256"],
                issuer="cdp",
                leeway=timedelta(seconds=5),
                options={"require": ["exp", "nbf", "sub", "uri"]},
            )
        except jwt.PyJWTError:
            return 401, "Unauthorized"
        if (
            header.get("kid") != KEY_NAME
            or not header.get("nonce")
            or claims["sub"] != KEY_NAME
            or claims["uri"] != f"GET api.coinbase.com{path}"
        ):
            return 401, "Unauthorized"
        self.signed.append(path)
        name = path.removeprefix("/api/v3/brokerage/")
        if name == "key_permissions":
            return {
                "can_view": True,
                "can_trade": self.can_trade,
                "can_transfer": False,
                "portfolio_uuid": "p-1",
                "portfolio_type": "DEFAULT",
            }
        if name == "accounts":
            accounts = [
                self._account("BTC", "0.4", "0.1"),
                self._account("USD", "100", "0"),
                self._account("ETH", "0", "0"),
            ]
            return self._page(accounts, params, "accounts", has_next=True)
        if name == "orders/historical/batch":
            orders = [
                self._order(
                    "o-1",
                    "OPEN",
                    {"limit_limit_gtc": {"base_size": "2", "limit_price": "100.5"}},
                ),
                self._order(
                    "o-2", "FILLED", {"market_market_ioc": {"quote_size": "50"}}
                ),
            ]
            if params.get("order_status") == "OPEN":
                orders = [one for one in orders if one["status"] == "OPEN"]
            if "product_ids" in params:
                orders = [
                    one for one in orders if one["product_id"] == params["product_ids"]
                ]
            return self._page(orders, params, "orders", has_next=True)
        if name == "orders/historical/fills":
            return self._page(self._fills(params), params, "fills", has_next=False)
        return 404, "NotFound"

    def _page(
        self,
        items: list[dict[str, Any]],
        params: dict[str, str],
        key: str,
        has_next: bool,
    ) -> dict[str, Any]:
        """One record a page, by an offset cursor, to read them page by page."""
        start = int(params.get("cursor") or "0")
        more = start + 1 < len(items)
        page: dict[str, Any] = {
            key: items[start : start + 1],
            "cursor": str(start + 1) if more else "",
        }
        if has_next:
            page["has_next"] = more
        return page

    def _account(self, currency: str, available: str, hold: str) -> dict[str, Any]:
        return {
            "uuid": f"a-{currency}",
            "currency": currency,
            "available_balance": {"value": available, "currency": currency},
            "hold": {"value": hold, "currency": currency},
            "active": True,
        }

    def _order(
        self, order_id: str, status: str, shape: dict[str, Any]
    ) -> dict[str, Any]:
        filled = status == "FILLED"
        return {
            "order_id": order_id,
            "product_id": "BTC-USD",
            "side": "BUY",
            "status": status,
            "order_type": "LIMIT" if "limit_limit_gtc" in shape else "MARKET",
            "order_configuration": shape,
            "filled_size": "0.5" if filled else "0",
            "average_filled_price": "100" if filled else "0",
            "created_time": "2026-11-20T10:00:00.123456789Z",
        }

    def my_fill_ms(self, hours: int) -> int:
        return self.now_ms - hours * HOUR_MS

    def _fills(self, params: dict[str, str]) -> list[dict[str, Any]]:
        def ms(text: str) -> int:
            return int(
                datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000
            )

        low = (
            ms(params["start_sequence_timestamp"])
            if "start_sequence_timestamp" in params
            else 0
        )
        high = (
            ms(params["end_sequence_timestamp"])
            if "end_sequence_timestamp" in params
            else self.now_ms + 1
        )
        found = []
        for hours in MY_FILL_HOURS:
            at = self.my_fill_ms(hours)
            if not low <= at < high:
                continue
            when = (
                datetime.fromtimestamp(at / 1000, tz=UTC)
                .isoformat()
                .replace("+00:00", "Z")
            )
            found.append(
                {
                    "entry_id": f"e-{hours}",
                    "trade_id": f"t-{hours}",
                    "order_id": f"o-{hours}",
                    "trade_time": when,
                    "price": "100.5",
                    "size": "2",
                    "commission": "0.1",
                    "product_id": params.get("product_ids"),
                    "liquidity_indicator": "MAKER",
                    "side": "SELL",
                    "size_in_quote": hours == 2,
                }
            )
        return list(reversed(found))

    def _result(self, path: str, params: dict[str, str]) -> Any:
        if path == "/time":
            # A JSON number, as Coinbase sends it.
            return f'{{"iso": "now", "epoch": {self.now_ms / 1000:.3f}}}'
        if path == "/products":
            return [
                {
                    "id": name,
                    "base_currency": base,
                    "quote_currency": quote,
                    "quote_increment": "0.01",
                    "base_increment": "0.00000001",
                    "min_market_funds": "1",
                    "status": status,
                    "trading_disabled": disabled,
                }
                for name, base, quote, status, disabled in PRODUCTS
            ]
        if path == "/products/stats":
            return {
                name: {
                    "stats_24hour": {
                        "open": "100",
                        "high": "103",
                        "low": "99",
                        "last": f"{100 + index}.5",
                        "volume": "9000" if index == 1 else f"{index}.5",
                    },
                    "stats_30day": {"volume": "1"},
                }
                for index, (name, *_) in enumerate(PRODUCTS)
            }
        parts = path.split("/")
        if len(parts) < 4 or parts[1] != "products":
            return 404, "NotFound"
        name, what = parts[2], parts[3]
        if name not in {row[0] for row in PRODUCTS if row[3] == "online"}:
            return 404, "NotFound"
        if what == "candles":
            return self._candles(params)
        if what == "trades":
            return self._trades(name, params)
        if what == "book":
            return self._book(params)
        if what == "stats":
            return {
                "open": "100",
                "high": "103",
                "low": "99",
                "last": "101",
                "volume": "7",
            }
        return 404, "NotFound"

    def _candles(self, params: dict[str, str]) -> Any:
        if params.get("granularity") not in {
            "60",
            "300",
            "900",
            "3600",
            "21600",
            "86400",
        }:
            return 400, "Unsupported granularity"
        assert params["granularity"] == "3600", "the fake knows hourly candles only"
        opens = [self.first_open_s + index * HOUR_S for index in range(CANDLES)]
        if "start" in params and "end" in params:
            start, end = int(params["start"]), int(params["end"])
            if (end - start) // HOUR_S + 1 > 300:
                return 400, "granularity too small for the requested time range"
            opens = [one for one in opens if start <= one <= end]
        else:
            opens = opens[-300:]
        rows = ",".join(
            f"[{one},0.9,1.1,{100 + (one - self.first_open_s) // HOUR_S},1.0,5.25]"
            for one in reversed(opens)
        )
        return f"[{rows}]"

    def _trade(self, trade_id: int) -> dict[str, Any]:
        at = datetime.fromtimestamp(self.trade_ms(trade_id) / 1000, tz=UTC)
        return {
            "trade_id": trade_id,
            "side": "buy" if trade_id % 2 == 0 else "sell",
            "size": "0.01000000",
            "price": f"{1000 + trade_id}.50000000",
            "time": at.isoformat().replace("+00:00", "Z"),
        }

    def _trades(self, name: str, params: dict[str, str]) -> Any:
        del name
        limit = int(params.get("limit", "1000"))
        if not 1 <= limit <= 1000:
            return 400, "Invalid limit"
        ids = list(range(1, self.trades + 1))
        if "after" in params:
            ids = [one for one in ids if one < int(params["after"])]
        return [self._trade(one) for one in reversed(ids[-limit:])]

    def _book(self, params: dict[str, str]) -> Any:
        level = params.get("level", "1")
        depth = 1 if level == "1" else 500
        return {
            "bids": [[f"{100 - step / 100:.2f}", "1.5", 1] for step in range(depth)],
            "asks": [[f"{100.01 + step / 100:.2f}", "2", 1] for step in range(depth)],
            "sequence": 1,
        }


def install(monkeypatch: pytest.MonkeyPatch) -> FakeCoinbase:
    fake = FakeCoinbase()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(fake.handler()))

    monkeypatch.setattr(coinbase_session, "make_client", client)
    return fake

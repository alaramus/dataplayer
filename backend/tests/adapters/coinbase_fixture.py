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
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.adapters.coinbase import session as coinbase_session

HOUR_S = 3600
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
        found = self._result(url.path, params)
        if isinstance(found, tuple):
            status, message = found
            return httpx.Response(status, json={"message": message})
        if isinstance(found, str):
            return httpx.Response(200, content=found.encode())
        return httpx.Response(200, json=found)

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

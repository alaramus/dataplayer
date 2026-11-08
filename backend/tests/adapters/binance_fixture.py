"""A Binance that answers from memory, for tests that must not reach the real one.

Binance refuses addresses in the United States, where CI runs, so the
adapter is tested against this instead: the paths, parameters, shapes,
weights and refusals the adapter relies on, checked against the real API
when the adapter was written (D316). One trade a minute and one candle an
hour, counted back from now.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.adapters.binance import session as binance_session

HOUR_MS = 3_600_000
MINUTE_MS = 60_000
TRADES = 5000
CANDLES = 3000
TWO_DAYS_MS = 2 * 86_400_000
PERPETUAL_DELIVERY = 4_133_404_800_000

SPOT_SYMBOLS = [
    ("BTCUSDT", "BTC", "USDT", "TRADING"),
    ("ETHUSDT", "ETH", "USDT", "TRADING"),
    ("币安人生USDT", "币安人生", "USDT", "TRADING"),
    ("ETHBTC", "ETH", "BTC", "TRADING"),
    ("GONEUSDT", "GONE", "USDT", "BREAK"),
]

FUTURES_SYMBOLS = [
    ("BTCUSDT", "BTC", "USDT", "TRADING", "PERPETUAL", PERPETUAL_DELIVERY),
    ("BTCUSDT_261225", "BTC", "USDT", "TRADING", "CURRENT_QUARTER", 1_798_185_600_000),
    ("OLDUSDT", "OLD", "USDT", "SETTLING", "PERPETUAL", PERPETUAL_DELIVERY),
]

SPOT_DEPTHS = {5, 10, 20, 50, 100, 500, 1000, 5000}
FUTURES_DEPTHS = {5, 10, 20, 50, 100, 500, 1000}


def _filters(price_step: str) -> list[dict[str, Any]]:
    return [
        {"filterType": "PRICE_FILTER", "tickSize": price_step},
        {"filterType": "LOT_SIZE", "stepSize": "0.00001000"},
        {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
    ]


@dataclass
class Asked:
    host: str
    path: str
    params: dict[str, str]


@dataclass
class FakeBinance:
    now_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    asked: list[Asked] = field(default_factory=list)
    # Weight already used this minute, as Binance would report it.
    used: int = 0
    # How many trades there are; raised by a test to make new ones.
    trades: int = TRADES
    # Answer every request with this status and headers instead.
    refuse: tuple[int, dict[str, str], dict[str, Any]] | None = None

    @property
    def last_trade_ms(self) -> int:
        return self.now_ms - self.now_ms % 1000

    def trade_ms(self, trade_id: int) -> int:
        return self.last_trade_ms - (self.trades - trade_id) * MINUTE_MS

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
            status, headers, body = self.refuse
            return httpx.Response(status, headers=headers, json=body)
        futures = url.path.startswith("/fapi/")
        name = url.path.split("/", 3)[3]
        body, weight = self._body(name, params, futures)
        self.used += weight
        headers = {"x-mbx-used-weight-1m": str(self.used)}
        if isinstance(body, tuple):
            status, payload = body
            return httpx.Response(status, headers=headers, json=payload)
        return httpx.Response(200, headers=headers, content=json.dumps(body).encode())

    def _body(
        self, name: str, params: dict[str, str], futures: bool
    ) -> tuple[Any, int]:
        if name in {"ping", "time"}:
            return ({} if name == "ping" else {"serverTime": self.now_ms}), 1
        if name == "system/status":
            return {"status": 0, "msg": "normal"}, 1
        if name == "exchangeInfo":
            return self._info(params, futures), 20
        symbol = params.get("symbol")
        known = {row[0] for row in (FUTURES_SYMBOLS if futures else SPOT_SYMBOLS)}
        if name == "ticker/24hr":
            return self._tickers(futures), 40 if futures else 80
        if symbol not in known:
            return (400, {"code": -1121, "msg": "Invalid symbol."}), 1
        if name == "klines":
            return self._klines(params, futures), 2
        if name == "aggTrades":
            return self._trades(params, futures), 20 if futures else 4
        if name == "depth":
            return self._depth(params, futures), 5
        return (404, {"code": -1, "msg": "?"}), 1

    def _info(self, params: dict[str, str], futures: bool) -> dict[str, Any]:
        limit = 2400 if futures else 6000
        symbols: list[dict[str, Any]] = []
        if futures:
            for name, base, quote, status, contract, delivery in FUTURES_SYMBOLS:
                symbols.append(
                    {
                        "symbol": name,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "status": status,
                        "contractType": contract,
                        "deliveryDate": delivery,
                        "onboardDate": 1_569_398_400_000,
                        "filters": _filters("0.10"),
                    }
                )
        else:
            for name, base, quote, status in SPOT_SYMBOLS:
                if params.get("symbolStatus") == "TRADING" and status != "TRADING":
                    continue
                symbols.append(
                    {
                        "symbol": name,
                        "baseAsset": base,
                        "quoteAsset": quote,
                        "status": status,
                        "filters": _filters("0.01000000"),
                    }
                )
        return {
            "rateLimits": [
                {
                    "rateLimitType": "REQUEST_WEIGHT",
                    "interval": "MINUTE",
                    "intervalNum": 1,
                    "limit": limit,
                }
            ],
            "symbols": symbols,
        }

    def _tickers(self, futures: bool) -> list[dict[str, Any]]:
        rows = FUTURES_SYMBOLS if futures else SPOT_SYMBOLS
        found = []
        for index, row in enumerate(rows):
            found.append(
                {
                    "symbol": row[0],
                    "lastPrice": f"{100 + index}.10000000",
                    "priceChange": "-1.50000000",
                    "priceChangePercent": "-1.471",
                    "weightedAvgPrice": "101.00000000",
                    "openPrice": "102.00000000",
                    "highPrice": "103.00000000",
                    "lowPrice": "99.00000000",
                    "volume": "10.00000000",
                    # The second symbol trades most.
                    "quoteVolume": "9000.5" if index == 1 else f"{index}.25",
                    "count": 10 + index,
                    "openTime": self.now_ms - 86_400_000,
                    "closeTime": self.now_ms,
                }
            )
        return found

    def _klines(self, params: dict[str, str], futures: bool) -> list[list[Any]]:
        assert params["interval"] == "1h", "the fake knows hourly candles only"
        ceiling = 1500 if futures else 1000
        limit = min(int(params.get("limit", "500")), ceiling)
        opens = [self.first_open_ms + index * HOUR_MS for index in range(CANDLES)]
        if "startTime" in params:
            opens = [one for one in opens if one >= int(params["startTime"])]
        if "endTime" in params:
            opens = [one for one in opens if one <= int(params["endTime"])]
        # Binance answers the first `limit` from a start, else the last ones.
        opens = opens[:limit] if "startTime" in params else opens[-limit:]
        return [
            [
                one,
                f"{100 + (one - self.first_open_ms) // HOUR_MS}.00000000",
                "1.10000000",
                "0.90000000",
                "1.00000000",
                "5.00000000",
                one + HOUR_MS - 1,
                "500.00000000",
                7,
                "2.00000000",
                "200.00000000",
                "0",
            ]
            for one in opens
        ]

    def _trades(self, params: dict[str, str], futures: bool) -> Any:
        limit = min(int(params.get("limit", "500")), 1000)
        ids = list(range(1, self.trades + 1))
        window_start = self.now_ms - TWO_DAYS_MS
        if "fromId" in params:
            first = int(params["fromId"])
            if futures and (first < 1 or self.trade_ms(first) < window_start):
                return 400, {"code": -4166, "msg": "Search window is restricted."}
            ids = [one for one in ids if one >= first][:limit]
        elif "startTime" in params or "endTime" in params:
            start = int(params.get("startTime", "0"))
            end = int(params.get("endTime", str(self.now_ms)))
            if futures and start < window_start:
                return 400, {"code": -4166, "msg": "Search window is restricted."}
            ids = [one for one in ids if start <= self.trade_ms(one) <= end][:limit]
        else:
            ids = ids[-limit:]
        return [
            {
                "a": one,
                "p": f"{1000 + one}.50000000",
                "q": "0.01000000",
                "f": one * 2,
                "l": one * 2 + 1,
                "T": self.trade_ms(one),
                "m": one % 2 == 0,
            }
            for one in ids
        ]

    def _depth(self, params: dict[str, str], futures: bool) -> Any:
        limit = int(params.get("limit", "100"))
        if limit not in (FUTURES_DEPTHS if futures else SPOT_DEPTHS):
            return 400, {"code": -1100, "msg": "Illegal characters found in parameter."}
        return {
            "bids": [[f"{100 - level / 100:.2f}", "1.5"] for level in range(limit)],
            "asks": [[f"{100.01 + level / 100:.2f}", "2"] for level in range(limit)],
        }


def install(monkeypatch: pytest.MonkeyPatch) -> FakeBinance:
    """A fake Binance every new client of the source speaks to."""
    fake = FakeBinance()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(fake.handler()))

    monkeypatch.setattr(binance_session, "make_client", client)
    return fake

"""An OKX that answers from memory, for tests that must not reach the real one.

CI runs in the United States, which OKX's main service does not serve, so
the adapter is tested against this instead: the paths, parameters, shapes
and refusals the adapter relies on, checked against the real v5 API when the
adapter was written (D432). One trade a second, numbered one after another,
and one candle an hour, counted back from now; every answer a `code`, as
OKX's are.
"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app.adapters.okx import session as okx_session

API_KEY = "fake-okx-key"
API_SECRET = "fake-okx-secret"
PASSPHRASE = "fake-okx-passphrase"
DAY_MS = 86_400_000
HOUR_MS = 3_600_000
SECOND_MS = 1000
KEPT_MS = 90 * DAY_MS
CANDLES = 3000
TRADES = 5000
# The first trade id the fake answers; older ones are gone, as OKX's
# older than three months are.
FIRST_TRADE = 1001

# Spot: name, base, quote, state.
SPOT = [
    ("BTC-USDT", "BTC", "USDT", "live"),
    ("ETH-USDT", "ETH", "USDT", "live"),
    ("ETH-BTC", "ETH", "BTC", "live"),
    ("GONE-USDT", "GONE", "USDT", "suspend"),
]
# Contracts: name, type, family, contract type, value, lot, state, expiry.
CONTRACTS = [
    ("BTC-USDT-SWAP", "SWAP", "BTC-USDT", "linear", "0.01", "0.01", "live", ""),
    ("BTC-USDC-SWAP", "SWAP", "BTC-USDC", "linear", "0.0001", "0.01", "live", ""),
    ("BTC-USD-SWAP", "SWAP", "BTC-USD", "inverse", "100", "0.1", "live", ""),
    ("NEW-USDT-SWAP", "SWAP", "NEW-USDT", "linear", "1", "1", "preopen", ""),
    (
        "BTC-USDT-261225",
        "FUTURES",
        "BTC-USDT",
        "linear",
        "0.01",
        "0.1",
        "live",
        "1798185600000",
    ),
    (
        "BTC-USD-261225",
        "FUTURES",
        "BTC-USD",
        "inverse",
        "100",
        "1",
        "live",
        "1798185600000",
    ),
]


@dataclass
class Asked:
    host: str
    path: str
    params: dict[str, str]
    headers: dict[str, str]


@dataclass
class FakeOkx:
    now_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    asked: list[Asked] = field(default_factory=list)
    # The newest trade's id; raised by a test to make new ones.
    trades: int = TRADES
    first_trade: int = FIRST_TRADE
    # How far apart trades are; a test raises it to reach past OKX's three
    # months, beyond which trades are gone.
    spacing_ms: int = SECOND_MS
    # Answer every request with this status and body instead.
    refuse: tuple[int, dict[str, Any]] | None = None
    # What OKX says of the key's permissions.
    perm: str = "read_only"
    # How many signed requests to refuse as carrying a stale time.
    stale: int = 0
    # The signed paths answered.
    signed: list[str] = field(default_factory=list)
    maintenance: bool = False

    @property
    def last_trade_ms(self) -> int:
        return self.now_ms - self.now_ms % 1000

    def add_trades(self, count: int) -> None:
        """New trades, a second apart, made after the old ones and now."""
        self.trades += count
        self.now_ms += count * self.spacing_ms

    def trade_ms(self, trade_id: int) -> int:
        return self.last_trade_ms - (self.trades - trade_id) * self.spacing_ms

    @property
    def kept_from(self) -> int:
        """The oldest trade still answered: none older than ninety days."""
        oldest = self.trades - (KEPT_MS // self.spacing_ms) + 1
        return max(self.first_trade, oldest)

    @property
    def first_open_ms(self) -> int:
        return self.now_ms - self.now_ms % HOUR_MS - (CANDLES - 1) * HOUR_MS

    def handler(self) -> Callable[[httpx.Request], httpx.Response]:
        return self.answer

    def answer(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        params = dict(parse_qsl(url.query))
        self.asked.append(Asked(url.netloc, url.path, params, dict(request.headers)))
        if self.refuse is not None:
            status, body = self.refuse
            return httpx.Response(status, json=body)
        if "OK-ACCESS-SIGN" in request.headers:
            target = url.path + (f"?{url.query}" if url.query else "")
            result = self._signed(request, url.path, target, params)
        else:
            result = self._result(url.path, params)
        if isinstance(result, tuple):
            status, code, message = result
            return httpx.Response(
                status, json={"code": code, "msg": message, "data": []}
            )
        return httpx.Response(
            200,
            content=json.dumps({"code": "0", "msg": "", "data": result}).encode(),
        )

    # --- the account of one fake key ------------------------------------------

    def _signed(
        self, request: httpx.Request, path: str, target: str, params: dict[str, str]
    ) -> Any:
        headers = request.headers
        if headers.get("OK-ACCESS-KEY") != API_KEY:
            return 401, "50111", "Invalid OK-ACCESS-KEY."
        if headers.get("OK-ACCESS-PASSPHRASE") != PASSPHRASE:
            return 401, "50105", "OK-ACCESS-PASSPHRASE incorrect."
        stamp = headers.get("OK-ACCESS-TIMESTAMP", "")
        expected = base64.b64encode(
            hmac.new(
                API_SECRET.encode(), f"{stamp}GET{target}".encode(), hashlib.sha256
            ).digest()
        ).decode()
        if not hmac.compare_digest(headers.get("OK-ACCESS-SIGN", ""), expected):
            return 401, "50113", "Invalid signature."
        at = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if abs(at.timestamp() * 1000 - self.now_ms) > 30_000 or self.stale > 0:
            self.stale = max(0, self.stale - 1)
            return 401, "50102", "Timestamp request expired."
        self.signed.append(path)
        return self.account(path, params)

    def account(self, path: str, params: dict[str, str]) -> Any:
        """Overridden by the account's tests; nothing here before them."""
        del path, params
        return 400, "50014", "?"

    # --- public data -------------------------------------------------------------

    def _result(self, path: str, params: dict[str, str]) -> Any:
        name = path.removeprefix("/api/v5/")
        if name == "public/time":
            return [{"ts": str(self.now_ms)}]
        if name == "system/status":
            if not self.maintenance:
                return []
            return [{"state": "ongoing", "serviceType": "5", "title": "upgrade"}]
        if name == "public/instruments":
            return self._instruments(params["instType"])
        if name == "market/tickers":
            return self._tickers(params["instType"])
        known = {row[0] for row in SPOT if row[3] == "live"} | {
            row[0] for row in CONTRACTS if row[6] == "live"
        }
        if params.get("instId") not in known:
            return 200, "51001", "Instrument ID doesn't exist."
        if name == "market/ticker":
            return [
                one
                for one in self._tickers(self._type_of(params["instId"]))
                if one["instId"] == params["instId"]
            ]
        if name == "market/history-candles":
            return self._candles(params)
        if name == "market/history-trades":
            return self._trades(params)
        if name == "market/books":
            return self._book(params)
        return 404, "404", "?"

    def _type_of(self, name: str) -> str:
        for row in CONTRACTS:
            if row[0] == name:
                return row[1]
        return "SPOT"

    def _instruments(self, inst_type: str) -> list[dict[str, Any]]:
        if inst_type == "SPOT":
            return [
                {
                    "instType": "SPOT",
                    "instId": name,
                    "baseCcy": base,
                    "quoteCcy": quote,
                    "state": state,
                    "tickSz": "0.1",
                    "lotSz": "0.00000001",
                    "minSz": "0.00001",
                    "ctType": "",
                    "ctVal": "",
                    "instFamily": "",
                    "listTime": "1611907686000",
                    "expTime": "",
                }
                for name, base, quote, state in SPOT
            ]
        return [
            {
                "instType": kind,
                "instId": name,
                "instFamily": family,
                "uly": family,
                "baseCcy": "",
                "quoteCcy": "",
                "ctType": ct_type,
                "ctVal": value,
                "ctValCcy": "USD" if ct_type == "inverse" else family.split("-")[0],
                "settleCcy": family.split("-")[0]
                if ct_type == "inverse"
                else family.split("-")[1],
                "lotSz": lot,
                "tickSz": "0.1",
                "state": state,
                "listTime": "1573557408000",
                "expTime": expiry,
            }
            for name, kind, family, ct_type, value, lot, state, expiry in CONTRACTS
            if kind == inst_type
        ]

    def _tickers(self, inst_type: str) -> list[dict[str, Any]]:
        names = (
            [row[0] for row in SPOT]
            if inst_type == "SPOT"
            else [row[0] for row in CONTRACTS if row[1] == inst_type]
        )
        found = []
        for index, name in enumerate(names):
            found.append(
                {
                    "instType": inst_type,
                    "instId": name,
                    "last": f"{100 + index}.5",
                    "open24h": "100",
                    "high24h": "103",
                    "low24h": "99",
                    # The second instrument trades most.
                    "vol24h": "9000" if index == 1 else f"{index}.5",
                    "volCcy24h": "900000" if index == 1 else f"{index}.25",
                    "ts": str(self.now_ms),
                }
            )
        return found

    def _candles(self, params: dict[str, str]) -> Any:
        assert params["bar"] == "1H", "the fake knows hourly candles only"
        limit = int(params.get("limit", "100"))
        if not 1 <= limit <= 300:
            return 200, "51000", "Parameter limit error"
        opens = [self.first_open_ms + index * HOUR_MS for index in range(CANDLES)]
        if "after" in params:
            opens = [one for one in opens if one < int(params["after"])]
        if "before" in params:
            opens = [one for one in opens if one > int(params["before"])]
        newest = opens[-1] if opens else None
        last_open = self.first_open_ms + (CANDLES - 1) * HOUR_MS
        return [
            [
                str(one),
                f"{100 + (one - self.first_open_ms) // HOUR_MS}",
                "1.1",
                "0.9",
                "1",
                "5",
                "7",
                "500",
                "0" if one == last_open else "1",
            ]
            for one in reversed(opens[-limit:])
            if newest is not None
        ]

    def _trade(self, name: str, trade_id: int) -> dict[str, Any]:
        return {
            "instId": name,
            "tradeId": str(trade_id),
            "px": f"{1000 + trade_id}.5",
            "sz": "2",
            "side": "sell" if trade_id % 2 == 0 else "buy",
            "ts": str(self.trade_ms(trade_id)),
            "source": "0",
        }

    def _trades(self, params: dict[str, str]) -> Any:
        limit = int(params.get("limit", "100"))
        if not 1 <= limit <= 100:
            return 200, "51000", "Parameter limit error"
        ids = list(range(self.kept_from, self.trades + 1))
        if params.get("type", "1") == "2":
            if "before" in params:
                return 200, "51000", "Parameter before error"
            if "after" in params:
                ids = [one for one in ids if self.trade_ms(one) < int(params["after"])]
        else:
            if "after" in params:
                ids = [one for one in ids if one < int(params["after"])]
            if "before" in params:
                ids = [one for one in ids if one > int(params["before"])]
        return [self._trade(params["instId"], one) for one in reversed(ids[-limit:])]

    def _book(self, params: dict[str, str]) -> Any:
        depth = int(params.get("sz", "1"))
        if not 1 <= depth <= 400:
            return 200, "51000", "Parameter sz error"
        return [
            {
                "bids": [
                    [f"{100 - level / 100:.2f}", "1.5", "0", "1"]
                    for level in range(depth)
                ],
                "asks": [
                    [f"{100.01 + level / 100:.2f}", "2", "0", "1"]
                    for level in range(depth)
                ],
                "ts": str(self.now_ms),
            }
        ]


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeOkx | None = None) -> FakeOkx:
    """A fake OKX every new client of the source speaks to."""
    found = fake or FakeOkx()

    def client() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(found.handler()))

    monkeypatch.setattr(okx_session, "make_client", client)
    return found

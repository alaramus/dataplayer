"""What the connection says about Binance and itself (D320).

The Exchange section and its shared readers (D425), in Binance's words, and
the report only a key has: what Binance lets it do (D322).
"""

from app.adapters.binance.account import PERMISSIONS, restrictions
from app.adapters.binance.session import BinanceSession
from app.adapters.market.reports import (
    ExchangeReport,
    ExchangeReports,
    Rows,
    clock_rows,
    limit_rows,
    market_rows,
    moment_of,
    status_rows,
)
from app.core.translation import N_, say

SECTION_DESCRIPTION = N_("What Binance and this connection say about themselves")

ENDPOINT_TITLES = {
    "binance": N_("Binance"),
    "binance_key": N_("Binance, with an API key"),
    "market_data": N_("Binance, market data only"),
    "testnet": N_("Testnet"),
    "testnet_key": N_("Testnet, with an API key"),
}


async def _status(session: BinanceSession) -> Rows:
    return await status_rows(session, ENDPOINT_TITLES, session.options.endpoint)


async def _key(session: BinanceSession) -> Rows:
    """What Binance says the connection's key may do (D322)."""
    answer = await restrictions(session)
    if answer is None:
        return [(say("What the key may do"), say("not known on the testnet"))]
    rows: Rows = [
        (say(word), say("yes") if answer.get(flag) is True else say("no"))
        for flag, word in PERMISSIONS
    ]
    rows.append(
        (
            say("limited to listed addresses"),
            say("yes") if answer.get("ipRestrict") is True else say("no"),
        )
    )
    created = answer.get("createTime")
    if isinstance(created, int):
        rows.append((say("created"), moment_of(created)))
    return rows


REPORTS: tuple[ExchangeReport[BinanceSession], ...] = (
    ExchangeReport(
        "status",
        N_("Status"),
        N_("The endpoint, Binance's own status, and whether each market answers"),
        _status,
        refresh_seconds=30,
    ),
    ExchangeReport(
        "clock",
        N_("Clock"),
        N_("Each market's time against this server's"),
        clock_rows,
    ),
    ExchangeReport(
        "rate-limit",
        N_("Rate limit"),
        N_("What each market allows a minute, what was used, and where this stops"),
        limit_rows,
        refresh_seconds=10,
    ),
    ExchangeReport(
        "markets",
        N_("Markets"),
        N_("How many symbols trade and in how many quote assets"),
        market_rows,
    ),
    ExchangeReport(
        "key",
        N_("API key"),
        N_("What Binance lets this connection's key do"),
        _key,
        keyed=True,
    ),
)


def binance_reports(session: BinanceSession) -> ExchangeReports[BinanceSession]:
    return ExchangeReports(session, SECTION_DESCRIPTION, REPORTS)

"""What the connection says about Coinbase and itself (D442).

The Exchange section and its shared readers (D425) in Coinbase's words.
Coinbase has no system status on its public paths, and one budget for the
address.
"""

from app.adapters.coinbase.account import PERMISSIONS, key_info
from app.adapters.coinbase.session import CoinbaseSession
from app.adapters.market.reports import (
    ExchangeReport,
    ExchangeReports,
    Rows,
    clock_rows,
    limit_rows,
    market_rows,
    status_rows,
)
from app.adapters.metrics import MetricPreset, MetricRecipe
from app.core.translation import N_, say

SECTION_DESCRIPTION = N_("What Coinbase and this connection say about themselves")

ENDPOINT_TITLES = {
    "coinbase": N_("Coinbase Exchange"),
    "sandbox": N_("Sandbox"),
    "coinbase_key": N_("Coinbase Exchange, with an API key"),
}


async def _key(session: CoinbaseSession) -> Rows:
    """What Coinbase says the connection's key may do (D443)."""
    info = await key_info(session)
    yes, no = say("yes"), say("no")
    rows: Rows = [
        (say(word), yes if info.get(field) is True else no)
        for field, word in PERMISSIONS
    ]
    kind = info.get("portfolio_type")
    if isinstance(kind, str) and kind:
        rows.append((say("portfolio"), kind.casefold()))
    return rows


async def _status(session: CoinbaseSession) -> Rows:
    return await status_rows(session, ENDPOINT_TITLES, session.endpoint)


REPORTS: tuple[ExchangeReport[CoinbaseSession], ...] = (
    ExchangeReport(
        "status",
        N_("Status"),
        N_("The endpoint, and whether each market answers"),
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
        N_(
            "What Coinbase allows this address in a second, what was used, "
            "and where this stops"
        ),
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
        N_("What Coinbase lets this connection's key do"),
        _key,
        keyed=True,
    ),
)


def coinbase_reports(session: CoinbaseSession) -> ExchangeReports[CoinbaseSession]:
    return ExchangeReports(session, SECTION_DESCRIPTION, REPORTS)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="coinbase-connection",
        name=N_("Coinbase connection"),
        description=N_(
            "The requests this connection made in each second against where "
            "it stops, how long Coinbase takes to answer, and whether it "
            "answers."
        ),
        recipes=(
            MetricRecipe(
                "timeseries", N_("Requests in a second"), (0, 0, 8, 5), "weight"
            ),
            MetricRecipe("stat", N_("Markets answering"), (8, 0, 4, 5), "reachable"),
            MetricRecipe("timeseries", N_("Latency"), (0, 5, 12, 5), "latency"),
        ),
    ),
)

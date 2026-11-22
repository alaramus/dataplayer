"""What the connection says about Bybit and itself (D430).

The Exchange section and its shared readers (D425) in Bybit's words. Bybit
has no system status on its public paths, and one budget for the address.
"""

from app.adapters.bybit.session import BybitSession
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
from app.core.translation import N_

SECTION_DESCRIPTION = N_("What Bybit and this connection say about themselves")

ENDPOINT_TITLES = {
    "bybit": N_("Bybit"),
    "bytick": N_("Bybit, through bytick.com"),
    "testnet": N_("Testnet"),
}


async def _status(session: BybitSession) -> Rows:
    return await status_rows(session, ENDPOINT_TITLES, session.endpoint)


REPORTS: tuple[ExchangeReport[BybitSession], ...] = (
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
            "What Bybit allows this address in five seconds, what was used, "
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
)


def bybit_reports(session: BybitSession) -> ExchangeReports[BybitSession]:
    return ExchangeReports(session, SECTION_DESCRIPTION, REPORTS)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="bybit-connection",
        name=N_("Bybit connection"),
        description=N_(
            "The requests this connection made in each five seconds against "
            "where it stops, how long Bybit takes to answer, and whether each "
            "market answers."
        ),
        recipes=(
            MetricRecipe(
                "timeseries",
                N_("Requests in five seconds"),
                (0, 0, 8, 5),
                "weight",
            ),
            MetricRecipe("stat", N_("Markets answering"), (8, 0, 4, 5), "reachable"),
            MetricRecipe("timeseries", N_("Latency"), (0, 5, 12, 5), "latency"),
        ),
    ),
)

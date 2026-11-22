"""What the connection says about Bybit and itself (D430).

The Exchange section and its shared readers (D425) in Bybit's words. Bybit
has no system status on its public paths, and one budget for the address.
"""

from app.adapters.bybit.account import PERMISSION_GROUPS, granted, key_info
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
from app.core.translation import N_, say

SECTION_DESCRIPTION = N_("What Bybit and this connection say about themselves")

ENDPOINT_TITLES = {
    "bybit": N_("Bybit"),
    "bytick": N_("Bybit, through bytick.com"),
    "bybit_key": N_("Bybit, with an API key"),
    "testnet": N_("Testnet"),
    "testnet_key": N_("Testnet, with an API key"),
}


async def _key(session: BybitSession) -> Rows:
    """What Bybit says the connection's key may do (D431)."""
    info = await key_info(session)
    yes, no = say("yes"), say("no")
    rows: Rows = [(say("read only"), yes if info.get("readOnly") == 1 else no)]
    rows += [
        (say(word), yes if granted(info, group) else no)
        for group, word in PERMISSION_GROUPS
    ]
    ips = info.get("ips")
    limited = isinstance(ips, list) and bool(ips) and ips != ["*"]
    rows.append((say("limited to listed addresses"), yes if limited else no))
    for field, word in (("createdAt", N_("created")), ("expiredAt", N_("expires"))):
        value = info.get(field)
        # Bybit dates a key that never expires at the epoch.
        if isinstance(value, str) and value and not value.startswith("1970"):
            rows.append((say(word), value))
    return rows


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
    ExchangeReport(
        "key",
        N_("API key"),
        N_("What Bybit lets this connection's key do"),
        _key,
        keyed=True,
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

"""What the connection says about OKX and itself (D436).

The Exchange section and its shared readers (D425) in OKX's words. OKX
limits each path on its own, so the rate limit is said a path at a time, and
measured the same way.
"""

import time

from app.adapters.market.budget import Budget
from app.adapters.market.reports import (
    ExchangeReport,
    ExchangeReports,
    Rows,
    clock_rows,
    market_rows,
    moment_of,
    status_rows,
)
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.adapters.okx.session import OkxSession
from app.core.translation import N_, say

SECTION_DESCRIPTION = N_("What OKX and this connection say about themselves")

ENDPOINT_TITLES = {
    "okx": N_("OKX"),
    "okx_key": N_("OKX, with an API key"),
    "eea": N_("OKX Europe"),
    "eea_key": N_("OKX Europe, with an API key"),
    "demo": N_("Demo trading"),
    "demo_key": N_("Demo trading, with an API key"),
}


def path_title(key: str) -> str:
    """A budget's key as a person reads it: the path after `/api/v5/`."""
    return key.removeprefix("/api/v5/")


async def budgets(session: OkxSession) -> dict[str, Budget]:
    """Each path's budget as it stands, every market pinged first."""
    await session.pinged()
    async with session.kept() as kept:
        return dict(sorted(kept.budgets.items()))


async def _limit(session: OkxSession) -> Rows:
    """Each path asked so far: its limit, what was used, where this stops."""
    rows: Rows = []
    now = time.time()
    for key, state in (await budgets(session)).items():
        title = path_title(key)
        rows += [
            (
                say(
                    "{market}: limit in {seconds} s",
                    market=title,
                    seconds=state.window_seconds,
                ),
                str(state.limit),
            ),
            (
                say(
                    "{market}: used in these {seconds} s",
                    market=title,
                    seconds=state.window_seconds,
                ),
                str(state.used_at(now)),
            ),
            (
                say("{market}: this connection stops at", market=title),
                str(state.ceiling),
            ),
            (
                say("{market}: requests held", market=title),
                say("until {at}", at=moment_of(state.held_until * 1000))
                if state.held_until > now
                else say("no"),
            ),
        ]
    return rows


async def _status(session: OkxSession) -> Rows:
    return await status_rows(session, ENDPOINT_TITLES, session.endpoint)


async def metric_samples(session: OkxSession) -> list[MetricSample]:
    """Reach and latency per market, the weight per path (D436)."""
    found: list[MetricSample] = []
    for key, pinged in (await session.pinged()).items():
        up = pinged.latency_ms is not None
        found.append(MetricSample("reachable", "up", 1.0 if up else 0.0, label=key))
        if pinged.latency_ms is not None:
            found.append(
                MetricSample("latency", "ms", pinged.latency_ms, label=key, unit="ms")
            )
    now = time.time()
    async with session.kept() as kept:
        for key, state in sorted(kept.budgets.items()):
            label = path_title(key)
            found += [
                MetricSample("weight", "used", float(state.used_at(now)), label=label),
                MetricSample("weight", "ceiling", float(state.ceiling), label=label),
            ]
    return found


REPORTS: tuple[ExchangeReport[OkxSession], ...] = (
    ExchangeReport(
        "status",
        N_("Status"),
        N_("The endpoint, OKX's maintenance, and whether each market answers"),
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
            "What OKX allows this address on each path asked so far, what "
            "was used, and where this stops"
        ),
        _limit,
        refresh_seconds=10,
    ),
    ExchangeReport(
        "markets",
        N_("Markets"),
        N_("How many symbols trade and in how many quote assets"),
        market_rows,
    ),
)


def okx_reports(session: OkxSession) -> ExchangeReports[OkxSession]:
    return ExchangeReports(session, SECTION_DESCRIPTION, REPORTS)


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="okx-connection",
        name=N_("OKX connection"),
        description=N_(
            "The requests this connection made of each path in its window "
            "against where it stops, how long OKX takes to answer, and "
            "whether each market answers."
        ),
        recipes=(
            MetricRecipe(
                "timeseries",
                N_("Requests a path in its window"),
                (0, 0, 8, 5),
                "weight",
            ),
            MetricRecipe("stat", N_("Markets answering"), (8, 0, 4, 5), "reachable"),
            MetricRecipe("timeseries", N_("Latency"), (0, 5, 12, 5), "latency"),
        ),
    ),
)

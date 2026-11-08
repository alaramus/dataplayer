"""What a Binance connection is measured by (D320): its own use of Binance.

The weight used a minute against where this connection stops, how long a
request takes, and whether each market answers. Prices are not metrics: they
belong in a pipeline's table, which a dashboard reads as it reads any other.
"""

import time

from app.adapters.binance.session import CEILING_SHARE, BinanceSession
from app.adapters.metrics import MetricPreset, MetricRecipe, MetricSample
from app.core.translation import N_


class BinanceMetrics:
    def __init__(self, session: BinanceSession) -> None:
        self._session = session

    async def metric_samples(self) -> list[MetricSample]:
        found: list[MetricSample] = []
        minute = int(time.time() // 60)
        for key, pinged in (await self._session.pinged()).items():
            state = pinged.state
            up = pinged.latency_ms is not None
            found.append(MetricSample("reachable", "up", 1.0 if up else 0.0, label=key))
            if pinged.latency_ms is not None:
                found.append(
                    MetricSample(
                        "latency", "ms", pinged.latency_ms, label=key, unit="ms"
                    )
                )
            used = state.used if state.minute == minute else 0
            found.append(MetricSample("weight", "used", float(used), label=key))
            found.append(
                MetricSample(
                    "weight",
                    "ceiling",
                    float(int(state.limit * CEILING_SHARE)),
                    label=key,
                )
            )
        return found


PRESETS: tuple[MetricPreset, ...] = (
    MetricPreset(
        key="binance-connection",
        name=N_("Binance connection"),
        description=N_(
            "The weight this connection used each minute against where it stops, "
            "how long Binance takes to answer, and whether each market answers."
        ),
        recipes=(
            MetricRecipe(
                "timeseries", N_("Weight used a minute"), (0, 0, 8, 5), "weight"
            ),
            MetricRecipe("stat", N_("Markets answering"), (8, 0, 4, 5), "reachable"),
            MetricRecipe("timeseries", N_("Latency"), (0, 5, 12, 5), "latency"),
        ),
    ),
)

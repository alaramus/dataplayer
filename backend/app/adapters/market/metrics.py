"""What an exchange connection is measured by (D320, D425): its own use of the exchange.

The weight used in the current window against where this connection stops,
how long a ping takes, and whether each market answers, per market as the
label. Prices are not metrics: they belong in a pipeline's table, which a
dashboard reads as it reads any other. Each exchange names its preset.
"""

import time
from typing import Any

from app.adapters.market.session import MarketSession
from app.adapters.metrics import MetricSample

# The label of a budget every market spends from (D426).
ADDRESS = "address"


async def metric_samples(session: MarketSession[Any]) -> list[MetricSample]:
    found: list[MetricSample] = []
    now = time.time()
    for key, pinged in (await session.pinged()).items():
        state = pinged.state
        up = pinged.latency_ms is not None
        found.append(MetricSample("reachable", "up", 1.0 if up else 0.0, label=key))
        if pinged.latency_ms is not None:
            found.append(
                MetricSample("latency", "ms", pinged.latency_ms, label=key, unit="ms")
            )
        if session.per_address and any(one.label == ADDRESS for one in found):
            continue
        label = ADDRESS if session.per_address else key
        found.append(
            MetricSample("weight", "used", float(state.used_at(now)), label=label)
        )
        found.append(
            MetricSample("weight", "ceiling", float(state.ceiling), label=label)
        )
    return found

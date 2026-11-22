"""What a Binance connection is measured by (D320): the shared samples (D425), its preset."""

from app.adapters.metrics import MetricPreset, MetricRecipe
from app.core.translation import N_

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

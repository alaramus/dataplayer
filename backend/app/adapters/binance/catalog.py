"""Binance's markets as the shared catalog's (D317, D425).

The ids and nodes are the shared catalog's; this names the three markets an
id may begin with.
"""

from app.adapters.binance.markets import BY_KEY, Market
from app.adapters.market.catalog import Place, place_in


def place_of(node_id: str) -> Place[Market]:
    """The node an id names, or a refusal when it names none of this source."""
    return place_in(BY_KEY, node_id)

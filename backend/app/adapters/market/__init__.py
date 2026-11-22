"""What every exchange's market data shares, under the exchange's own client (D425).

A source of market data — Binance, Bybit — brings its hosts, its limits, its
paths, its symbols' names and its sockets' frames; this package brings the
rest once: the catalog's shape, the columns of a feed, the rate limit's
ceiling as a mechanism, the Exchange section of reports, the metrics, the
search, the read of a list and of a book, the live view's upstream socket.
"""

from app.adapters.market.locales.ar import MESSAGES as AR
from app.adapters.market.locales.de import MESSAGES as DE
from app.adapters.market.locales.es import MESSAGES as ES
from app.adapters.market.locales.fr import MESSAGES as FR
from app.adapters.market.locales.hi import MESSAGES as HI
from app.adapters.market.locales.ru import MESSAGES as RU
from app.adapters.market.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

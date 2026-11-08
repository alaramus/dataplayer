from app.adapters.binance import adapter  # noqa: F401
from app.adapters.binance.locales.ar import MESSAGES as AR
from app.adapters.binance.locales.de import MESSAGES as DE
from app.adapters.binance.locales.es import MESSAGES as ES
from app.adapters.binance.locales.fr import MESSAGES as FR
from app.adapters.binance.locales.hi import MESSAGES as HI
from app.adapters.binance.locales.ru import MESSAGES as RU
from app.adapters.binance.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

from app.adapters.coinbase import adapter  # noqa: F401
from app.adapters.coinbase.locales.ar import MESSAGES as AR
from app.adapters.coinbase.locales.de import MESSAGES as DE
from app.adapters.coinbase.locales.es import MESSAGES as ES
from app.adapters.coinbase.locales.fr import MESSAGES as FR
from app.adapters.coinbase.locales.hi import MESSAGES as HI
from app.adapters.coinbase.locales.ru import MESSAGES as RU
from app.adapters.coinbase.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

from app.adapters.bybit import adapter  # noqa: F401
from app.adapters.bybit.locales.ar import MESSAGES as AR
from app.adapters.bybit.locales.de import MESSAGES as DE
from app.adapters.bybit.locales.es import MESSAGES as ES
from app.adapters.bybit.locales.fr import MESSAGES as FR
from app.adapters.bybit.locales.hi import MESSAGES as HI
from app.adapters.bybit.locales.ru import MESSAGES as RU
from app.adapters.bybit.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

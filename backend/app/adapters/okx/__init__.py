from app.adapters.okx import adapter  # noqa: F401
from app.adapters.okx.locales.ar import MESSAGES as AR
from app.adapters.okx.locales.de import MESSAGES as DE
from app.adapters.okx.locales.es import MESSAGES as ES
from app.adapters.okx.locales.fr import MESSAGES as FR
from app.adapters.okx.locales.hi import MESSAGES as HI
from app.adapters.okx.locales.ru import MESSAGES as RU
from app.adapters.okx.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

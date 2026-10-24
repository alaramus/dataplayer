from app.adapters.sqlite import adapter  # noqa: F401
from app.adapters.sqlite.locales.de import MESSAGES as DE
from app.adapters.sqlite.locales.es import MESSAGES as ES
from app.adapters.sqlite.locales.fr import MESSAGES as FR
from app.adapters.sqlite.locales.hi import MESSAGES as HI
from app.adapters.sqlite.locales.ru import MESSAGES as RU
from app.adapters.sqlite.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

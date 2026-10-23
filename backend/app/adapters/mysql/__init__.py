from app.adapters.mysql import adapter  # noqa: F401
from app.adapters.mysql.locales.de import MESSAGES as DE
from app.adapters.mysql.locales.es import MESSAGES as ES
from app.adapters.mysql.locales.fr import MESSAGES as FR
from app.adapters.mysql.locales.hi import MESSAGES as HI
from app.adapters.mysql.locales.ru import MESSAGES as RU
from app.adapters.mysql.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

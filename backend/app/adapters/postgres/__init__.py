from app.adapters.postgres import adapter  # noqa: F401
from app.adapters.postgres.locales.de import MESSAGES as DE
from app.adapters.postgres.locales.es import MESSAGES as ES
from app.adapters.postgres.locales.fr import MESSAGES as FR
from app.adapters.postgres.locales.hi import MESSAGES as HI
from app.adapters.postgres.locales.ru import MESSAGES as RU
from app.adapters.postgres.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("de", DE)
register("ru", RU)
register("fr", FR)
register("zh", ZH)
register("hi", HI)
register("es", ES)

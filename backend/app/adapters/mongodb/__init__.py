from app.adapters.mongodb import adapter  # noqa: F401
from app.adapters.mongodb.locales.ar import MESSAGES as AR
from app.adapters.mongodb.locales.de import MESSAGES as DE
from app.adapters.mongodb.locales.es import MESSAGES as ES
from app.adapters.mongodb.locales.fr import MESSAGES as FR
from app.adapters.mongodb.locales.hi import MESSAGES as HI
from app.adapters.mongodb.locales.ru import MESSAGES as RU
from app.adapters.mongodb.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

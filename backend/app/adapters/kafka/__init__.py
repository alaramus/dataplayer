from app.adapters.kafka import adapter  # noqa: F401
from app.adapters.kafka.locales.ar import MESSAGES as AR
from app.adapters.kafka.locales.de import MESSAGES as DE
from app.adapters.kafka.locales.es import MESSAGES as ES
from app.adapters.kafka.locales.fr import MESSAGES as FR
from app.adapters.kafka.locales.hi import MESSAGES as HI
from app.adapters.kafka.locales.ru import MESSAGES as RU
from app.adapters.kafka.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

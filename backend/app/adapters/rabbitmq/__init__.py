from app.adapters.rabbitmq import adapter  # noqa: F401
from app.adapters.rabbitmq.locales.ar import MESSAGES as AR
from app.adapters.rabbitmq.locales.de import MESSAGES as DE
from app.adapters.rabbitmq.locales.es import MESSAGES as ES
from app.adapters.rabbitmq.locales.fr import MESSAGES as FR
from app.adapters.rabbitmq.locales.hi import MESSAGES as HI
from app.adapters.rabbitmq.locales.ru import MESSAGES as RU
from app.adapters.rabbitmq.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

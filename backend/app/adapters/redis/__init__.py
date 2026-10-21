# Imported for the side effect: the driver registers itself.
from app.adapters.redis import adapter  # noqa: F401
from app.adapters.redis.locales.de import MESSAGES as DE
from app.adapters.redis.locales.fr import MESSAGES as FR
from app.adapters.redis.locales.ru import MESSAGES as RU
from app.adapters.redis.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)

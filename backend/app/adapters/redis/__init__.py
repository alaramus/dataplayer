# Imported for the side effect: the driver registers itself.
from app.adapters.redis import adapter  # noqa: F401
from app.adapters.redis.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)

# Imported for the side effect: drivers register themselves on import.
from app.adapters import file, postgres, redis, ssh  # noqa: F401
from app.adapters.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)

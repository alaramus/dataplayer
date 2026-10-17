from app.adapters.postgres import adapter  # noqa: F401
from app.adapters.postgres.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)

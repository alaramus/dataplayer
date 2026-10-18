from app.adapters.mysql import adapter  # noqa: F401
from app.adapters.mysql.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)

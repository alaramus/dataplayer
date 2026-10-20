from app.adapters.postgres import adapter  # noqa: F401
from app.adapters.postgres.locales.de import MESSAGES as DE
from app.adapters.postgres.locales.fr import MESSAGES as FR
from app.adapters.postgres.locales.ru import MESSAGES as RU
from app.core.translation import register

register("de", DE)
register("ru", RU)
register("fr", FR)

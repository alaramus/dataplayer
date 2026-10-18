from app.core.translation import register
from app.queries.locales.de import MESSAGES as DE
from app.queries.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

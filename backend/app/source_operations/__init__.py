from app.core.translation import register
from app.source_operations.locales.de import MESSAGES as DE
from app.source_operations.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

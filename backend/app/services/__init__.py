from app.core.translation import register
from app.services.locales.de import MESSAGES as DE
from app.services.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

from app.connectors.locales.de import MESSAGES as DE
from app.connectors.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("de", DE)

from app.core.translation import register
from app.users.locales.de import MESSAGES as DE
from app.users.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

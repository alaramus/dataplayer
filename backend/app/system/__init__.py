from app.core.translation import register
from app.system.locales.de import MESSAGES as DE
from app.system.locales.fr import MESSAGES as FR
from app.system.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

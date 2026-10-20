from app.core.translation import register
from app.users.locales.de import MESSAGES as DE
from app.users.locales.fr import MESSAGES as FR
from app.users.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

from app.core.translation import register
from app.transfers.locales.de import MESSAGES as DE
from app.transfers.locales.fr import MESSAGES as FR
from app.transfers.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

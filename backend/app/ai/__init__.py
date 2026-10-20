from app.ai.locales.de import MESSAGES as DE
from app.ai.locales.fr import MESSAGES as FR
from app.ai.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)

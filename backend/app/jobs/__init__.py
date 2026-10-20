from app.core.translation import register
from app.jobs.locales.de import MESSAGES as DE
from app.jobs.locales.fr import MESSAGES as FR
from app.jobs.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

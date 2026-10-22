from app.core.translation import register
from app.jobs.locales.de import MESSAGES as DE
from app.jobs.locales.fr import MESSAGES as FR
from app.jobs.locales.hi import MESSAGES as HI
from app.jobs.locales.ru import MESSAGES as RU
from app.jobs.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)

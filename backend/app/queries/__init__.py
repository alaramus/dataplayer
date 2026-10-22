from app.core.translation import register
from app.queries.locales.de import MESSAGES as DE
from app.queries.locales.fr import MESSAGES as FR
from app.queries.locales.hi import MESSAGES as HI
from app.queries.locales.ru import MESSAGES as RU
from app.queries.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)

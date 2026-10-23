from app.core.translation import register
from app.users.locales.de import MESSAGES as DE
from app.users.locales.es import MESSAGES as ES
from app.users.locales.fr import MESSAGES as FR
from app.users.locales.hi import MESSAGES as HI
from app.users.locales.ru import MESSAGES as RU
from app.users.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

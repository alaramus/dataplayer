from app.core.translation import register
from app.system.locales.ar import MESSAGES as AR
from app.system.locales.de import MESSAGES as DE
from app.system.locales.es import MESSAGES as ES
from app.system.locales.fr import MESSAGES as FR
from app.system.locales.hi import MESSAGES as HI
from app.system.locales.ru import MESSAGES as RU
from app.system.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

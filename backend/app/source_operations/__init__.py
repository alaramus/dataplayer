from app.core.translation import register
from app.source_operations.locales.de import MESSAGES as DE
from app.source_operations.locales.es import MESSAGES as ES
from app.source_operations.locales.fr import MESSAGES as FR
from app.source_operations.locales.hi import MESSAGES as HI
from app.source_operations.locales.ru import MESSAGES as RU
from app.source_operations.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

from app.core.translation import register
from app.pipelines.locales.de import MESSAGES as DE
from app.pipelines.locales.es import MESSAGES as ES
from app.pipelines.locales.fr import MESSAGES as FR
from app.pipelines.locales.hi import MESSAGES as HI
from app.pipelines.locales.ru import MESSAGES as RU
from app.pipelines.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

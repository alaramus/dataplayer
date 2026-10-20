from app.core.translation import register
from app.pipelines.locales.de import MESSAGES as DE
from app.pipelines.locales.fr import MESSAGES as FR
from app.pipelines.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

from app.core.translation import register
from app.pipelines.locales.de import MESSAGES as DE
from app.pipelines.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

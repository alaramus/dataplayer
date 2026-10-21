from app.connectors.locales.de import MESSAGES as DE
from app.connectors.locales.fr import MESSAGES as FR
from app.connectors.locales.ru import MESSAGES as RU
from app.connectors.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)

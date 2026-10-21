from app.core.translation import register
from app.shares.locales.de import MESSAGES as DE
from app.shares.locales.fr import MESSAGES as FR
from app.shares.locales.ru import MESSAGES as RU
from app.shares.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)

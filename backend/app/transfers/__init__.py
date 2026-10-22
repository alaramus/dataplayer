from app.core.translation import register
from app.transfers.locales.de import MESSAGES as DE
from app.transfers.locales.fr import MESSAGES as FR
from app.transfers.locales.hi import MESSAGES as HI
from app.transfers.locales.ru import MESSAGES as RU
from app.transfers.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)

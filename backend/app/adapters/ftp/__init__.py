# Imported for the side effect: the driver registers itself on import.
from app.adapters.ftp import adapter  # noqa: F401
from app.adapters.ftp.locales.ar import MESSAGES as AR
from app.adapters.ftp.locales.de import MESSAGES as DE
from app.adapters.ftp.locales.es import MESSAGES as ES
from app.adapters.ftp.locales.fr import MESSAGES as FR
from app.adapters.ftp.locales.hi import MESSAGES as HI
from app.adapters.ftp.locales.ru import MESSAGES as RU
from app.adapters.ftp.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

# Imported for the side effect: the driver registers itself on import.
from app.adapters.s3 import adapter  # noqa: F401
from app.adapters.s3.locales.ar import MESSAGES as AR
from app.adapters.s3.locales.de import MESSAGES as DE
from app.adapters.s3.locales.es import MESSAGES as ES
from app.adapters.s3.locales.fr import MESSAGES as FR
from app.adapters.s3.locales.hi import MESSAGES as HI
from app.adapters.s3.locales.ru import MESSAGES as RU
from app.adapters.s3.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

from app.adapters.kubernetes import adapter  # noqa: F401
from app.adapters.kubernetes.locales.ar import MESSAGES as AR
from app.adapters.kubernetes.locales.de import MESSAGES as DE
from app.adapters.kubernetes.locales.es import MESSAGES as ES
from app.adapters.kubernetes.locales.fr import MESSAGES as FR
from app.adapters.kubernetes.locales.hi import MESSAGES as HI
from app.adapters.kubernetes.locales.ru import MESSAGES as RU
from app.adapters.kubernetes.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

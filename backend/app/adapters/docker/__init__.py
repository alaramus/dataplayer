from app.adapters.docker import adapter  # noqa: F401
from app.adapters.docker.locales.ar import MESSAGES as AR
from app.adapters.docker.locales.de import MESSAGES as DE
from app.adapters.docker.locales.es import MESSAGES as ES
from app.adapters.docker.locales.fr import MESSAGES as FR
from app.adapters.docker.locales.hi import MESSAGES as HI
from app.adapters.docker.locales.ru import MESSAGES as RU
from app.adapters.docker.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

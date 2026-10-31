from app.adapters.zookeeper import adapter  # noqa: F401
from app.adapters.zookeeper.locales.ar import MESSAGES as AR
from app.adapters.zookeeper.locales.de import MESSAGES as DE
from app.adapters.zookeeper.locales.es import MESSAGES as ES
from app.adapters.zookeeper.locales.fr import MESSAGES as FR
from app.adapters.zookeeper.locales.hi import MESSAGES as HI
from app.adapters.zookeeper.locales.ru import MESSAGES as RU
from app.adapters.zookeeper.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

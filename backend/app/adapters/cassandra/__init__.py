from app.adapters.cassandra import adapter  # noqa: F401
from app.adapters.cassandra.locales.ar import MESSAGES as AR
from app.adapters.cassandra.locales.de import MESSAGES as DE
from app.adapters.cassandra.locales.es import MESSAGES as ES
from app.adapters.cassandra.locales.fr import MESSAGES as FR
from app.adapters.cassandra.locales.hi import MESSAGES as HI
from app.adapters.cassandra.locales.ru import MESSAGES as RU
from app.adapters.cassandra.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

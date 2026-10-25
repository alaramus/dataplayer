# Imported for the side effect: drivers register themselves on import.
from app.adapters import (  # noqa: F401
    clickhouse,
    file,
    mysql,
    postgres,
    redis,
    sqlite,
    ssh,
)
from app.adapters.locales.de import MESSAGES as DE
from app.adapters.locales.es import MESSAGES as ES
from app.adapters.locales.fr import MESSAGES as FR
from app.adapters.locales.hi import MESSAGES as HI
from app.adapters.locales.ru import MESSAGES as RU
from app.adapters.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

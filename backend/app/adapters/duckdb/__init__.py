from app.adapters.duckdb import adapter  # noqa: F401
from app.adapters.duckdb.locales.ar import MESSAGES as AR
from app.adapters.duckdb.locales.de import MESSAGES as DE
from app.adapters.duckdb.locales.es import MESSAGES as ES
from app.adapters.duckdb.locales.fr import MESSAGES as FR
from app.adapters.duckdb.locales.hi import MESSAGES as HI
from app.adapters.duckdb.locales.ru import MESSAGES as RU
from app.adapters.duckdb.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

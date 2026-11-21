from app.adapters.content import register_database_reader
from app.adapters.duckdb import adapter  # noqa: F401
from app.adapters.duckdb.file_tables import tables_of
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
register_database_reader("duckdb", tables_of)

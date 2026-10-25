from app.adapters.clickhouse import adapter  # noqa: F401
from app.adapters.clickhouse.locales.de import MESSAGES as DE
from app.adapters.clickhouse.locales.es import MESSAGES as ES
from app.adapters.clickhouse.locales.fr import MESSAGES as FR
from app.adapters.clickhouse.locales.hi import MESSAGES as HI
from app.adapters.clickhouse.locales.ru import MESSAGES as RU
from app.adapters.clickhouse.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

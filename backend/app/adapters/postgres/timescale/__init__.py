"""TimescaleDB support composed into the PostgreSQL adapter (D119)."""

from app.adapters.postgres.timescale.locales.ar import MESSAGES as AR
from app.adapters.postgres.timescale.locales.de import MESSAGES as DE
from app.adapters.postgres.timescale.locales.es import MESSAGES as ES
from app.adapters.postgres.timescale.locales.fr import MESSAGES as FR
from app.adapters.postgres.timescale.locales.hi import MESSAGES as HI
from app.adapters.postgres.timescale.locales.ru import MESSAGES as RU
from app.adapters.postgres.timescale.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

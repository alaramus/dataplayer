"""TimescaleDB support composed into the PostgreSQL adapter (D119)."""

from app.adapters.postgres.timescale.locales.de import MESSAGES as DE
from app.adapters.postgres.timescale.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("de", DE)

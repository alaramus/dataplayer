"""Metrics: agents, the installation's store, collection and history (D125-D130)."""

from app.core.translation import register
from app.metrics.locales.de import MESSAGES as DE
from app.metrics.locales.es import MESSAGES as ES
from app.metrics.locales.fr import MESSAGES as FR
from app.metrics.locales.hi import MESSAGES as HI
from app.metrics.locales.ru import MESSAGES as RU
from app.metrics.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

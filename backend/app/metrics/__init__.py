"""Metrics: agents, the installation's store, collection and history (D125-D130)."""

from app.core.translation import register
from app.metrics.locales.de import MESSAGES as DE
from app.metrics.locales.fr import MESSAGES as FR
from app.metrics.locales.ru import MESSAGES as RU

register("ru", RU)
register("fr", FR)
register("de", DE)

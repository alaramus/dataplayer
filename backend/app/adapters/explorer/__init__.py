"""The file explorer: a tree of files, wherever it is kept (D150)."""

from app.adapters.explorer.locales.de import MESSAGES as DE
from app.adapters.explorer.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("de", DE)

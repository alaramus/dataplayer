"""The file explorer: a tree of files, wherever it is kept (D150)."""

from app.adapters.explorer.locales.de import MESSAGES as DE
from app.adapters.explorer.locales.fr import MESSAGES as FR
from app.adapters.explorer.locales.ru import MESSAGES as RU
from app.adapters.explorer.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)

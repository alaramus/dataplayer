"""Terminals: a shell on a source's machine, one socket each (D148, D149)."""

from app.core.translation import register
from app.terminals.locales.de import MESSAGES as DE
from app.terminals.locales.es import MESSAGES as ES
from app.terminals.locales.fr import MESSAGES as FR
from app.terminals.locales.hi import MESSAGES as HI
from app.terminals.locales.ru import MESSAGES as RU
from app.terminals.locales.zh import MESSAGES as ZH

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)

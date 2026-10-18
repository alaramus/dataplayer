"""Terminals: a shell on a source's machine, one socket each (D148, D149)."""

from app.core.translation import register
from app.terminals.locales.de import MESSAGES as DE
from app.terminals.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

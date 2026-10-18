# Imported for the side effect: the driver registers itself on import.
from app.adapters.file import adapter  # noqa: F401
from app.adapters.file.locales.de import MESSAGES as DE
from app.adapters.file.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("de", DE)

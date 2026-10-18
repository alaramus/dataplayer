# Imported for the side effect: the driver registers itself on import.
from app.adapters.ssh import adapter  # noqa: F401
from app.adapters.ssh.locales.de import MESSAGES as DE
from app.adapters.ssh.locales.ru import MESSAGES as RU
from app.core.translation import register

register("ru", RU)
register("de", DE)

# Imported for the side effect: the driver registers itself on import.
from app.adapters.ssh import adapter  # noqa: F401
from app.adapters.ssh.locales.de import MESSAGES as DE
from app.adapters.ssh.locales.fr import MESSAGES as FR
from app.adapters.ssh.locales.ru import MESSAGES as RU
from app.adapters.ssh.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)

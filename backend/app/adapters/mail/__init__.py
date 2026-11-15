from app.adapters.mail import adapter  # noqa: F401
from app.adapters.mail.locales.ar import MESSAGES as AR
from app.adapters.mail.locales.de import MESSAGES as DE
from app.adapters.mail.locales.es import MESSAGES as ES
from app.adapters.mail.locales.fr import MESSAGES as FR
from app.adapters.mail.locales.hi import MESSAGES as HI
from app.adapters.mail.locales.ru import MESSAGES as RU
from app.adapters.mail.locales.zh import MESSAGES as ZH
from app.core.translation import register

register("ru", RU)
register("fr", FR)
register("de", DE)
register("zh", ZH)
register("hi", HI)
register("es", ES)
register("ar", AR)

"""The user's guide: how the application works for the person using it (D183).

Pages are Markdown files in `pages/`, written for people rather than about the
code. The source-type catalog reads its short lists from them, and the agent is
meant to read the same pages later.
"""

from app.core.translation import register
from app.guide.locales.de import MESSAGES as DE
from app.guide.locales.fr import MESSAGES as FR
from app.guide.locales.hi import MESSAGES as HI
from app.guide.locales.ru import MESSAGES as RU
from app.guide.locales.zh import MESSAGES as ZH

register("de", DE)
register("ru", RU)
register("fr", FR)
register("zh", ZH)
register("hi", HI)

"""The user's guide: how the application works for the person using it (D183).

Pages are Markdown files in `pages/`, written for people rather than about the
code. The source-type catalog reads its short lists from them, and the agent is
meant to read the same pages later.
"""

from app.core.translation import register
from app.guide.locales.de import MESSAGES as DE
from app.guide.locales.ru import MESSAGES as RU

register("de", DE)
register("ru", RU)

"""One search over everything a person may see (D197–D205).

The engine asks providers — one per kind of application object, one per
connection — and never a source type directly. See
`docs/architecture/search.md`.
"""

from app.core.translation import register
from app.search.locales.de import MESSAGES as DE
from app.search.locales.ru import MESSAGES as RU

register("ru", RU)
register("de", DE)

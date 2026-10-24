"""Reading the guide's pages, and the two short lists a source page opens with."""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from app.core.translation import N_, Language, current_language, say

PAGES_DIR = Path(__file__).with_name("pages")

# A key is a file's stem and the only thing a client names. It is looked up
# among the files read at start, never joined onto a path (D8).
KEY = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# The headings whose top-level bullets are the short lists in the catalog. A
# translated page may keep them in English or use their translation.
CAN_SEE = N_("What you can see")
CAN_CHANGE = N_("What you can change")


class GuidePageInfo(BaseModel):
    key: str
    title: str


class GuidePage(GuidePageInfo):
    markdown: str


def source_page_key(adapter_type: str) -> str:
    """The page about one source type."""
    return f"source-{adapter_type}"


def parse(key: str, markdown: str) -> GuidePage:
    """One page, refused when it has no `# ` title to be listed by."""
    for line in markdown.splitlines():
        if line.startswith("# "):
            return GuidePage(key=key, title=line[2:].strip(), markdown=markdown)
    raise ValueError(f"Guide page {key} has no title")


def read(folder: Path | None = None) -> dict[str, GuidePage]:
    """Every page in a folder, by key. Raises on a file that is not a page."""
    found: dict[str, GuidePage] = {}
    for path in sorted((folder or PAGES_DIR).glob("*.md")):
        if not KEY.match(path.stem):
            raise ValueError(f"Guide page name is not a key: {path.name}")
        found[path.stem] = parse(path.stem, path.read_text(encoding="utf-8"))
    return found


@cache
def pages() -> dict[str, GuidePage]:
    """The English pages this build shipped with, read once per process."""
    return read()


@cache
def translated(language: Language) -> dict[str, GuidePage]:
    """A language's own pages, `pages/<language>/<key>.md` (D227). Raises on a
    page English lacks: a key is English's, and a link names it."""
    own = PAGES_DIR / language
    if language == "en" or not own.is_dir():
        return {}
    found = read(own)
    stray = sorted(set(found) - set(pages()))
    if stray:
        raise ValueError(
            f"Guide pages in {language} that English lacks: {', '.join(stray)}"
        )
    return found


def pages_in(language: Language | None = None) -> dict[str, GuidePage]:
    """Every page in the request's language, the English where one has no
    translation, in English's order."""
    own = translated(language or current_language.get())
    return {key: own.get(key, english) for key, english in pages().items()}


def page(key: str) -> GuidePage | None:
    return pages_in().get(key)


def bullets(markdown: str, heading: str) -> list[str]:
    """The top-level bullets under one `## ` heading, each as one line of text.

    A bullet wrapped onto indented lines in the page is one item: the lines
    under it are joined to it. Taking only its first line cut every wrapped
    item short in the catalog's panel.
    """
    items: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() in (heading, say(heading))
            continue
        if not inside:
            continue
        if line.startswith("- "):
            items.append(line[2:].strip())
        elif items and line.startswith(" ") and line.strip():
            items[-1] = f"{items[-1]} {line.strip()}"
        elif not line.strip() and items:
            # A blank line ends the item it follows; the list may go on.
            continue
    return items

"""Reading the guide's pages, and the two short lists a source page opens with."""

import re
from functools import cache
from pathlib import Path

from pydantic import BaseModel

PAGES_DIR = Path(__file__).with_name("pages")

# A key is a file's stem and the only thing a client names. It is looked up
# among the files read at start, never joined onto a path (D8).
KEY = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# The headings whose top-level bullets are the short lists in the catalog.
CAN_SEE = "What you can see"
CAN_CHANGE = "What you can change"


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


def read(folder: Path = PAGES_DIR) -> dict[str, GuidePage]:
    """Every page in a folder, by key. Raises on a file that is not a page."""
    found: dict[str, GuidePage] = {}
    for path in sorted(folder.glob("*.md")):
        if not KEY.match(path.stem):
            raise ValueError(f"Guide page name is not a key: {path.name}")
        found[path.stem] = parse(path.stem, path.read_text(encoding="utf-8"))
    return found


@cache
def pages() -> dict[str, GuidePage]:
    """The pages this build shipped with, read once per process."""
    return read()


def page(key: str) -> GuidePage | None:
    return pages().get(key)


def bullets(markdown: str, heading: str) -> list[str]:
    """The top-level bullets under one `## ` heading, each on one line."""
    items: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == heading
            continue
        if inside and line.startswith("- "):
            items.append(line[2:].strip())
    return items

"""The agent's `read_guide` tool: the user's guide, a page or one section at a time (D359).

The guide is the application's own text, not a person's data, so no
connection's transfer flag stands in front of it (D135).
"""

from typing import Any

from anyio import to_thread

from app.core.translation import Language
from app.guide import reader

DESCRIPTION = (
    "Read DataPlayer's user guide: how the application, its screens and each "
    "kind of source work for the person using them. Use it for any question about "
    "how DataPlayer works instead of guessing. Without key: every page with its "
    "key, title and section headings. With key: the whole page. With key and "
    "section: that one section, the cheaper read once the heading is known. A "
    "link to `name.md` in a page is the page with key `name`. `search` also finds "
    "guide pages by their words."
)


def sections(markdown: str) -> list[str]:
    return [line[3:].strip() for line in markdown.splitlines() if line.startswith("## ")]


def section_text(markdown: str, heading: str) -> str | None:
    """One `## ` section with what is under it, its `### ` parts included."""
    wanted = heading.strip().removeprefix("## ").strip().casefold()
    lines: list[str] = []
    inside = False
    for line in markdown.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip().casefold() == wanted
        if inside:
            lines.append(line)
    return "\n".join(lines).strip() or None


def answer(
    pages: dict[str, reader.GuidePage], key: str | None, section: str | None
) -> dict[str, Any]:
    if key is None:
        return {
            "pages": [
                {"key": one.key, "title": one.title, "sections": sections(one.markdown)}
                for one in pages.values()
            ]
        }
    page = pages.get(key)
    if page is None:
        return {"error": "No guide page has this key. Call read_guide without a key for the list."}
    if section is None:
        return {"key": page.key, "title": page.title, "markdown": page.markdown}
    text = section_text(page.markdown, section)
    if text is None:
        return {
            "error": "This page has no such section.",
            "key": page.key,
            "sections": sections(page.markdown),
        }
    return {"key": page.key, "title": page.title, "section": text}


async def read_guide(
    language: Language, key: str | None, section: str | None
) -> dict[str, Any]:
    """In the person's language, where a page has a translation (D227): the
    names of buttons in it are the ones on their screen."""
    pages = await to_thread.run_sync(reader.pages_in, language)
    return answer(pages, key, section)

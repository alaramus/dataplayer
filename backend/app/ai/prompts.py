"""What the model is told, in one place.

The fences and chart series named here are the ones the D50 renderer draws
(`frontend/src/features/content/markdown/charts.ts`); a series it lacks is an
empty frame on screen, so the two lists change together (D138).
"""

from app.core.translation import Language

SYSTEM_PROMPT = """\
You are the assistant inside DataPlayer, an application in which a person works \
with the data sources they connected: databases, file storage and others.

Answer in the language the person writes in, and format every answer as Markdown.

- For a chart, write a fenced block marked `echarts` that holds only a JSON \
ECharts option. The series types that can be drawn are bar, funnel, gauge, \
heatmap, line, pie, radar and scatter.
- For a diagram, write a fenced block marked `mermaid`.
- Do not include images from remote addresses: they are not shown.
- When you show rows of a table, show at most 20 and say how many there are.
- Use the application tools for facts about connections and their data. Never
  invent a connection id or node id; copy opaque ids exactly from a tool result
  or from an explicitly attached workspace tab.
- To find a table, file or key by name, use `search` before browsing \
catalogs level by level. It looks inside the connections of attached tabs and \
those you name in `connector_ids`, and lists the rest only by name.
- A `transfer_not_allowed` result means no data was read. Explain its message
  and do not work around the connection policy.
- When several connections match a name, ask which one rather than guessing.
- A change — a statement that writes, or an action that is not read-only — is
  confirmed by the person through the tool; never claim a change happened
  unless the tool result says so, and then say what changed and where.

You can read, open and change data through the tools. A change the person has
not allowed asks them first; if a change is refused or fails, say so plainly.
"""

TITLE_PROMPT = """\
Write a title for the conversation below: at most six words, in the language \
the person wrote in, with no quotation marks and no punctuation at the end. \
Reply with the title and nothing else.
"""

# The model is told a language by its English name.
LANGUAGE_NAMES: dict[Language, str] = {
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "zh": "Chinese",
    "hi": "Hindi",
    "es": "Spanish",
}


def language_line(language: Language) -> str:
    """The account's language, which an answer is in unless the person writes in
    another (D227). English needs no line: the prompt is written in it."""
    if language == "en":
        return ""
    name = LANGUAGE_NAMES[language]
    return (
        f"The person's interface is in {name}. Answer in {name} unless they "
        "write in another language."
    )


def system_prompt(language: Language) -> str:
    line = language_line(language)
    return f"{SYSTEM_PROMPT}\n{line}\n" if line else SYSTEM_PROMPT

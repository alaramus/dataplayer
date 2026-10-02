"""Text cut into segments, the words that matched marked (D198).

The words are case-folded and so is the text, but folding can change a
string's length — `ß` folds to `ss` — so positions in the folded text are
mapped back to the original one character at a time rather than assumed to
line up.
"""

from collections.abc import Sequence

from app.adapters.search import MAX_EXCERPT_CHARACTERS
from app.search.models import Segment

ELLIPSIS = "…"


def _folded(text: str) -> tuple[str, list[int]]:
    """The text case-folded, and for every folded character where it came from."""
    characters: list[str] = []
    origins: list[int] = []
    for index, character in enumerate(text):
        for folded in character.casefold():
            characters.append(folded)
            origins.append(index)
    return "".join(characters), origins


def spans(text: str, words: Sequence[str]) -> list[tuple[int, int]]:
    """Where in the original text every word occurs, merged, in order."""
    folded, origins = _folded(text)
    found: list[tuple[int, int]] = []
    for word in words:
        if word == "":
            continue
        start = folded.find(word)
        while start != -1:
            end = start + len(word)
            found.append((origins[start], origins[end - 1] + 1))
            start = folded.find(word, end)
    found.sort()
    merged: list[tuple[int, int]] = []
    for start, end in found:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def segments(
    text: str, words: Sequence[str], *, limit: int = MAX_EXCERPT_CHARACTERS
) -> list[Segment]:
    """At most `limit` characters of the text around the first hit, marked.

    A line longer than the limit is cut on both sides of the first word found,
    each cut said with an ellipsis, so a hit at the end of a long line is still
    shown rather than cut away.
    """
    text = " ".join(text.split())
    found = spans(text, words)
    start, end = 0, len(text)
    if end > limit:
        # Room for an ellipsis on either side, so the whole stays in the limit.
        size = limit - 2
        first = found[0][0] if found else 0
        start = max(0, min(first - size // 4, len(text) - size))
        end = start + size
    window = [
        (max(a, start), min(b, end)) for a, b in found if b > start and a < end
    ]
    cut: list[Segment] = []
    if start > 0:
        cut.append(Segment(text=ELLIPSIS))
    position = start
    for a, b in window:
        if a > position:
            cut.append(Segment(text=text[position:a]))
        cut.append(Segment(text=text[a:b], hit=True))
        position = b
    if position < end:
        cut.append(Segment(text=text[position:end]))
    if end < len(text):
        cut.append(Segment(text=ELLIPSIS))
    return _joined(cut)


def _joined(cut: list[Segment]) -> list[Segment]:
    """Neighbours of one kind as one segment: an ellipsis is plain text too."""
    joined: list[Segment] = []
    for one in cut:
        if joined and joined[-1].hit == one.hit:
            joined[-1] = Segment(text=joined[-1].text + one.text, hit=one.hit)
        else:
            joined.append(one)
    return joined

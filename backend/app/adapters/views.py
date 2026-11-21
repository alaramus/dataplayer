"""A node's document drawn as a page of blocks (D419–D421).

A source that describes a node in a JSON document of its own can also say what
that document means. The page is a closed set of blocks and values, so a block
the client cannot draw fails here rather than vanishing on screen; the client
lays it out and knows no source. Every word in it is the source's, already
through `say()`, and every value is what is shown, never text to parse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

# The ceilings of D419. Past one a block says how many it left out; the
# document beside the view has them all.
MAX_BLOCKS = 200
MAX_ROWS = 500
MAX_TEXT = 16 * 1024

Tone = Literal["good", "busy", "warning", "bad", "neutral"]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- values ------------------------------------------------------------------


class TextValue(_Closed):
    kind: Literal["text"] = "text"
    text: str = Field(max_length=MAX_TEXT)
    truncated: bool = False


class CodeValue(_Closed):
    """Monospaced, with a copy button."""

    kind: Literal["code"] = "code"
    text: str = Field(max_length=MAX_TEXT)
    truncated: bool = False


class NumberValue(_Closed):
    kind: Literal["number"] = "number"
    value: float
    unit: str | None = None


class BytesValue(_Closed):
    """A size, drawn in the reader's units."""

    kind: Literal["bytes"] = "bytes"
    value: int = Field(ge=0)


class MomentValue(_Closed):
    """An instant, drawn as the date and how long ago."""

    kind: Literal["moment"] = "moment"
    value: AwareDatetime


class DurationValue(_Closed):
    kind: Literal["duration"] = "duration"
    seconds: float = Field(ge=0)


class BooleanValue(_Closed):
    kind: Literal["boolean"] = "boolean"
    value: bool


class StateValue(_Closed):
    """A word and the meaning of it; the client turns the tone into a colour."""

    kind: Literal["state"] = "state"
    word: str = Field(min_length=1, max_length=200)
    tone: Tone = "neutral"


class ListValue(_Closed):
    """Short texts, drawn as chips."""

    kind: Literal["list"] = "list"
    items: list[str] = Field(max_length=MAX_ROWS)
    omitted: int = Field(default=0, ge=0)


class LinkValue(_Closed):
    """Text that opens another node of the same connection, by its id (D21)."""

    kind: Literal["link"] = "link"
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    node_id: str = Field(min_length=1, max_length=2048)


class EmptyValue(_Closed):
    """Not there, drawn as a dash: "not set" told apart from "not shown"."""

    kind: Literal["empty"] = "empty"


ViewValue = Annotated[
    TextValue
    | CodeValue
    | NumberValue
    | BytesValue
    | MomentValue
    | DurationValue
    | BooleanValue
    | StateValue
    | ListValue
    | LinkValue
    | EmptyValue,
    Field(discriminator="kind"),
]


# --- blocks ------------------------------------------------------------------


class ViewHeader(_Closed):
    """Once, at the top."""

    title: str = Field(min_length=1, max_length=MAX_TEXT)
    subtitle: ViewValue | None = None
    state: StateValue | None = None


class ViewField(_Closed):
    label: str = Field(min_length=1, max_length=200)
    value: ViewValue


class FieldsBlock(_Closed):
    kind: Literal["fields"] = "fields"
    fields: list[ViewField] = Field(max_length=MAX_ROWS)


class ViewPair(_Closed):
    name: str = Field(max_length=MAX_TEXT)
    value: str = Field(max_length=MAX_TEXT)
    # Drawn hidden until asked for (D421). The value still arrives: this hides
    # from a glance, not from a reader.
    sensitive: bool = False


class PairsBlock(_Closed):
    kind: Literal["pairs"] = "pairs"
    pairs: list[ViewPair] = Field(max_length=MAX_ROWS)
    omitted: int = Field(default=0, ge=0)


class TableBlock(_Closed):
    kind: Literal["table"] = "table"
    columns: list[str] = Field(min_length=1, max_length=50)
    rows: list[list[ViewValue]] = Field(max_length=MAX_ROWS)
    omitted: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def rows_fit_columns(self) -> TableBlock:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Every row of a table has one value per column")
        return self


class NoticeBlock(_Closed):
    """A sentence the source wants read."""

    kind: Literal["notice"] = "notice"
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    tone: Tone = "neutral"


SectionChild = Annotated[
    FieldsBlock | PairsBlock | TableBlock | NoticeBlock,
    Field(discriminator="kind"),
]


class SectionBlock(_Closed):
    """A title and the blocks under it. Sections do not nest."""

    kind: Literal["section"] = "section"
    title: str = Field(min_length=1, max_length=200)
    collapsed: bool = False
    blocks: list[SectionChild] = Field(max_length=MAX_BLOCKS)


ViewBlock = Annotated[
    SectionBlock | FieldsBlock | PairsBlock | TableBlock | NoticeBlock,
    Field(discriminator="kind"),
]


class DocumentView(_Closed):
    """What a node's document means, as its source says it (D420)."""

    kind: Literal["view"] = "view"
    header: ViewHeader
    blocks: list[ViewBlock] = Field(max_length=MAX_BLOCKS)

    @model_validator(mode="after")
    def bounded(self) -> DocumentView:
        count = sum(
            1 + (len(block.blocks) if isinstance(block, SectionBlock) else 0)
            for block in self.blocks
        )
        if count > MAX_BLOCKS:
            raise ValueError(f"A view holds at most {MAX_BLOCKS} blocks")
        return self


# --- building one --------------------------------------------------------------


def text(value: str) -> TextValue:
    """Text, cut at the ceiling rather than refused."""
    clipped = _clip(value)
    return TextValue(text=clipped, truncated=clipped != value)


def code(value: str) -> CodeValue:
    clipped = _clip(value)
    return CodeValue(text=clipped, truncated=clipped != value)


def moment(value: datetime | None) -> MomentValue | EmptyValue:
    return EmptyValue() if value is None else MomentValue(value=value)


def chips(items: list[str]) -> ListValue:
    kept = [_clip(item) for item in items[:MAX_ROWS]]
    return ListValue(items=kept, omitted=max(len(items) - MAX_ROWS, 0))


def pairs(found: list[ViewPair]) -> PairsBlock:
    return PairsBlock(pairs=found[:MAX_ROWS], omitted=max(len(found) - MAX_ROWS, 0))


def table(columns: list[str], rows: list[list[ViewValue]]) -> TableBlock:
    return TableBlock(
        columns=columns, rows=rows[:MAX_ROWS], omitted=max(len(rows) - MAX_ROWS, 0)
    )


def _clip(value: str) -> str:
    # Characters, as Pydantic counts `max_length`.
    return value if len(value) <= MAX_TEXT else value[:MAX_TEXT]

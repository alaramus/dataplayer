"""What a shared link says a reader should be looking at.

D59: the body is a discriminated union on `kind`, and a change that breaks
reading is a new variant rather than a version field. A version field turns
into a chain of `if version ==`, which is the branching this project replaces
with types.

Only one variant exists: a page of rows. It carries what the sender's grid was
showing — the query and the way the columns were arranged — and deliberately
not the page number: under a filter the reader's page three holds different
rows, so a shared offset points somewhere else, while the query means the same
thing on both screens.
"""

import hashlib
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.fetch import MAX_LIMIT, Filter, Sort

# A relation with more columns than this is not something a grid layout
# describes usefully, and the ceiling is here because the body arrives from a
# client and is stored.
MAX_COLUMNS = 500
MAX_NAME = 255


def _named_within(values: dict[str, object]) -> None:
    if len(values) > MAX_COLUMNS:
        raise ValueError(f"at most {MAX_COLUMNS} columns")
    for name in values:
        if len(name) > MAX_NAME:
            raise ValueError(f"a column name is at most {MAX_NAME} characters")


class RowsView(BaseModel):
    """A bounded page of a relation, as the sender had it arranged.

    The two maps are maps and not shapes: their keys are column names, which
    belong to the source and are not known here. They are still bounded, in
    length and in the size of a key.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["rows"] = "rows"
    filters: list[Filter] = Field(default_factory=list, max_length=MAX_COLUMNS)
    sort: list[Sort] = Field(default_factory=list, max_length=MAX_COLUMNS)
    page_size: int = Field(default=100, ge=1, le=MAX_LIMIT)
    column_order: list[str] = Field(default_factory=list, max_length=MAX_COLUMNS)
    pinned_left: list[str] = Field(default_factory=list, max_length=MAX_COLUMNS)
    column_visibility: dict[str, bool] = Field(default_factory=dict)
    column_sizing: dict[str, float] = Field(default_factory=dict)

    @field_validator("column_order", "pinned_left")
    @classmethod
    def _names_are_bounded(cls, value: list[str]) -> list[str]:
        for name in value:
            if len(name) > MAX_NAME:
                raise ValueError(f"a column name is at most {MAX_NAME} characters")
        return value

    @field_validator("column_visibility")
    @classmethod
    def _visibility_is_bounded(cls, value: dict[str, bool]) -> dict[str, bool]:
        _named_within(dict(value))
        return value

    @field_validator("column_sizing")
    @classmethod
    def _sizing_is_bounded(cls, value: dict[str, float]) -> dict[str, float]:
        _named_within(dict(value))
        for width in value.values():
            if not 0 < width <= 10_000:
                raise ValueError("a column width is a positive number of pixels")
        return value


# One variant so far, so this is the variant itself. A second kind of tab makes
# it `Annotated[RowsView | ChartView, Field(discriminator="kind")]`, which is a
# change of this line and of nothing that stores or carries a body: `kind` is
# already written, already required and already checked.
SharedView = RowsView


def fingerprint_of(connector_id: uuid.UUID, node_id: str, view: RowsView) -> str:
    """What makes two shares the same share.

    D59: pressing Share twice on the same view returns the same record, so the
    button does not mint a second address for one thing. The digest is over the
    validated body rather than the request, so two clients that send the same
    view with different key order or omitted defaults still match.
    """
    material = f"{connector_id}\n{node_id}\n{view.model_dump_json()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()

"""Tables a person declares over what a source keeps without structure (D170).

A declaration is the application's, kept with the connection rather than in
the source; the driver is handed the ones it has and shows each as a table.
Which nodes can carry one, and what a column may not be called, is the
driver's to say.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DeclaredType = Literal["text", "number", "boolean", "datetime"]

MAX_DECLARED_COLUMNS = 200
MAX_DECLARED_NAME = 255
MAX_PLACE_ID = 1024


class DeclaredColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_DECLARED_NAME)
    type: DeclaredType = "text"

    @field_validator("name")
    @classmethod
    def name_is_written(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A column needs a name")
        return stripped


class _TableShape(BaseModel):
    """A name and its columns, the same rules whoever writes them."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_DECLARED_NAME)
    # In the order the table shows them.
    columns: list[DeclaredColumn] = Field(min_length=1, max_length=MAX_DECLARED_COLUMNS)

    @field_validator("name")
    @classmethod
    def table_name_is_written(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A table needs a name")
        return stripped

    @field_validator("columns")
    @classmethod
    def columns_are_unique(cls, value: list[DeclaredColumn]) -> list[DeclaredColumn]:
        names = [column.name for column in value]
        if len(names) != len(set(names)):
            raise ValueError("Two columns have the same name")
        return value


class DeclaredTable(_TableShape):
    """One declaration, as the connection keeps it."""

    # The node whose contents are the rows: a Redis folder. One table per place.
    place_id: str = Field(min_length=1, max_length=MAX_PLACE_ID)


class DeclareTableRequest(_TableShape):
    """A declaration as a person writes it, on the node they chose."""

    # A folder, or the table already declared over one.
    node_id: str = Field(min_length=1, max_length=MAX_PLACE_ID)


class TablePlace(BaseModel):
    """Where a declaration over a node would stand, and what already does."""

    model_config = ConfigDict(extra="forbid")

    place_id: str
    # The level the table is listed in, beside its place: what a catalog
    # re-reads once the declaration changes.
    listed_in: str
    declared: DeclaredTable | None = None


class ProposedColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: DeclaredType
    ticked: bool
    # How many of the sampled keys hold it; zero for a declared column the
    # sample did not meet.
    found_in: int


class TableProposal(BaseModel):
    """What the declaration window starts from."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str
    columns: list[ProposedColumn]
    # How many keys the fields were read from.
    sampled: int
    declared: bool
    # Names a column may not take, because the table's own first column has it.
    reserved: list[str] = Field(default_factory=list)

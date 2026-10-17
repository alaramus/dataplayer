"""Source-independent commands for the constraints of one relation.

Two kinds are reachable: a unique constraint and a foreign key. A check
constraint is not, and never will be through this door — its body is an
expression, which is what D2c refuses.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.relation import RefAction
from app.core.translation import say


class UniqueConstraintSpec(BaseModel):
    """A promise that these columns together name at most one row."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["unique"] = "unique"
    columns: Annotated[list[str], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def distinct_columns(self) -> UniqueConstraintSpec:
        if len(self.columns) != len(set(self.columns)):
            raise ValueError(say("A column may appear in a constraint only once"))
        return self


class ForeignKeySpec(BaseModel):
    """A promise that these columns name a row of another relation.

    The target is a catalog node id, handed back exactly as it was given (D21);
    its columns are one of the candidate keys the target itself publishes, so
    the client never decides what may be referenced.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["foreign_key"] = "foreign_key"
    columns: Annotated[list[str], Field(min_length=1, max_length=32)]
    target_node_id: str
    target_columns: Annotated[list[str], Field(min_length=1, max_length=32)]
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"

    @model_validator(mode="after")
    def distinct_and_paired(self) -> ForeignKeySpec:
        if len(self.columns) != len(set(self.columns)):
            raise ValueError(say("A column may appear in a constraint only once"))
        if len(self.columns) != len(self.target_columns):
            raise ValueError(say("A foreign key names as many columns as it points at"))
        return self


ConstraintSpec = Annotated[
    UniqueConstraintSpec | ForeignKeySpec,
    Field(discriminator="kind"),
]


class CreateConstraintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    constraint: ConstraintSpec


class DropConstraintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)


class ConstraintCreated(BaseModel):
    """The constraint exists, under the name the source gave it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["created"] = "created"
    name: str


class RepeatingValues(BaseModel):
    """A unique constraint was asked for and these many values already repeat."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["repeating"] = "repeating"
    groups: int
    exact: bool = True


class UnmatchedRows(BaseModel):
    """A foreign key was asked for and these many rows point at nothing.

    Separate from `RepeatingValues` rather than one count with a reason beside
    it: the two lead to different work — one value has to be made unique, one
    row has to be corrected or removed — and a screen that had to read which it
    was out of a sentence would be parsing prose.

    Rows holding a null anywhere in the key are not counted. That is MATCH
    SIMPLE, which is what PostgreSQL would apply, and counting them would
    refuse a key the server would have accepted.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["unmatched"] = "unmatched"
    rows: int
    exact: bool = True


CreateConstraintResult = Annotated[
    ConstraintCreated | RepeatingValues | UnmatchedRows,
    Field(discriminator="kind"),
]


class ConstraintDropped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

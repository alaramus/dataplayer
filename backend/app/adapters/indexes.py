"""Source-independent commands for the indexes of one relation.

Creating and dropping are one capability rather than two: a source that could
make an index and not unmake it would let a user build something they cannot
remove.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateIndexRequest(BaseModel):
    """Columns of this relation, a published method code, and uniqueness.

    No name: an index means nothing to a person beyond the columns it covers,
    so asking for one asks for a fact that has no answer, and the source
    already derives a name and makes it unique against its own schema. No
    predicate and no expression either — those are what D2c refuses.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    # In index order, which is not the relation's order and matters.
    columns: Annotated[list[str], Field(min_length=1, max_length=32)]
    method: str
    unique: bool = False

    @model_validator(mode="after")
    def distinct_columns(self) -> CreateIndexRequest:
        if len(self.columns) != len(set(self.columns)):
            raise ValueError("A column may appear in an index only once")
        return self


class DropIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)


class IndexCreated(BaseModel):
    """The index exists, under the name the source gave it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["created"] = "created"
    name: str


class IndexBlocked(BaseModel):
    """A unique index was asked for and the rows repeat, this many times over.

    Groups rather than rows: what breaks uniqueness is a value appearing more
    than once, and the number of such values is what somebody has to go and
    look at. Groups holding a null are not counted — PostgreSQL's default is
    NULLS DISTINCT, and two nulls do not collide.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["blocked"] = "blocked"
    duplicate_groups: int
    # False when counting stopped at its ceiling, as in NullabilityBlocked.
    exact: bool = True


CreateIndexResult = Annotated[
    IndexCreated | IndexBlocked,
    Field(discriminator="kind"),
]


class IndexDropped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

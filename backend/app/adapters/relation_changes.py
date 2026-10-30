"""Source-independent commands for creating a relation.

Creating a relation and filling it are one request on purpose. A table made
from a file is one thing the reader asked for, and only the source can put the
DDL and the rows into a single transaction; two requests would leave an empty
table behind every time the rows were refused, and this platform has no way to
drop one (D45).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.catalog import CatalogNode
from app.adapters.relation import ColumnTypeOption
from app.adapters.update import ValuesRejected
from app.core.translation import N_, say


def _plain(name: str, refusal: str) -> str:
    if name.strip() != name:
        raise ValueError(say(refusal))
    return name


class NewColumn(BaseModel):
    """One column of a relation that does not exist yet.

    Its name and its type, and deliberately nothing else. Requiring a value,
    a default and a key are changes to a relation that already exists, and
    each of them already has a command that says what stands in its way.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63)
    # The same opaque code a new column of an existing relation is given (D27).
    # Never SQL: the source alone turns it into DDL.
    type_code: str

    @model_validator(mode="after")
    def plain_name(self) -> NewColumn:
        _plain(self.name, N_("A column name cannot start or end with whitespace"))
        return self


class CreateRelationRequest(BaseModel):
    """A relation to create in one container, with the rows it starts with."""

    model_config = ConfigDict(extra="forbid")

    # The container it is created in — the source's own opaque id for it (D21).
    # The client never composes one out of a schema name.
    parent_node_id: str
    name: str = Field(min_length=1, max_length=63)
    columns: Annotated[list[NewColumn], Field(min_length=1, max_length=100)]
    # The first rows, values in the order of `columns`. An empty list is a
    # relation and no rows, which is a request worth making.
    rows: Annotated[list[list[str | None]], Field(max_length=5000)] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def named_once_and_rectangular(self) -> CreateRelationRequest:
        _plain(self.name, N_("A relation name cannot start or end with whitespace"))
        names = [column.name for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError(say("A column may be named only once"))
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError(say("Every row carries one value per column"))
        # No third ceiling on the product of the two: what a whole file may
        # weigh is a question for whoever supplies the rows, and the one place
        # that does today refuses a file over its own byte limit while it is
        # still arriving.
        return self


class RelationCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["created"] = "created"
    # The relation as the catalog describes it, so nothing on the client
    # composes an id or decides what kind of node this now is (D21).
    node: CatalogNode
    inserted: int


# Rejected values are the same answer they are for an insert, and the same
# model: the reason a value cannot cross is the column's type either way, and
# a second shape for it would only be a second thing to keep in step.
CreateRelationResult = Annotated[
    RelationCreated | ValuesRejected,
    Field(discriminator="kind"),
]


class NewRelationOptions(BaseModel):
    """What one container will accept a new relation with.

    Asked of a container rather than read off a relation, because there is no
    relation yet: `RelationModel` publishes the same vocabulary for a table
    that exists, and this is the answer to the same question one step earlier.
    A container that admits nothing says so with a reason, the way every other
    gate in that model does.
    """

    model_config = ConfigDict(extra="forbid")

    supported: bool = False
    reason: str | None = None
    column_type_options: list[ColumnTypeOption] = Field(default_factory=list)
    # The code a column of a delimited file takes: text of any length, since a
    # file states no types (D45). None where this container makes no such column.
    text_type: str | None = None

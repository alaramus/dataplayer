"""Source-independent commands for changing relation columns."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AddColumnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)
    type_code: str
    nullable: bool = True

    @model_validator(mode="after")
    def plain_name(self) -> AddColumnRequest:
        if self.name.strip() != self.name:
            raise ValueError("A column name cannot start or end with whitespace")
        return self


class DropColumnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)


class RenameColumnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)
    new_name: str = Field(min_length=1, max_length=63)

    @model_validator(mode="after")
    def plain_and_changed_name(self) -> RenameColumnRequest:
        if self.new_name.strip() != self.new_name:
            raise ValueError("A column name cannot start or end with whitespace")
        if self.name == self.new_name:
            raise ValueError("The new column name must be different")
        return self


class ColumnDefaultRequest(BaseModel):
    """Set a literal default, or remove the current default."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)
    action: Literal["set", "drop"]
    value: str | None = None

    @model_validator(mode="after")
    def value_matches_action(self) -> ColumnDefaultRequest:
        if self.action == "set" and self.value is None:
            raise ValueError("A literal value is required when setting a default")
        if self.action == "drop" and self.value is not None:
            raise ValueError("A value cannot be supplied when dropping a default")
        return self


class ColumnNullabilityRequest(BaseModel):
    """Ask a column to require a value, or to stop requiring one."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str = Field(min_length=1, max_length=63)
    nullable: bool


class NullabilityChanged(BaseModel):
    """The column now says what was asked of it."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["changed"] = "changed"
    name: str
    nullable: bool


class NullabilityBlocked(BaseModel):
    """Rows already there contradict the constraint, and here are how many.

    An answer rather than an error, for the reason `NoReferencedRows` is one:
    the request was well formed and the source is reporting a fact about the
    data. The number has to arrive as a number — a screen that reads it out of
    a message is a screen parsing prose — and the driver's own refusal cannot
    be passed on at all, because it quotes the offending row.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["blocked"] = "blocked"
    name: str
    rows_without_value: int
    # False when counting stopped at its ceiling: an unbounded scan is no more
    # acceptable here than it is for a page of rows.
    exact: bool = True


ColumnNullabilityResult = Annotated[
    NullabilityChanged | NullabilityBlocked,
    Field(discriminator="kind"),
]


class ColumnChangeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

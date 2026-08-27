"""Source-independent commands for changing relation columns."""

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


class ColumnChangeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str

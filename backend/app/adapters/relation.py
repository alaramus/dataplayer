"""What a source can say about one relation, whatever the source is."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TypeCategory = Literal[
    "number",
    "string",
    "boolean",
    "datetime",
    "binary",
    "json",
    "uuid",
    "network",
    "geometric",
    "range",
    "enum",
    "composite",
    "array",
    "other",
]
RelationKind = Literal[
    "table",
    "partitioned_table",
    "view",
    "materialized_view",
    "foreign_table",
]
Persistence = Literal["permanent", "unlogged", "temporary"]
RefAction = Literal["no_action", "restrict", "cascade", "set_null", "set_default"]
Storage = Literal["plain", "main", "external", "extended"]


class ColumnType(BaseModel):
    """A type's DDL spelling and its value semantics."""

    model_config = ConfigDict(extra="forbid")

    sql: str
    category: TypeCategory
    element: ColumnType | None = None
    dimensions: int = 0
    enum_values: list[str] | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int
    name: str
    type: ColumnType
    nullable: bool
    storage: Storage
    comment: str | None = None
    default: str | None = None
    identity: Literal["always", "by_default"] | None = None
    generated: str | None = None
    collation: str | None = None


class PrimaryKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["primary_key"] = "primary_key"
    name: str
    columns: list[str]


class UniqueConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["unique"] = "unique"
    name: str
    columns: list[str]
    nulls_not_distinct: bool = False


class ForeignKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["foreign_key"] = "foreign_key"
    name: str
    columns: list[str]
    target_node_id: str
    target_columns: list[str]
    on_update: RefAction = "no_action"
    on_delete: RefAction = "no_action"
    match: Literal["full", "partial", "simple"] = "simple"


class CheckConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["check"] = "check"
    name: str
    expression: str
    columns: list[str] = Field(default_factory=list)


class ExclusionConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["exclude"] = "exclude"
    name: str
    expression: str


Constraint = Annotated[
    PrimaryKey | UniqueConstraint | ForeignKey | CheckConstraint | ExclusionConstraint,
    Field(discriminator="kind"),
]


class Index(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    method: str
    unique: bool = False
    primary: bool = False
    valid: bool = True
    columns: list[str] = Field(default_factory=list)
    predicate: str | None = None
    definition: str


class Partitioning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["range", "list", "hash"]
    key: str


class PartitionOf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_node_id: str
    bounds: str


class ColumnTypeOption(BaseModel):
    """One source-owned DDL type choice; its code is not SQL."""

    model_config = ConfigDict(extra="forbid")

    code: str
    title: str
    sql: str


class RelationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    schema_name: str
    name: str
    kind: RelationKind
    owner: str
    persistence: Persistence
    comment: str | None = None
    row_estimate: int | None = None
    size_bytes: int | None = None
    columns: list[Column] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    indexes: list[Index] = Field(default_factory=list)
    partitioning: Partitioning | None = None
    partition_of: PartitionOf | None = None
    column_changes_supported: bool = False
    column_changes_reason: str | None = None
    column_type_options: list[ColumnTypeOption] = Field(default_factory=list)


def without_column_changes(model: RelationModel, reason: str) -> RelationModel:
    """The same description, with the shape of it declared unchangeable.

    The relation already says whether its columns can be changed and why not,
    and the structure screen already reads that. A caller who may not change
    the shape is told through the same two fields rather than by a screen
    knowing the rule; the type choices go with them, since they exist only to
    fill in a change nobody is being offered.
    """
    return model.model_copy(
        update={
            "column_changes_supported": False,
            "column_changes_reason": reason,
            "column_type_options": [],
        }
    )

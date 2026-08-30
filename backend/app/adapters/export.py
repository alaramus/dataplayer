"""A whole tabular read as bounded batches, never as one unbounded result."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adapters.fetch import Filter, Sort

EXPORT_BATCH_SIZE = 500


class ExportRequest(BaseModel):
    """Every row matching one safe query, in the requested column order."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    columns: list[str] = Field(min_length=1)
    filters: list[Filter] = Field(default_factory=list)
    sort: list[Sort] = Field(default_factory=list)

    @field_validator("columns")
    @classmethod
    def columns_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Export columns must be unique")
        return value


class ExportBatch(BaseModel):
    """One bounded piece of an export stream."""

    model_config = ConfigDict(extra="forbid")

    rows: list[list[str | None]] = Field(max_length=EXPORT_BATCH_SIZE)

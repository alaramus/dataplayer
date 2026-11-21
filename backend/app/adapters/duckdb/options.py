"""Which file of a person's storage a DuckDB source is (D387)."""

from pathlib import PurePosixPath

from pydantic import BaseModel, Field, field_validator

from app.adapters.home_file import below_home
from app.adapters.layout import layout
from app.core.translation import N_


class DuckdbOptions(BaseModel):
    path: str = Field(
        title=N_("Database file"),
        description=N_("Path of the file inside your personal storage, such as data/shop.duckdb"),
        min_length=1,
        json_schema_extra=layout(),
    )
    create: bool = Field(
        default=False,
        title=N_("Create the file if it is missing"),
        description=N_("Without this, a file that does not exist fails the connection check"),
        json_schema_extra=layout(),
    )

    @field_validator("path")
    @classmethod
    def _must_name_a_file_inside_the_home(cls, value: str) -> str:
        return below_home(value)

    @property
    def parts(self) -> tuple[str, ...]:
        return PurePosixPath(self.path).parts

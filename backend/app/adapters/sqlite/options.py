"""Which file of a person's storage a SQLite source is (D247).

A path below the owner's home and nothing else: the home is the server's to
compose, as it is for a file source (D8), so no field can name a place outside
it.
"""

from pathlib import PurePosixPath

from pydantic import BaseModel, Field, field_validator

from app.adapters.explorer.storage import stays_inside_root
from app.adapters.layout import layout
from app.core.translation import N_, say


class SqliteOptions(BaseModel):
    path: str = Field(
        title=N_("Database file"),
        description=N_("Path of the file inside your personal storage, such as data/shop.db"),
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
        """Stored as a path below the home with no leading slash: `data/shop.db`."""
        below_home = value.strip().strip("/")
        if below_home == "":
            raise ValueError(say("Name a file inside your personal storage"))
        if not stays_inside_root(below_home):
            raise ValueError(say("The path must stay inside your personal storage"))
        return below_home

    @property
    def parts(self) -> tuple[str, ...]:
        return PurePosixPath(self.path).parts

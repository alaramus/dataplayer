from pydantic import BaseModel, Field, field_validator

from app.adapters.file.session import stays_inside_root
from app.adapters.layout import layout


class FileOptions(BaseModel):
    # The only option there is. The root itself is never named by the client:
    # it comes from the owner of the connector, so this path is always read
    # relative to that person's own storage.
    path: str = Field(
        default="/",
        title="Path",
        description="Path inside your personal storage",
        json_schema_extra=layout(),
        # The default goes through the validator too, so a stored path has one
        # shape whatever the form sent.
        validate_default=True,
    )

    @field_validator("path")
    @classmethod
    def _must_stay_inside_the_home(cls, value: str) -> str:
        """Refuse what leaves the home, and store what stays in one form.

        A stored path begins at the root and says so: "/" is the root itself.
        It used to be the empty string, which is what a connection held
        whether the user typed "/" or left the box alone, and reads like a
        field nobody filled in.
        """
        below_home = value.strip().strip("/")
        if not stays_inside_root(below_home):
            raise ValueError("The path must stay inside your personal storage")
        return f"/{below_home}"

    @property
    def below_home(self) -> str:
        """The folder as a path is joined from it: without the leading slash.

        `Path.joinpath` reads a segment that starts with a separator as "begin
        again at the file system root", so joining the stored form would leave
        personal storage entirely.
        """
        return self.path[1:]

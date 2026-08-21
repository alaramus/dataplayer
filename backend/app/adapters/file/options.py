from pydantic import BaseModel, Field, field_validator

from app.adapters.file.session import stays_inside_root


class FileOptions(BaseModel):
    # The only option there is. The root itself is never named by the client:
    # it comes from the owner of the connector, so this path is always read
    # relative to that person's own storage.
    path: str = Field(
        default="/",
        title="Folder",
        description="Folder inside your personal storage",
        # The default goes through the validator too, so "/" becomes the
        # empty path that means "the home directory itself".
        validate_default=True,
    )

    @field_validator("path")
    @classmethod
    def _must_stay_inside_the_home(cls, value: str) -> str:
        relative = value.strip().strip("/")
        if relative and not stays_inside_root(relative):
            raise ValueError("The folder must stay inside your personal storage")
        return relative

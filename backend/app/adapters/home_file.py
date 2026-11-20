"""A database file of its owner's storage, for the sources that are one (D247, D387).

A path below the owner's home and nothing else: the home is the server's to
compose, as it is for a file source (D8), so no field can name a place outside
it. The path is judged by the file source's own rule on every open, symlinks
followed, so a link put in place of the file afterwards is caught as well.
"""

from pathlib import Path

from app.adapters.explorer.storage import stays_inside_root
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError
from app.core.translation import say


def below_home(value: str) -> str:
    """A path as it is stored: below the home with no leading slash, `data/shop.db`."""
    below = value.strip().strip("/")
    if below == "":
        raise ValueError(say("Name a file inside your personal storage"))
    if not stays_inside_root(below):
        raise ValueError(say("The path must stay inside your personal storage"))
    return below


class HomeFile:
    """One file of one person's storage, which may be made when it is missing."""

    def __init__(self, home_dir: Path, path: str, *, create: bool) -> None:
        self._storage = LocalStorage(home_dir)
        self._path = path
        self._create = create

    @property
    def home(self) -> Path:
        """The home with links followed: what containment is judged against."""
        return self._storage.resolved_root

    def path(self) -> Path:
        """Where the file is on this server's disk; it may not be there."""
        try:
            return self._storage.path_of(self._storage.place(self._path))
        except ValueError:
            raise AdapterError(
                "config", say("The path must stay inside your personal storage")
            ) from None

    def to_open(self) -> Path:
        """The file to open, refused unless it is there or may be made.

        A typo should not leave an empty database behind, so a missing file
        is made only where the person asked and only in a folder that exists.
        """
        path = self.path()
        if path.is_dir():
            raise AdapterError("config", say("The path names a folder, not a file"))
        if not path.exists():
            if not self._create:
                raise AdapterError("config", say("The database file does not exist"))
            if not path.parent.is_dir():
                raise AdapterError(
                    "config", say("The folder for the database file does not exist")
                )
        return path

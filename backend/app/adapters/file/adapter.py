"""A person's own storage on this server, as a source: the explorer over the
local disk (D150)."""

from pathlib import Path, PurePosixPath

from app.adapters.explorer.explorer import Explorer
from app.adapters.file.options import FileOptions
from app.adapters.file.storage import LocalStorage
from app.adapters.registry import AdapterContext, register


class FileAdapter(Explorer):
    """The explorer over one folder of a person's home.

    The root is composed here and nowhere else: the home directory decided by
    the server, plus the folder the user chose inside it.
    """

    def __init__(self, options: FileOptions, context: AdapterContext) -> None:
        root = context.home_dir.joinpath(*PurePosixPath(options.below_home).parts)
        self._local = LocalStorage(root, home_dir=context.home_dir)
        super().__init__(self._local)

    @property
    def root(self) -> Path:
        return self._local.root


@register(
    name="file",
    title="Files",
    category="files",
    description=(
        "Your personal storage on this server. Browse folders and open files "
        "through representations appropriate to their content."
    ),
    options_schema=FileOptions,
    adapter_class=FileAdapter,
)
def _build(options: FileOptions, context: AdapterContext) -> FileAdapter:
    return FileAdapter(options, context)

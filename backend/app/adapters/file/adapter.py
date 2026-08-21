from pathlib import Path, PurePosixPath

from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file.catalog import FileCatalog
from app.adapters.file.fetch import FileFetch
from app.adapters.file.options import FileOptions
from app.adapters.file.session import FileSession
from app.adapters.protocol import ConnectionCheckResult
from app.adapters.registry import AdapterContext, register


class FileAdapter:
    """Facade over a root and the capabilities built on it.

    The root is composed here and nowhere else: the home directory decided by
    the server, plus the folder the user chose inside it.
    """

    def __init__(self, options: FileOptions, context: AdapterContext) -> None:
        root = context.home_dir.joinpath(*PurePosixPath(options.path).parts)
        self._session = FileSession(root)
        self._catalog = FileCatalog(self._session)
        self._fetch = FileFetch(self._session)

    @property
    def root(self) -> Path:
        return self._session.root

    async def check_connection(self) -> ConnectionCheckResult:
        return await self._session.check()

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return await self._catalog.list_children(node_id)

    async def fetch(self, request: FetchRequest) -> FetchResult:
        return await self._fetch.fetch(request)


@register(name="file", title="Files", options_schema=FileOptions)
def _build(options: FileOptions, context: AdapterContext) -> FileAdapter:
    return FileAdapter(options, context)

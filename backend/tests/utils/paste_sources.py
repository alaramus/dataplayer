"""Sources the paste kinds can be exercised against without a server (D164)."""

from collections.abc import AsyncIterator

from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.relation import Column, ColumnType, RelationModel
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
)
from app.adapters.update import (
    InsertRowRequest,
    InsertRowResult,
    InsertRowsRequest,
    InsertRowsResult,
)

ROWS: list[list[str | None]] = [["1", "Ada"], ["2", None], ["3", 'Grace "G"']]
PETS: list[list[str | None]] = [["1", "cat"]]

# Each relation's columns and rows. `sales.people` shares its name with
# `public.people`, so two of them saved together want the same file.
RELATIONS: dict[str, tuple[list[str], list[list[str | None]]]] = {
    "public.people": (["id", "name"], ROWS),
    "public.pets": (["id", "species"], PETS),
    "sales.people": (["id", "name"], ROWS),
}


class Table:
    """A source holding a few relations, `public.people` first, read in batches of two."""

    def __init__(
        self, *, fail_at_batch: int | None = None, failing: str | None = None
    ) -> None:
        self.fail_at_batch = fail_at_batch
        # The one relation whose stream fails, when the others must not.
        self.failing = failing
        self.closed = False

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")

    async def relation_model(self, node_id: str) -> RelationModel:
        if "." not in node_id:
            raise ValueError(f'"{node_id}" is not a relation')
        if node_id not in RELATIONS:
            raise NodeNotFound(node_id)
        schema, _, name = node_id.partition(".")
        return RelationModel(
            node_id=node_id,
            schema_name=schema,
            name=name,
            kind="table",
            columns=[
                Column(
                    position=position,
                    name=column,
                    type=ColumnType(sql="text", category="string"),
                    nullable=True,
                )
                for position, column in enumerate(RELATIONS[node_id][0], start=1)
            ],
        )

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        columns, rows = RELATIONS[request.node_id]
        assert request.columns == columns
        failing = self.failing in (None, request.node_id)
        try:
            for number, start in enumerate(range(0, len(rows), 2)):
                if failing and number == self.fail_at_batch:
                    raise AdapterError("network", "The source went away")
                yield ExportBatch(rows=rows[start : start + 2])
        finally:
            self.closed = True


class Explorer:
    """What the file kinds see of an explorer connection: its storage."""

    def __init__(self, storage: LocalStorage) -> None:
        self.storage = storage

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")


class Database:
    """A source that reads, inserts and creates relations, as far as the
    registry can tell; nothing here is ever called."""

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raise NotImplementedError

    async def insert_row(self, request: InsertRowRequest) -> InsertRowResult:
        raise NotImplementedError

    async def insert_rows(self, request: InsertRowsRequest) -> InsertRowsResult:
        raise NotImplementedError

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        raise NotImplementedError

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        raise NotImplementedError

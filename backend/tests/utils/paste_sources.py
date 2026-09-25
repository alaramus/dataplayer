"""Sources the paste kinds can be exercised against without a server (D164)."""

from collections.abc import AsyncIterator

from app.adapters.export import ExportBatch, ExportRequest
from app.adapters.file.storage import LocalStorage
from app.adapters.protocol import AdapterError, ConnectionCheckResult, NodeNotFound
from app.adapters.relation import Column, ColumnType, RelationModel

ROWS: list[list[str | None]] = [["1", "Ada"], ["2", None], ["3", 'Grace "G"']]


class Table:
    """A source holding one relation, `public.people`, read in batches of two."""

    def __init__(self, *, fail_at_batch: int | None = None) -> None:
        self.fail_at_batch = fail_at_batch
        self.closed = False

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")

    async def relation_model(self, node_id: str) -> RelationModel:
        if "." not in node_id:
            raise ValueError(f'"{node_id}" is not a relation')
        if node_id != "public.people":
            raise NodeNotFound(node_id)
        return RelationModel(
            node_id=node_id,
            schema_name="public",
            name="people",
            kind="table",
            columns=[
                Column(
                    position=position,
                    name=name,
                    type=ColumnType(sql="text", category="string"),
                    nullable=True,
                )
                for position, name in enumerate(["id", "name"], start=1)
            ],
        )

    def export_rows(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        return self._stream(request)

    async def _stream(self, request: ExportRequest) -> AsyncIterator[ExportBatch]:
        assert request.columns == ["id", "name"]
        try:
            for number, start in enumerate(range(0, len(ROWS), 2)):
                if number == self.fail_at_batch:
                    raise AdapterError("network", "The source went away")
                yield ExportBatch(rows=ROWS[start : start + 2])
        finally:
            self.closed = True


class Explorer:
    """What the file kinds see of an explorer connection: its storage."""

    def __init__(self, storage: LocalStorage) -> None:
        self.storage = storage

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="")

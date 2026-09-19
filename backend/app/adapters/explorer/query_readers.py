"""File relations for SQL, including the bounded log projection (D96)."""

import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Literal

import duckdb
import pyarrow as pa

from app.adapters.explorer.binary import bytes_look_binary
from app.adapters.explorer.formats import FileFormat, format_of
from app.adapters.explorer.readers import LogReader
from app.adapters.protocol import AdapterError

# Arrow input lives outside DuckDB's memory limit. These ceilings apply across
# all logs in one run, before result limits have anything to count.
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_LOG_ROWS = 100_000
MAX_LOG_CELLS = 500_000
MAX_LOG_CELL_BYTES = 4 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


class PreparationStopped(Exception):
    def __init__(self, status: Literal["cancelled", "timed_out"]) -> None:
        self.status = status
        super().__init__(status)


class Preparation:
    """Cancellation and a deadline while Python prepares the engine's input."""

    def __init__(self, deadline: float, interrupted: Event | None = None) -> None:
        self._deadline = deadline
        self._interrupted = interrupted

    def check(self) -> None:
        if self._interrupted is not None and self._interrupted.is_set():
            raise PreparationStopped("cancelled")
        if time.monotonic() >= self._deadline:
            raise PreparationStopped("timed_out")


class FileReaders:
    """One set of readers and one log input budget per engine."""

    def __init__(
        self, connection: duckdb.DuckDBPyConnection, checkpoint: Callable[[], None]
    ) -> None:
        self._connection = connection
        self._checkpoint = checkpoint
        self._bytes = 0
        self._rows = 0
        self._cells = 0

    def read(self, path: Path) -> duckdb.DuckDBPyRelation:
        # Resolved paths are driver arguments, never text inserted into SQL.
        self._checkpoint()
        relation = _READERS[format_of(path.name)](self, path)
        self._checkpoint()
        return relation

    def _csv(self, path: Path) -> duckdb.DuckDBPyRelation:
        return self._connection.read_csv(str(path))

    def _parquet(self, path: Path) -> duckdb.DuckDBPyRelation:
        return self._connection.read_parquet(str(path))

    def _json(self, path: Path) -> duckdb.DuckDBPyRelation:
        return self._connection.read_json(str(path))

    def _log(self, path: Path) -> duckdb.DuckDBPyRelation:
        data = self._snapshot(path)
        if bytes_look_binary(data):
            raise AdapterError("config", "This log contains binary data")
        try:
            page = LogReader().read_snapshot(
                data,
                MAX_LOG_ROWS - self._rows,
                max_cells=MAX_LOG_CELLS - self._cells,
                checkpoint=self._checkpoint,
            )
        except ValueError as exc:
            # These are the projection's own safe refusals, never driver text.
            raise AdapterError("config", str(exc)) from None
        if page.has_more:
            raise AdapterError("config", "The logs exceed the SQL input row limit")
        self._rows += len(page.rows)
        self._cells += len(page.rows) * len(page.columns)
        if self._cells > MAX_LOG_CELLS:
            raise AdapterError("config", "The logs exceed the SQL input cell limit")
        if not page.columns:
            raise AdapterError("config", "This log has no columns SQL can read")
        try:
            for column in page.columns:
                column.name.encode("utf-8")
            for row in page.rows:
                self._checkpoint()
                if any(
                    cell is not None and len(cell.encode("utf-8")) > MAX_LOG_CELL_BYTES
                    for cell in row
                ):
                    raise AdapterError(
                        "config", "A log value exceeds the SQL input cell size limit"
                    )
        except UnicodeEncodeError:
            raise AdapterError(
                "config", "This log contains text that cannot be represented in UTF-8"
            ) from None

        arrays = []
        for index in range(len(page.columns)):
            self._checkpoint()
            arrays.append(pa.array([row[index] for row in page.rows], type=pa.string()))
        table = pa.Table.from_arrays(
            arrays, names=[column.name for column in page.columns]
        )
        return self._connection.from_arrow(table)

    def _snapshot(self, path: Path) -> bytes:
        """Read to EOF or refuse: a growing file cannot evade a stat check."""
        data = bytearray()
        try:
            with path.open("rb") as handle:
                while True:
                    self._checkpoint()
                    chunk = handle.read(
                        min(READ_CHUNK_BYTES, MAX_LOG_BYTES - self._bytes + 1)
                    )
                    self._bytes += len(chunk)
                    if self._bytes > MAX_LOG_BYTES:
                        raise AdapterError(
                            "config", "The logs exceed the SQL input byte limit"
                        )
                    if not chunk:
                        break
                    data.extend(chunk)
        except OSError:
            raise AdapterError("config", "This log could not be read") from None
        return bytes(data)


_READERS: dict[FileFormat, Callable[[FileReaders, Path], duckdb.DuckDBPyRelation]] = {
    "delimited": FileReaders._csv,
    "parquet": FileReaders._parquet,
    "json": FileReaders._json,
    "jsonl": FileReaders._json,
    "log": FileReaders._log,
}
QUERY_FORMATS = frozenset(_READERS)

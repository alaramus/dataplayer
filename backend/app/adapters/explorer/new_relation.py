"""Creating a relation where the source keeps files: one delimited file.

A folder has no CREATE TABLE and needs none. Rows under named columns are a
delimited file, so the command that makes a table in a database writes one
here (D45) and the screen that asks is the same screen: a folder answers the
question a schema answers, and the type vocabulary has a single entry because
every value in such a file is text.

The write is atomic for the reason the database half is transactional. The
file is built beside its destination and linked into place under a name
nothing else holds, so a failure leaves nothing half-written behind and a name
already taken is refused rather than replaced.
"""

import csv

from anyio import to_thread

from app.adapters.delimited import delimiter_of
from app.adapters.explorer.catalog import node_of
from app.adapters.explorer.formats import format_of
from app.adapters.explorer.storage import Place, Storage, is_plain_name
from app.adapters.protocol import AdapterError, NodeNotFound
from app.adapters.relation import ColumnTypeOption
from app.adapters.relation_changes import (
    CreateRelationRequest,
    CreateRelationResult,
    NewRelationOptions,
    RelationCreated,
)

# One entry, and it is not a choice: a delimited file states no types and every
# value read out of one comes back as text (D45). Published all the same,
# because the screen asks the container what it accepts rather than knowing.
TEXT_COLUMN = ColumnTypeOption(code="text", title="Text", sql="text")

# What a name with no delimited extension of its own is given. A file that is
# not named as one would be written as a table and read back as a document.
DEFAULT_SUFFIX = ".csv"


class ExplorerNewRelations:
    """The `create-relation` capability of a tree of files."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def new_relation_options(self, parent_node_id: str) -> NewRelationOptions:
        return await to_thread.run_sync(self._options, parent_node_id)

    async def create_relation(
        self, request: CreateRelationRequest
    ) -> CreateRelationResult:
        return await to_thread.run_sync(self._create, request)

    def _options(self, parent_node_id: str) -> NewRelationOptions:
        # Containment first, as every read of this source judges it (D8). The
        # root itself is a folder and is named by the empty id, which is what
        # a connector with no folders in it offers.
        found = self._storage.entry(self._storage.place(parent_node_id))
        if found is None:
            raise NodeNotFound(parent_node_id)
        if not found.is_directory:
            return NewRelationOptions(
                supported=False, reason="A table is written into a folder"
            )
        return NewRelationOptions(supported=True, column_type_options=[TEXT_COLUMN])

    def _create(self, request: CreateRelationRequest) -> CreateRelationResult:
        options = self._options(request.parent_node_id)
        if not options.supported:
            raise ValueError(options.reason or "This node cannot hold a relation")
        for column in request.columns:
            if column.type_code != TEXT_COLUMN.code:
                raise ValueError(f'Unknown column type "{column.type_code}"')

        name = filename_for(request.name)
        target = self._storage.child(self._storage.place(request.parent_node_id), name)
        if self._storage.entry(target) is not None:
            raise ValueError(f"{name} is already there")

        self._write(
            target,
            header=[column.name for column in request.columns],
            rows=request.rows,
        )
        written = self._storage.entry(target)
        if written is None:  # pragma: no cover - the file was just written here
            raise AdapterError("unknown", "The new file could not be described")
        return RelationCreated(
            node=node_of(self._storage, written), inserted=len(request.rows)
        )

    def _write(
        self,
        target: Place,
        header: list[str],
        rows: list[list[str | None]],
    ) -> None:
        """Build the file beside its destination and claim the name with it.

        Publishing claims the name rather than checking it: a second request
        between the check above and this line fails here instead of replacing
        what it wrote.
        """
        delimiter = delimiter_of(target.name, "")
        with self._storage.staged(target, prefix=".csv-new-") as staged:
            with staged.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
                writer.writerow(header)
                writer.writerows(rows)
            try:
                self._storage.publish(staged, target)
            except FileExistsError:
                raise ValueError(f"{target.name} is already there") from None


def filename_for(name: str) -> str:
    """The file a relation of this name is written to.

    The one name rule of this source, then an extension when the name carries
    none that would be read back as a table: a reader who typed "orders" asked
    for a table, and `orders` alone opens as a document.
    """
    plain = name.strip()
    if not is_plain_name(plain):
        raise ValueError("A name must be a single plain name, without separators")
    if format_of(plain) == "delimited":
        return plain
    return f"{plain}{DEFAULT_SUFFIX}"

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
import os
import tempfile
from pathlib import Path

from anyio import to_thread

from app.adapters.delimited import delimiter_of
from app.adapters.file.catalog import node_of
from app.adapters.file.formats import format_of
from app.adapters.file.session import FileSession, is_plain_name
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


class FileNewRelations:
    """The `create-relation` capability of the file source."""

    def __init__(self, session: FileSession) -> None:
        self._session = session

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
        path = self._session.resolve(parent_node_id)
        if not path.exists():
            raise NodeNotFound(parent_node_id)
        if not path.is_dir():
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

        parent = self._session.resolve(request.parent_node_id)
        name = filename_for(request.name)
        target = parent / name
        if target.exists():
            raise ValueError(f"{name} is already there")

        written = _write(
            parent=parent,
            name=name,
            header=[column.name for column in request.columns],
            rows=request.rows,
        )
        node = node_of(self._session, written, written.name, written.stat(), False)
        if node is None:  # pragma: no cover - the file was just written here
            raise AdapterError("unknown", "The new file could not be described")
        return RelationCreated(node=node, inserted=len(request.rows))


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


def _write(
    parent: Path, name: str, header: list[str], rows: list[list[str | None]]
) -> Path:
    """Build the file beside its destination and link it into place.

    `os.link` is what makes the name a claim rather than a check: a second
    request between the check above and this line fails here instead of
    replacing what it wrote.
    """
    delimiter = delimiter_of(name, "")
    descriptor, temporary = tempfile.mkstemp(dir=parent, prefix=".csv-new-")
    draft = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
        target = parent / name
        try:
            os.link(draft, target)
        except FileExistsError:
            raise ValueError(f"{name} is already there") from None
        return target
    finally:
        draft.unlink(missing_ok=True)

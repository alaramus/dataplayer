"""A source whose rows are documents, read and changed as documents (D295).

The grid reads a collection as rows (D284); this reads the same documents
whole — each as a tree to look at and as the text of it to edit — under the
same filters, order and paging, and changes one by the fields that differ.
A change names the document by the handle a page gave it (D287), so a
document changed in between is a conflict here as it is in the grid.
"""

from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.content import JsonValue
from app.adapters.fetch import FetchRequest

# The longest text of one document a change may carry.
MAX_DOCUMENT_TEXT = 1024 * 1024


class DocumentsRequest(FetchRequest):
    """A page of documents, as `FetchRequest` names a page of rows."""


class DocumentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None where the document has no `_id` to be named by: a view's.
    row_handle: str | None = None
    # The document as editable text, in the source's own notation.
    text: str
    # The same document as a tree; None when it was too large to draw.
    value: JsonValue | None = None
    # The text is only the beginning of the document, which cannot be edited.
    truncated: bool = False


class DocumentsPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentItem]
    has_more: bool
    offset: int = Field(ge=0)
    change_supported: bool = False
    change_reason: str | None = None


class FieldChange(BaseModel):
    """One field of a document set to a value, or removed.

    A path rather than a dotted name: a key may hold a dot, and only the
    source knows whether such a key can be addressed.
    """

    model_config = ConfigDict(extra="forbid")

    path: Annotated[list[str], Field(min_length=1, max_length=32)]
    op: Literal["set", "unset"]
    # The value in the source's notation; absent for `unset`.
    value: str | None = None


class DocumentText(BaseModel):
    """The whole document as edited; the source changes the fields that differ."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["document"] = "document"
    text: str = Field(min_length=1, max_length=MAX_DOCUMENT_TEXT)


class FieldChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["fields"] = "fields"
    changes: Annotated[list[FieldChange], Field(min_length=1, max_length=200)]


DocumentChange = Annotated[DocumentText | FieldChanges, Field(discriminator="kind")]


class DocumentChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    row_handle: str
    change: DocumentChange


class DocumentChanged(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # How many fields were set or removed; none when nothing differed.
    changed: int = Field(ge=0)
    item: DocumentItem


@runtime_checkable
class SupportsDocuments(Protocol):
    async def read_documents(self, request: DocumentsRequest) -> DocumentsPage:
        """A page of whole documents. Raises what `fetch` raises."""
        ...

    async def change_document(self, request: DocumentChangeRequest) -> DocumentChanged:
        """Change the fields that differ, if the document is still the one read.

        Raises `RowConflict` when it is not, `ValueError` for text or a change
        the source cannot take, `AdapterError` for the source's failures.
        """
        ...

"""Query documents: the library, one console, and Trash.

D63: a document belongs to one user and is bound to one connection. Creating
one asks for `read` on that connection, because a console is a way of looking
at a source. Reading and editing an existing one does not: a document survives
losing its context, and only running it — which does not exist yet — needs the
source at all.

Nothing here publishes a query capability. There is no execution in this
module, by design: the early slices are deliberately hidden so the shapes and
the state machine can be proved without offering a primitive product.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors import crud as connector_crud
from app.connectors.access import get_or_404
from app.core.db import SessionDep
from app.core.schemas import Message
from app.queries import crud
from app.queries.content import body_of, encrypted, preview_of
from app.queries.models import (
    EditorLayout,
    QueryDocument,
    QueryDocumentCreate,
    QueryDocumentPublic,
    QueryDocumentsPublic,
    QueryDocumentSummary,
    QueryDocumentUpdate,
)
from app.users.deps import CurrentUser
from app.users.models import User

router = APIRouter(prefix="/queries", tags=["queries"])

MAX_PAGE = 200


def _title_of(raw: str | None) -> str | None:
    """A name, or nothing at all.

    Spaces are not a name: a document titled with them would sort and search
    as though it had one while looking exactly like a draft.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _layout_of(document: QueryDocument) -> EditorLayout:
    """The stored layout, or the default when an older shape is in the column.

    Unlike a share body there is nothing here to refuse: a split ratio is not
    the document, so a geometry this version no longer accepts falls back to
    where a new editor opens rather than making the text unreadable.
    """
    try:
        return EditorLayout.model_validate(document.layout)
    except ValueError:
        return EditorLayout()


def _public(
    document: QueryDocument, *, connector_label: str | None
) -> QueryDocumentPublic:
    return QueryDocumentPublic(
        id=document.id,
        connector_id=document.connector_id,
        connector_label=connector_label,
        title=document.title,
        body=body_of(document),
        revision=document.revision,
        search_path=list(document.search_path),
        layout=_layout_of(document),
        created_at=document.created_at,
        updated_at=document.updated_at,
        trashed_at=document.trashed_at,
    )


def _summary(
    document: QueryDocument, *, connector_label: str | None
) -> QueryDocumentSummary:
    return QueryDocumentSummary(
        id=document.id,
        connector_id=document.connector_id,
        connector_label=connector_label,
        title=document.title,
        preview=preview_of(body_of(document)),
        revision=document.revision,
        created_at=document.created_at,
        updated_at=document.updated_at,
        trashed_at=document.trashed_at,
    )


async def _label_of(
    session: AsyncSession, document: QueryDocument, user: User
) -> str | None:
    if document.connector_id is None:
        return None
    names = await connector_crud.visible_names(
        session, user=user, connector_ids=[document.connector_id]
    )
    return names.get(document.connector_id)


async def _owned_or_404(
    session: AsyncSession, document_id: uuid.UUID, user: User
) -> QueryDocument:
    document = await crud.get_owned(session, document_id=document_id, owner=user)
    if document is None:
        raise HTTPException(status_code=404, detail="Query document not found")
    return document


@router.get("/documents", response_model=QueryDocumentsPublic)
async def list_documents(
    session: SessionDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID | None = None,
    search: str = Query(default="", max_length=200),
    trashed: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE),
) -> QueryDocumentsPublic:
    """This user's documents, newest first, or what is waiting in Trash."""
    documents, count = await crud.list_for(
        session,
        owner=current_user,
        connector_id=connector_id,
        search=search.strip(),
        trashed=trashed,
        skip=skip,
        limit=limit,
    )
    names = await connector_crud.visible_names(
        session,
        user=current_user,
        connector_ids={
            document.connector_id
            for document in documents
            if document.connector_id is not None
        },
    )
    return QueryDocumentsPublic(
        data=[
            _summary(
                document,
                connector_label=(
                    None
                    if document.connector_id is None
                    else names.get(document.connector_id)
                ),
            )
            for document in documents
        ],
        count=count,
    )


@router.post("/documents", response_model=QueryDocumentPublic)
async def create_document(
    session: SessionDep, current_user: CurrentUser, body: QueryDocumentCreate
) -> QueryDocumentPublic:
    """Open a new console, or keep a copy of one that could not be saved.

    `read` on the connection and no more: writing SQL into a document is not
    running it, and what running needs is decided where there is a Run.
    """
    connector = await get_or_404(
        session, body.connector_id, current_user, requires="read"
    )
    document = await crud.create(
        session,
        owner=current_user,
        connector_id=connector.id,
        title=_title_of(body.title),
        body=body.body,
        search_path=body.search_path,
        layout=body.layout,
    )
    return _public(document, connector_label=connector.name)


@router.get("/documents/{document_id}", response_model=QueryDocumentPublic)
async def read_document(
    session: SessionDep, current_user: CurrentUser, document_id: uuid.UUID
) -> QueryDocumentPublic:
    document = await _owned_or_404(session, document_id, current_user)
    return _public(
        document, connector_label=await _label_of(session, document, current_user)
    )


@router.patch("/documents/{document_id}", response_model=QueryDocumentPublic)
async def update_document(
    session: SessionDep,
    current_user: CurrentUser,
    document_id: uuid.UUID,
    body: QueryDocumentUpdate,
) -> QueryDocumentPublic:
    """One autosave, or one deliberate change of name or context.

    The revision the caller started from must be the one in the database. When
    it is not, the answer is 409 and nothing is written: the client reads the
    document again and offers keeping its own text, taking the remote one, or
    saving its own as a copy. Choosing is a person's job, and picking the last
    writer in silence is what makes work disappear (D63).

    Only what was sent changes, and absent is not null: a title sent as null
    takes the name off the document and makes it a draft again.
    """
    document = await _owned_or_404(session, document_id, current_user)
    if document.trashed_at is not None:
        raise HTTPException(
            status_code=409, detail="This document is in Trash; restore it first"
        )
    if body.revision != document.revision:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This document changed elsewhere",
                "revision": document.revision,
            },
        )
    if "title" in body.model_fields_set:
        document.title = _title_of(body.title)
    if body.body is not None:
        document.body = encrypted(body.body)
    if body.search_path is not None:
        document.search_path = list(body.search_path)
    if body.layout is not None:
        document.layout = body.layout.model_dump()
    document.revision += 1
    saved = await crud.save(session, document=document)
    return _public(saved, connector_label=await _label_of(session, saved, current_user))


@router.delete("/documents/{document_id}", response_model=Message)
async def trash_document(
    session: SessionDep, current_user: CurrentUser, document_id: uuid.UUID
) -> Message:
    """Move a document to Trash, where it waits its retention out (D63)."""
    document = await _owned_or_404(session, document_id, current_user)
    if document.trashed_at is None:
        await crud.trash(session, document=document)
    return Message(message="Document moved to Trash")


@router.post("/documents/{document_id}/restore", response_model=QueryDocumentPublic)
async def restore_document(
    session: SessionDep, current_user: CurrentUser, document_id: uuid.UUID
) -> QueryDocumentPublic:
    document = await _owned_or_404(session, document_id, current_user)
    restored = await crud.restore(session, document=document)
    return _public(
        restored, connector_label=await _label_of(session, restored, current_user)
    )


@router.delete("/documents/{document_id}/purge", response_model=Message)
async def purge_document(
    session: SessionDep, current_user: CurrentUser, document_id: uuid.UUID
) -> Message:
    """Delete a document for good, before its retention runs out.

    Only from Trash: the deliberate second step is what makes the first one
    safe to press.
    """
    document = await _owned_or_404(session, document_id, current_user)
    if document.trashed_at is None:
        raise HTTPException(
            status_code=409, detail="Move this document to Trash before deleting it"
        )
    await crud.purge(session, document=document)
    return Message(message="Document deleted")

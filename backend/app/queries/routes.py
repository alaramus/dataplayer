"""Query documents, and the runs made from them.

D63: a document belongs to one user and is bound to one connection. Creating
one asks for `read` on that connection, because a console is a way of looking
at a source; reading and editing an existing one asks for nothing, because a
document survives losing its context. Running it needs the source, and asks
for the level the statements need.

The read kernel is here without a console to drive it: the editor gains Run in
a later slice, so these shapes and this state machine are proved before
anything is offered to a user (D62).
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.query import QueryProfile, QueryRequest, SupportsQuery
from app.adapters.resources import ResourcesDep, ResourceStore
from app.connectors import crud as connector_crud
from app.connectors.access import adapter_for, get_or_404
from app.core.config import settings
from app.core.db import SessionDep
from app.core.schemas import Message
from app.queries import crud, execution
from app.queries.content import body_of, encrypted, preview_of
from app.queries.execution import RunnerDep, RunRefused
from app.queries.models import (
    EditorLayout,
    QueryDocument,
    QueryDocumentCreate,
    QueryDocumentPublic,
    QueryDocumentsPublic,
    QueryDocumentSummary,
    QueryDocumentUpdate,
)
from app.queries.results import ResultsDep
from app.queries.runs import (
    TERMINAL,
    ExecutionRun,
    ResultPage,
    RunPublic,
    RunStart,
    StatementPublic,
    StatementRun,
)
from app.realtime.topics import TopicsDep
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


# --- runs -------------------------------------------------------------------
#
# D64: starting a run validates and records, then answers. What runs is a task,
# what says how it is going is the socket, and what settles it is the route
# below — which is the authority and the fallback when a message is missed.


async def _source_or_501(
    session: AsyncSession,
    connector_id: uuid.UUID,
    user: User,
    resources: ResourceStore,
) -> SupportsQuery:
    """A source that accepts complete SQL, or the reason it does not.

    `read` and no more: this slice runs reads, and the level a script needs is
    the highest level any of its statements needs (D62).
    """
    adapter = await adapter_for(session, connector_id, user, resources, requires="read")
    if not isinstance(adapter, SupportsQuery):
        raise HTTPException(
            status_code=501,
            detail={
                "message": "This source does not run queries",
                "capability": "query",
            },
        )
    return adapter


def _statements_public(rows: list[StatementRun]) -> list[StatementPublic]:
    return [
        StatementPublic.model_validate(
            {
                **row.model_dump(exclude={"run_id"}),
                "notices": row.notices,
            }
        )
        for row in sorted(rows, key=lambda row: row.ordinal)
    ]


async def _run_public(session: AsyncSession, run: ExecutionRun) -> RunPublic:
    rows = (
        await session.exec(
            select(StatementRun).where(StatementRun.run_id == run.id)
        )
    ).all()
    return RunPublic.model_validate(
        {**run.model_dump(), "statements": _statements_public(list(rows))}
    )


async def _owned_run_or_404(
    session: AsyncSession, run_id: uuid.UUID, user: User
) -> ExecutionRun:
    run = await session.get(ExecutionRun, run_id)
    if run is None or run.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/connectors/{connector_id}/profile", response_model=QueryProfile)
async def read_profile(
    session: SessionDep,
    resources: ResourcesDep,
    current_user: CurrentUser,
    connector_id: uuid.UUID,
) -> QueryProfile:
    """What this source accepts as a complete statement, in its own words."""
    source = await _source_or_501(session, connector_id, current_user, resources)
    return source.query_profile()


@router.post("/runs", response_model=RunPublic)
async def start_run(
    session: SessionDep,
    resources: ResourcesDep,
    topics: TopicsDep,
    runner: RunnerDep,
    current_user: CurrentUser,
    body: RunStart,
) -> RunPublic:
    """Accept a run, record it, and start carrying it out.

    Idempotent by the id the client chose: the same command twice is one run,
    and the same id with a different command is a conflict rather than a second
    execution nobody asked for (D64).
    """
    existing = await session.get(ExecutionRun, body.run_id)
    if existing is not None:
        if (
            existing.owner_id != current_user.id
            or existing.fingerprint != execution.fingerprint(body)
        ):
            raise HTTPException(
                status_code=409,
                detail="This run id was already used for a different run",
            )
        return await _run_public(session, existing)

    source = await _source_or_501(session, body.connector_id, current_user, resources)
    profile = source.query_profile()
    if body.mode not in profile.statement_modes:
        raise HTTPException(
            status_code=422, detail=f"This source does not run in {body.mode} mode"
        )
    timeout = min(
        body.timeout_seconds or profile.default_timeout_seconds,
        profile.max_timeout_seconds,
    )
    bounds = execution.limits(statement_timeout_seconds=timeout)

    document: QueryDocument | None = None
    if body.document_id is not None:
        document = await _owned_or_404(session, body.document_id, current_user)
        # One document, one run at a time. Another document is the explicit way
        # to run two things at once (D64).
        if await runner.is_running_document(document.id):
            raise HTTPException(
                status_code=409, detail="This document is already running something"
            )

    try:
        statements = execution.admit(source.prepare_query(body.text), bounds)
    except RunRefused as refusal:
        raise HTTPException(
            status_code=refusal.status_code, detail=refusal.message
        ) from None

    # Refused rather than queued where nobody can see it (D64).
    if await runner.active_count(current_user.id) >= settings.QUERY_MAX_ACTIVE_RUNS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You already have {settings.QUERY_MAX_ACTIVE_RUNS} runs going; "
                "wait for one to finish or cancel it"
            ),
        )

    search_path = list(document.search_path) if document is not None else []
    run = await execution.record(
        session,
        owner_id=current_user.id,
        body=body,
        statements=statements,
        timeout_seconds=timeout,
        search_path=search_path,
    )
    await runner.launch(
        run_id=run.id,
        owner_id=current_user.id,
        document_id=body.document_id,
        source=source,
        request=QueryRequest(
            text=body.text,
            mode=body.mode,
            search_path=search_path,
            limits=bounds,
        ),
        topics=topics,
    )
    return await _run_public(session, run)


@router.get("/runs/{run_id}", response_model=RunPublic)
async def read_run(
    session: SessionDep, current_user: CurrentUser, run_id: uuid.UUID
) -> RunPublic:
    """What this run is doing, or did. The authority, and the fallback."""
    run = await _owned_run_or_404(session, run_id, current_user)
    # Written by the task on its own session, so this one must not answer from
    # what it read before the task committed.
    await session.refresh(run)
    return await _run_public(session, run)


@router.post("/runs/{run_id}/cancel", response_model=RunPublic)
async def cancel_run(
    session: SessionDep, runner: RunnerDep, current_user: CurrentUser, run_id: uuid.UUID
) -> RunPublic:
    """Ask a run to stop.

    Idempotent, and not optimistic: the run moves to `cancelling` and stays
    there until the source says what actually happened. A query that won the
    race honestly finishes as a success (D64).
    """
    run = await _owned_run_or_404(session, run_id, current_user)
    if run.status in TERMINAL:
        return await _run_public(session, run)
    if run.status != "cancelling":
        run.status = "cancelling"
        session.add(run)
        await session.commit()
        await session.refresh(run)
    await runner.cancel(run_id)
    return await _run_public(session, run)


@router.get("/results/{result_id}", response_model=ResultPage)
async def read_result(
    results: ResultsDep,
    current_user: CurrentUser,
    result_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(
        default=settings.QUERY_PAGE_DEFAULT_ROWS,
        ge=1,
        le=settings.QUERY_PAGE_MAX_ROWS,
    ),
) -> ResultPage:
    """A page of a captured result.

    Of the snapshot, never of the source: these rows were read once, inside the
    transaction that produced them. A result that has expired is gone, and the
    run that produced it — which is durable — still says what happened (D64).
    """
    result = await results.get(result_id, owner_id=current_user.id)
    if result is None:
        raise HTTPException(
            status_code=404, detail="This result is no longer available"
        )
    return ResultPage(
        result_id=result_id,
        columns=result.columns,
        rows=result.rows[offset : offset + limit],
        offset=offset,
        limit=limit,
        total_rows=len(result.rows),
        truncated=result.truncated,
    )

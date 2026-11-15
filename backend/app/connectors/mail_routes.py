"""A mailbox's routes, under `/connectors/{id}/mail` (D366).

Apart from the connector routes because nothing there is shared with mail but
resolving the adapter. Every route requires `own`: a grantee of a shared
connection reads with the owner's credentials, and for a mailbox that would be
reading somebody's letters (D367).
"""

import json
import uuid
from collections.abc import Awaitable
from typing import Annotated

from anyio import to_thread
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ValidationError
from starlette.responses import Response

from app.adapters.actions import StorageFull
from app.adapters.mailbox import (
    MAX_OUTGOING_BYTES,
    DraftSaved,
    MailboxRefused,
    MailFolder,
    MailMessage,
    MarkRequest,
    MessagePage,
    MessageQuery,
    MessageRef,
    MessagesDeleted,
    MessageSelection,
    MessageSent,
    MessagesMoved,
    MoveRequest,
    OutgoingFile,
    OutgoingMessage,
    SupportsMailbox,
)
from app.adapters.protocol import AdapterError
from app.adapters.resources import ResourcesDep
from app.connectors import content_tickets, mail_files
from app.connectors.access import adapter_for, get_or_404
from app.core.db import SessionDep
from app.core.problems import Problem
from app.core.translation import say
from app.users import quota, storage
from app.users.deps import CurrentUser

router = APIRouter(prefix="/connectors", tags=["mail"])


class AttachmentRequest(MessageRef):
    part: str


class AttachmentKept(BaseModel):
    # Where in the person's storage, as the file explorer names it.
    path: str


async def _mailbox(
    session: SessionDep, current_user: CurrentUser, resources: ResourcesDep, connector_id: uuid.UUID
) -> SupportsMailbox:
    adapter = await adapter_for(session, connector_id, current_user, resources, requires="own")
    if not isinstance(adapter, SupportsMailbox):
        raise Problem(501, "mail.not_a_mailbox", error_kind="config")
    return adapter


async def _answered[T](call: Awaitable[T]) -> T:
    """The mailbox's answer, its refusals and failures as statuses."""
    try:
        return await call
    except MailboxRefused as refused:
        raise HTTPException(status_code=refused.status, detail={"message": refused.message}) from None
    except AdapterError as failure:
        raise HTTPException(
            status_code=502, detail={"message": failure.message, "error_kind": failure.error_kind}
        ) from None


@router.get("/{connector_id}/mail/folders", response_model=list[MailFolder])
async def mail_folders(
    session: SessionDep, current_user: CurrentUser, resources: ResourcesDep, connector_id: uuid.UUID
) -> list[MailFolder]:
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    return await _answered(mailbox.mail_folders())


@router.get("/{connector_id}/mail/messages", response_model=MessagePage)
async def mail_messages(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    query: Annotated[MessageQuery, Query()],
) -> MessagePage:
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    return await _answered(mailbox.mail_messages(query))


@router.get("/{connector_id}/mail/message", response_model=MailMessage)
async def mail_message(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    ref: Annotated[MessageRef, Query()],
) -> MailMessage:
    """One letter, which opening marks read (D368)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    return await _answered(mailbox.mail_message(ref))


@router.post("/{connector_id}/mail/seen", status_code=204)
async def mark_messages(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: MarkRequest,
) -> None:
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    await _answered(mailbox.mark_messages(request))


@router.post("/{connector_id}/mail/delete", response_model=MessagesDeleted)
async def delete_messages(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    selection: MessageSelection,
) -> MessagesDeleted:
    """Into Trash, or for good from Trash itself (D370)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    return await _answered(mailbox.delete_messages(selection))


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail={
            "message": say(
                "Attachments come to more than {mb} MB, which is more than a letter may carry",
                mb=MAX_OUTGOING_BYTES // (1024 * 1024),
            )
        },
    )


async def _letter(
    message: str, files: list[UploadFile], owner: uuid.UUID
) -> tuple[OutgoingMessage, list[OutgoingFile]]:
    """The letter, its uploads and the files it names in the owner's folder (D374).

    Read here rather than by the mailbox: a file of somebody's storage is the
    application's to find, by the one containment rule (D8).
    """
    try:
        outgoing = OutgoingMessage.model_validate(json.loads(message))
    except (ValueError, ValidationError) as invalid:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", "message"], "msg": str(invalid), "type": "value_error"}],
        ) from None
    attached: list[OutgoingFile] = []
    total = 0
    for upload in files:
        body = await upload.read(MAX_OUTGOING_BYTES - total + 1)
        total += len(body)
        if total > MAX_OUTGOING_BYTES:
            raise _too_large()
        attached.append(
            OutgoingFile(
                filename=mail_files.safe_name(upload.filename or ""),
                media_type=upload.content_type or "application/octet-stream",
                body=body,
            )
        )
    if outgoing.stored_files:
        try:
            stored = await to_thread.run_sync(
                lambda: mail_files.read_stored(
                    storage.home_dir(owner), outgoing.stored_files, MAX_OUTGOING_BYTES - total
                )
            )
        except mail_files.TooLarge:
            raise _too_large() from None
        except ValueError as refused:
            raise HTTPException(status_code=422, detail={"message": str(refused)}) from None
        attached.extend(stored)
    return outgoing, attached


@router.post("/{connector_id}/mail/send", response_model=MessageSent)
async def send_message(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    # The letter, as OutgoingMessage JSON beside the files.
    message: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 - FastAPI reads the default, never mutates it
) -> MessageSent:
    """A letter, its uploads and its files from the owner's folder, 25 MB in all (D370)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    outgoing, attached = await _letter(message, files, current_user.id)
    return await _answered(mailbox.send_message(outgoing, attached))


@router.post("/{connector_id}/mail/draft", response_model=DraftSaved)
async def save_draft(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    message: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 - FastAPI reads the default, never mutates it
) -> DraftSaved:
    """Into Drafts, replacing the draft it was opened from (D375)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    outgoing, attached = await _letter(message, files, current_user.id)
    return await _answered(mailbox.save_draft(outgoing, attached))


@router.post("/{connector_id}/mail/move", response_model=MessagesMoved)
async def move_messages(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: MoveRequest,
) -> MessagesMoved:
    """To a folder of this mailbox, checked before anything moves (D376)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    return await _answered(mailbox.move_messages(request))


@router.get("/{connector_id}/mail/my-files", response_model=mail_files.FolderListing)
async def my_files(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    path: str = "",
) -> mail_files.FolderListing:
    """One folder of the owner's storage, to attach a file from (D374).

    A mail route, so `own`: the storage listed is the mailbox owner's, who is
    the person asking.
    """
    await _mailbox(session, current_user, resources, connector_id)
    try:
        return await to_thread.run_sync(
            lambda: mail_files.listing(storage.home_dir(current_user.id), path)
        )
    except ValueError as refused:
        raise HTTPException(status_code=422, detail={"message": str(refused)}) from None


@router.get("/{connector_id}/mail/attachment", response_class=Response)
async def download_attachment(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: Annotated[AttachmentRequest, Query()],
) -> Response:
    """The bytes, under the attachment's own name (D371)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    found = await _answered(
        mailbox.mail_attachment(MessageRef(folder=request.folder, uid=request.uid), request.part)
    )
    return Response(
        content=found.body,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": content_tickets.content_disposition(
                mail_files.safe_name(found.filename), inline=False
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{connector_id}/mail/attachment/keep", response_model=AttachmentKept)
async def keep_attachment(
    session: SessionDep,
    current_user: CurrentUser,
    resources: ResourcesDep,
    connector_id: uuid.UUID,
    request: AttachmentRequest,
) -> AttachmentKept:
    """Into `Mail/<address>/` of the owner's folder, under their limit (D371)."""
    mailbox = await _mailbox(session, current_user, resources, connector_id)
    found = await _answered(
        mailbox.mail_attachment(MessageRef(folder=request.folder, uid=request.uid), request.part)
    )
    connector = await get_or_404(session, connector_id, current_user, requires="own")
    owner = connector.owner_id
    try:
        path = await to_thread.run_sync(
            lambda: mail_files.keep_attachment(
                home=storage.home_dir(owner),
                address=mailbox.mailbox_address(),
                filename=found.filename,
                body=found.body,
                limit_bytes=quota.limit_bytes(owner),
            )
        )
    except StorageFull as full:
        raise HTTPException(status_code=507, detail={"message": full.message}) from None
    except (OSError, ValueError):
        raise Problem(507, "mail.attachment_not_stored", error_kind="config") from None
    return AttachmentKept(path=path)

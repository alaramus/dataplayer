"""The agent's API: models, keys and choices, conversations and their answers."""

import uuid
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import Json, ValidationError
from sqlmodel import col, update

from app.ai import attachments, conversations, preferences, quick_chat
from app.ai.catalog import Provider, catalog
from app.ai.content import opened, opened_bytes, sealed
from app.ai.models import (
    TERMINAL,
    AgentAnswer,
    AgentModelPublic,
    AgentRun,
    AgentRunPublic,
    AgentSettingsPublic,
    AgentSettingsUpdate,
    ChatProjectPublic,
    ChatProjectsPublic,
    ChatProjectWrite,
    ConversationMessageCreate,
    ConversationPublic,
    ConversationsPublic,
    ConversationSummary,
    ConversationUpdate,
    ProviderKeyCheck,
    ProviderKeyTry,
    ProviderKeyWrite,
    ScreenContexts,
)
from app.ai.runner import AgentRunnerDep, RunRefused
from app.connectors.content_tickets import content_disposition
from app.core.db import SessionDep
from app.core.schemas import Message
from app.users.deps import CurrentUser

router = APIRouter(prefix="/ai", tags=["ai"])

NOT_FOUND = {"message": "No such conversation"}


@router.get("/quick-chats", response_model=list[quick_chat.QuickChatSummary])
async def list_quick_chats(
    session: SessionDep, current_user: CurrentUser, archived: bool = False
) -> Any:
    return await quick_chat.list_for_owner(session, current_user.id, archived=archived)


@router.post(
    "/quick-chats", response_model=quick_chat.QuickChatSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_quick_chat(session: SessionDep, current_user: CurrentUser) -> Any:
    chat = quick_chat.QuickConversation(
        owner_id=current_user.id, title=sealed("New chat")
    )
    session.add(chat)
    await session.commit()
    return quick_chat.summary(chat)


@router.delete("/quick-chats/archived", response_model=Message)
async def delete_archived_quick_chats(
    session: SessionDep, current_user: CurrentUser
) -> Any:
    count = await quick_chat.delete_archived_for_owner(session, current_user.id)
    return Message(message=f"{count} quick chats deleted")


@router.get("/quick-chats/{chat_id}", response_model=quick_chat.QuickChatPublic)
async def read_quick_chat(
    session: SessionDep, current_user: CurrentUser, chat_id: uuid.UUID
) -> Any:
    chat = await quick_chat.get_for_owner(session, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail={"message": "No such quick chat"})
    return await quick_chat.public(session, chat)


@router.patch("/quick-chats/{chat_id}", response_model=quick_chat.QuickChatSummary)
async def update_quick_chat(
    session: SessionDep,
    current_user: CurrentUser,
    chat_id: uuid.UUID,
    body: quick_chat.QuickChatUpdate,
) -> Any:
    chat = await quick_chat.get_for_owner(session, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail={"message": "No such quick chat"})
    if "project_id" in body.model_fields_set and body.project_id is not None:
        project = await conversations.project_for_owner(session, body.project_id, current_user.id)
        if project is None:
            raise HTTPException(status_code=404, detail=NO_PROJECT)
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=422, detail={"message": "Write a chat title first"})
        chat.title = sealed(body.title.strip())
    if body.pinned is not None:
        chat.pinned = body.pinned
    if body.archived is not None:
        chat.archived = body.archived
    if "project_id" in body.model_fields_set:
        chat.project_id = body.project_id
    session.add(chat)
    await session.commit()
    return quick_chat.summary(chat)


@router.delete("/quick-chats/{chat_id}", response_model=Message)
async def delete_quick_chat(
    session: SessionDep, current_user: CurrentUser, chat_id: uuid.UUID
) -> Any:
    chat = await quick_chat.get_for_owner(session, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail={"message": "No such quick chat"})
    await session.delete(chat)
    await session.commit()
    return Message(message="Quick chat deleted")


@router.post("/quick-chats/{chat_id}/messages", response_model=quick_chat.QuickChatPublic)
async def send_quick_chat_message(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    chat_id: uuid.UUID,
    body: quick_chat.QuickChatSend,
) -> Any:
    chat = await quick_chat.get_for_owner(session, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail={"message": "No such quick chat"})
    if body.model_key is not None and catalog().find(body.model_key) is None:
        raise HTTPException(status_code=422, detail={"message": "That model is not in the list"})
    try:
        return await quick_chat.send(
            session, chat, current_user.id, body, catalog(), runner.chat_models
        )
    except ValueError as refused:
        raise HTTPException(status_code=422, detail={"message": str(refused)}) from refused
    except RuntimeError as failed:
        raise HTTPException(status_code=502, detail={"message": str(failed)}) from failed


@router.get("/models", response_model=list[AgentModelPublic])
async def read_models(session: SessionDep, current_user: CurrentUser) -> Any:
    """Every model the list holds, and whether this person has a key for it (D140)."""
    return await preferences.models_for(session, current_user.id, catalog())


@router.get("/settings", response_model=AgentSettingsPublic)
async def read_settings(session: SessionDep, current_user: CurrentUser) -> Any:
    return await preferences.settings_of(session, current_user.id, catalog())


@router.patch("/settings", response_model=AgentSettingsPublic)
async def update_settings(
    session: SessionDep, current_user: CurrentUser, update: AgentSettingsUpdate
) -> Any:
    try:
        return await preferences.update_settings(
            session, current_user.id, update, catalog()
        )
    except preferences.SettingsRefused as refused:
        raise HTTPException(status_code=422, detail={"message": refused.message})


@router.put("/keys/{provider}", response_model=AgentSettingsPublic)
async def write_key(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    provider: Provider,
    body: ProviderKeyWrite,
) -> Any:
    """Set or replace a key. What comes back says it is set, never what it is."""
    if provider == "typesafe":
        checked = await preferences.check_key(
            session,
            current_user.id,
            provider,
            catalog(),
            runner.chat_models,
            candidate=body.key.get_secret_value(),
        )
        if not checked.ok:
            raise HTTPException(status_code=422, detail={"message": checked.message})
    await preferences.set_key(
        session, current_user.id, provider, body.key.get_secret_value()
    )
    return await preferences.settings_of(session, current_user.id, catalog())


@router.delete("/keys/{provider}", response_model=AgentSettingsPublic)
async def remove_key(
    session: SessionDep, current_user: CurrentUser, provider: Provider
) -> Any:
    await preferences.remove_key(session, current_user.id, provider)
    return await preferences.settings_of(session, current_user.id, catalog())


@router.post("/keys/{provider}/check", response_model=ProviderKeyCheck)
async def check_key(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    provider: Provider,
    body: ProviderKeyTry | None = None,
) -> Any:
    """The key being typed, or the stored one. A check stores nothing (D140)."""
    candidate = body.key.get_secret_value() if body is not None and body.key else None
    return await preferences.check_key(
        session,
        current_user.id,
        provider,
        catalog(),
        runner.chat_models,
        candidate=candidate,
    )


NO_PROJECT = {"message": "No such project"}


@router.get("/projects", response_model=ChatProjectsPublic)
async def read_projects(session: SessionDep, current_user: CurrentUser) -> Any:
    """The folders a person sorted their conversations into (D141)."""
    return await conversations.projects_for_owner(session, current_user.id)


@router.post(
    "/projects", response_model=ChatProjectPublic, status_code=status.HTTP_201_CREATED
)
async def create_project(
    session: SessionDep, current_user: CurrentUser, body: ChatProjectWrite
) -> Any:
    project = await conversations.create_project(
        session, current_user.id, body.name.strip()
    )
    return ChatProjectPublic(id=project.id, name=body.name.strip())


@router.patch("/projects/{project_id}", response_model=ChatProjectPublic)
async def rename_project(
    session: SessionDep,
    current_user: CurrentUser,
    project_id: uuid.UUID,
    body: ChatProjectWrite,
) -> Any:
    project = await conversations.project_for_owner(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail=NO_PROJECT)
    renamed = await conversations.rename_project(session, project, body.name.strip())
    return ChatProjectPublic(id=renamed.id, name=body.name.strip())


@router.delete("/projects/{project_id}", response_model=Message)
async def delete_project(
    session: SessionDep, current_user: CurrentUser, project_id: uuid.UUID
) -> Any:
    """The folder only. Every conversation in it stays, out of any folder."""
    project = await conversations.project_for_owner(session, project_id, current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail=NO_PROJECT)
    await session.exec(
        update(quick_chat.QuickConversation)
        .where(col(quick_chat.QuickConversation.project_id) == project.id)
        .values(project_id=None)
    )
    await conversations.delete_project(session, project)
    return Message(message="Project deleted")


@router.get("/conversations", response_model=ConversationsPublic)
async def read_conversations(
    session: SessionDep,
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    archived: bool = False,
) -> Any:
    """The history, pinned first; or the archive, which the settings show."""
    return await conversations.list_for_owner(
        session, current_user.id, skip=skip, limit=limit, archived=archived
    )


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(session: SessionDep, current_user: CurrentUser) -> Any:
    conversation = await conversations.create(session, current_user.id)
    return conversations.summary_of(conversation, active=False, waiting=False)


# Before the route addressed by id, which would otherwise answer 422 for this
# path rather than letting it through.
@router.delete("/conversations/archived", response_model=Message)
async def delete_archived_conversations(
    session: SessionDep, current_user: CurrentUser, runner: AgentRunnerDep
) -> Any:
    """Empty the archive, permanently. Nothing in the history is touched (D141)."""
    ids = await conversations.archived_ids_for_owner(session, current_user.id)
    await runner.forget(ids)
    await conversations.delete_rows(session, ids)
    return Message(message=f"{len(ids)} conversations deleted")


@router.get("/conversations/{conversation_id}", response_model=ConversationPublic)
async def read_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    conversation_id: uuid.UUID,
) -> Any:
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return await conversations.conversation_public(
        session, conversation, runner.partial_answers()
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationSummary)
async def update_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
) -> Any:
    """Its name, pin, archive, model, policy or project; a model is also the person's."""
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if body.model_key is not None and catalog().find(body.model_key) is None:
        raise HTTPException(
            status_code=422, detail={"message": "That model is not in the list"}
        )
    if body.auto_provider is not None:
        fallback = catalog().find(body.model_key)
        if fallback is None or fallback.provider != body.auto_provider:
            raise HTTPException(
                status_code=422,
                detail={"message": "Choose a fallback model from this provider"},
            )
        if await preferences.key_for(session, current_user.id, body.auto_provider) is None:
            raise HTTPException(
                status_code=422,
                detail={"message": "Set this model provider's API key first"},
            )
        if await preferences.key_for(session, current_user.id, "typesafe") is None:
            raise HTTPException(status_code=422, detail={"message": "Set a Jev API key first"})
    if body.change_policy == "jev" and await preferences.key_for(
        session, current_user.id, "typesafe"
    ) is None:
        raise HTTPException(status_code=422, detail={"message": "Set a Jev API key first"})
    # A folder is named as sent, so that `null` can take a conversation out of
    # one; somebody else's folder is not found, like everything else here.
    move = "project_id" in body.model_fields_set
    if move and body.project_id is not None:
        project = await conversations.project_for_owner(
            session, body.project_id, current_user.id
        )
        if project is None:
            raise HTTPException(status_code=404, detail=NO_PROJECT)
    title = body.title.strip() if body.title is not None else None
    if body.model_key is not None:
        await preferences.remember_model(
            session, current_user.id, body.model_key, body.auto_provider
        )
    changed = await conversations.change(
        session,
        conversation,
        title=title,
        pinned=body.pinned,
        archived=body.archived,
        model_key=body.model_key,
        auto_provider=body.auto_provider,
        set_auto_provider=(
            "auto_provider" in body.model_fields_set or body.model_key is not None
        ),
        change_policy=body.change_policy,
        project_id=body.project_id,
        move=move,
    )
    current = await conversations.active_run(session, conversation_id)
    return conversations.summary_of(
        changed,
        active=current is not None,
        waiting=current is not None and current.status == "awaiting_answer",
    )


@router.delete("/conversations/{conversation_id}", response_model=Message)
async def delete_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    conversation_id: uuid.UUID,
) -> Any:
    """Permanently. A running answer is stopped first (D141)."""
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    await runner.forget([conversation_id])
    await conversations.delete_rows(session, [conversation_id])
    return Message(message="Conversation deleted")


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AgentRunPublic,
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_message(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    conversation_id: uuid.UUID,
    text: Annotated[str, Form()] = "",
    contexts: Annotated[Json[ScreenContexts] | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> Any:
    """Say something, with files if any; the answer is written by a task and
    heard on the socket (D137, D142).

    A form rather than JSON, for the files. The attached tabs are a field of it
    holding their JSON list, the way an action's parameters travel beside its
    file; typed as JSON of ScreenContext rather than as a bare string, so the
    schema still names the type the client builds them with.
    """
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        body = ConversationMessageCreate(
            text=text, contexts=contexts.root if contexts is not None else []
        )
    except ValidationError as refused:
        raise HTTPException(
            status_code=422,
            detail={"message": "The message or the tabs attached to it could not be read"},
        ) from refused
    try:
        attached = await attachments.read_uploads(files or [])
    except attachments.AttachmentRefused as refused:
        raise HTTPException(status_code=422, detail={"message": refused.message}) from refused
    if not body.text.strip() and not attached:
        raise HTTPException(
            status_code=422, detail={"message": "Write a message or attach a file"}
        )
    try:
        run = await runner.start(
            session, owner_id=current_user.id, conversation=conversation,
            text=body.text, contexts=body.contexts, attachments=attached,
        )
    except RunRefused as refused:
        raise HTTPException(
            status_code=refused.status_code, detail={"message": refused.message}
        )
    return await conversations.run_public(session, run, partial_answer="")


@router.get(
    "/conversations/{conversation_id}/attachments/{attachment_id}",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def read_attachment(
    session: SessionDep,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> Response:
    """A file sent with a message, as it was sent (D142).

    Served as what it was taken for, never as what its name says: an image by
    the type its bytes showed, anything else as plain text.
    """
    found = await conversations.attachment_for_owner(
        session, conversation_id, attachment_id, current_user.id
    )
    if found is None:
        raise HTTPException(status_code=404, detail={"message": "No such file"})
    return Response(
        content=opened_bytes(found.content),
        media_type=found.media_type if found.kind == "image" else "text/plain; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(opened(found.name), inline=True),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


async def _owned_run(
    session: SessionDep, run_id: uuid.UUID, owner_id: uuid.UUID
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None or run.owner_id != owner_id:
        raise HTTPException(status_code=404, detail={"message": "No such answer"})
    return run


@router.get("/runs/{run_id}", response_model=AgentRunPublic)
async def read_run(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    run_id: uuid.UUID,
) -> Any:
    """The authority on an answer, with its text so far while it is written."""
    run = await _owned_run(session, run_id, current_user.id)
    return await conversations.run_public(
        session, run, partial_answer=runner.partial_answers().get(run_id)
    )


@router.post("/runs/{run_id}/answer", response_model=AgentRunPublic)
async def answer_run(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    run_id: uuid.UUID,
    body: AgentAnswer,
) -> Any:
    """Continue the exact tool call held in LangGraph's persisted pause."""
    run = await _owned_run(session, run_id, current_user.id)
    try:
        await runner.resume(session, run=run, answer=body.answer)
    except RunRefused as refused:
        raise HTTPException(
            status_code=refused.status_code, detail={"message": refused.message}
        )
    await session.refresh(run)
    return await conversations.run_public(session, run, partial_answer="")


@router.post("/runs/{run_id}/cancel", response_model=AgentRunPublic)
async def cancel_run(
    session: SessionDep,
    current_user: CurrentUser,
    runner: AgentRunnerDep,
    run_id: uuid.UUID,
) -> Any:
    """Stop. What was already written stays in the conversation (D137)."""
    run = await _owned_run(session, run_id, current_user.id)
    if run.status in TERMINAL:
        return await conversations.run_public(session, run)
    if await runner.cancel_pause(session, run):
        await session.refresh(run)
        return await conversations.run_public(session, run)
    if not await runner.cancel(run_id):
        raise HTTPException(
            status_code=409,
            detail={"message": "This answer is not being written by this server"},
        )
    await session.refresh(run)
    return await conversations.run_public(session, run)

"""The agent's API: models, keys and choices, conversations and their answers."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app.ai import conversations, preferences
from app.ai.catalog import Provider, catalog
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
)
from app.ai.runner import AgentRunnerDep, RunRefused
from app.core.db import SessionDep
from app.core.schemas import Message
from app.users.deps import CurrentUser

router = APIRouter(prefix="/ai", tags=["ai"])

NOT_FOUND = {"message": "No such conversation"}


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
    provider: Provider,
    body: ProviderKeyWrite,
) -> Any:
    """Set or replace a key. What comes back says it is set, never what it is."""
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
    """Its name, its pin, or whether it is in the archive."""
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if body.model_key is not None and catalog().find(body.model_key) is None:
        raise HTTPException(
            status_code=422, detail={"message": "That model is not in the list"}
        )
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
    changed = await conversations.change(
        session,
        conversation,
        title=title,
        pinned=body.pinned,
        archived=body.archived,
        model_key=body.model_key,
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
    body: ConversationMessageCreate,
) -> Any:
    """Say something; the answer is written by a task and heard on the socket (D137)."""
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        run = await runner.start(
            session, owner_id=current_user.id, conversation=conversation,
            text=body.text, contexts=body.contexts,
        )
    except RunRefused as refused:
        raise HTTPException(
            status_code=refused.status_code, detail={"message": refused.message}
        )
    return await conversations.run_public(session, run, partial_answer="")


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

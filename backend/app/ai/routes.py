"""The agent's API: models, keys and choices, conversations and their answers."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app.ai import conversations, preferences
from app.ai.catalog import Provider, catalog
from app.ai.models import (
    TERMINAL,
    AgentModelPublic,
    AgentRun,
    AgentRunPublic,
    AgentSettingsPublic,
    AgentSettingsUpdate,
    ConversationMessageCreate,
    ConversationPublic,
    ConversationRename,
    ConversationsPublic,
    ConversationSummary,
    ProviderKeyCheck,
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
) -> Any:
    return await preferences.check_key(
        session, current_user.id, provider, catalog(), runner.chat_models
    )


@router.get("/conversations", response_model=ConversationsPublic)
async def read_conversations(
    session: SessionDep,
    current_user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Any:
    return await conversations.list_for_owner(
        session, current_user.id, skip=skip, limit=limit
    )


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(session: SessionDep, current_user: CurrentUser) -> Any:
    conversation = await conversations.create(session, current_user.id)
    return ConversationSummary(
        id=conversation.id,
        title="New chat",
        updated_at=conversation.updated_at,
        active=False,
    )


@router.delete("/conversations", response_model=Message)
async def delete_all_conversations(
    session: SessionDep, current_user: CurrentUser, runner: AgentRunnerDep
) -> Any:
    """Every conversation of this person, permanently (D141)."""
    ids = await conversations.ids_for_owner(session, current_user.id)
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
async def rename_conversation(
    session: SessionDep,
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    body: ConversationRename,
) -> Any:
    """A name the person chose, which no title from the model replaces."""
    conversation = await conversations.get_for_owner(
        session, conversation_id, current_user.id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    renamed = await conversations.rename(session, conversation, body.title.strip())
    active = await conversations.active_run(session, conversation_id) is not None
    return ConversationSummary(
        id=renamed.id, title=body.title.strip(), updated_at=renamed.updated_at, active=active
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
    if not await runner.cancel(run_id):
        raise HTTPException(
            status_code=409,
            detail={"message": "This answer is not being written by this server"},
        )
    await session.refresh(run)
    return await conversations.run_public(session, run)

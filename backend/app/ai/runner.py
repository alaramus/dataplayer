"""Writing an answer: recorded first, carried out by a task after (D137).

The request that sends a message records the run and returns. A task streams
the model's answer over the socket, writes the transcript when it ends, and is
the only thing that holds the partial answer — which is why a page opened
mid-answer asks the run for it rather than the database.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.cache import DataCache
from app.adapters.resources import ResourceStore
from app.ai import checkpoints, conversations, preferences
from app.ai.attachments import NewAttachment, model_content
from app.ai.catalog import PROVIDER_TITLES, ModelCatalog, ModelInfo
from app.ai.models import AgentRun, Conversation, RunStatus, ScreenContext, StepStatus
from app.ai.prompts import SYSTEM_PROMPT, TITLE_PROMPT
from app.ai.providers import ChatModels
from app.ai.tools import (
    LIMIT_MESSAGE,
    ToolLimitReached,
    ToolRuntime,
    build_tools,
    transfer_policy,
)
from app.ai.topic import (
    AgentEvent,
    AnswerDelta,
    ReasoningDelta,
    RunChanged,
    StepChanged,
    TitleChanged,
    WorkspaceOpened,
    announce,
)
from app.core.config import settings
from app.core.db import async_session_maker
from app.realtime.topics import TopicSet

logger = logging.getLogger(__name__)

THINKING = "Thinking"
# How often streamed text is sent: a frame per token is a frame per few
# milliseconds, and the window redraws no faster than this anyway.
DELTA_INTERVAL_SECONDS = 0.05
TITLE_TIMEOUT_SECONDS = 60.0
TITLE_OUTPUT_TOKENS = 2048
TITLE_MAX_CHARS = 80
TITLE_EXCERPT_CHARS = 2000


class RunRefused(Exception):
    """The message will not be answered, and the answer says why."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class RunPaused(Exception):
    """LangGraph persisted a question and stopped before the next model call."""


@dataclass
class _Active:
    task: asyncio.Task[None]
    owner_id: uuid.UUID
    conversation_id: uuid.UUID
    answer: list[str] = field(default_factory=list)
    # Stop was pressed. A task cancelled without it is the application
    # shutting down, and the startup sweep says `interrupted` instead.
    stopping: bool = False


class _Deltas:
    """Text waiting to be sent, flushed at most every DELTA_INTERVAL_SECONDS."""

    def __init__(self) -> None:
        self.answer = ""
        self.reasoning = ""
        self._sent_at = time.monotonic()

    def due(self) -> bool:
        return time.monotonic() - self._sent_at >= DELTA_INTERVAL_SECONDS

    def take(self) -> tuple[str, str]:
        answer, reasoning = self.answer, self.reasoning
        self.answer = self.reasoning = ""
        self._sent_at = time.monotonic()
        return answer, reasoning


class AgentRunner:
    """The answers this process is writing.

    Process-local, like a query run and for the same reason: a task and a
    stream do not cross a process, and there is one (D124).
    """

    def __init__(
        self,
        *,
        checkpointer: BaseCheckpointSaver[Any],
        chat_models: ChatModels,
        topics: TopicSet,
        catalog: ModelCatalog,
        resources: ResourceStore,
        data_cache: DataCache,
    ) -> None:
        self.chat_models = chat_models
        self._checkpointer = checkpointer
        self._topics = topics
        self._catalog = catalog
        self._resources = resources
        self._data_cache = data_cache
        self._active: dict[uuid.UUID, _Active] = {}
        self._lock = asyncio.Lock()

    def partial_answers(self) -> dict[uuid.UUID, str]:
        return {run_id: "".join(active.answer) for run_id, active in self._active.items()}

    async def start(
        self,
        session: AsyncSession,
        *,
        owner_id: uuid.UUID,
        conversation: Conversation,
        text: str,
        contexts: list[ScreenContext],
        attachments: Sequence[NewAttachment] = (),
    ) -> AgentRun:
        model = await preferences.model_for(
            session, owner_id, conversation, self._catalog
        )
        if model is None:
            raise RunRefused(409, "Choose a model in the agent settings first")
        # The composer offers images only to a model that reads them (D142);
        # this is the same rule for a client that did not ask first.
        if any(one.kind == "image" for one in attachments) and not model.image_input:
            raise RunRefused(422, f"{model.name} does not read images; choose a model that does")
        key = await preferences.key_for(session, owner_id, model.provider)
        if key is None:
            raise RunRefused(
                409,
                f"Add a key for {PROVIDER_TITLES[model.provider]} in the agent settings first",
            )
        async with self._lock:
            # Checked and recorded under one lock: two sends at once would
            # otherwise both find the conversation idle.
            if await conversations.active_run(session, conversation.id) is not None:
                raise RunRefused(409, "This conversation is already being answered")
            # A conversation the person named never asks the model for a title.
            first = (
                not conversation.title_is_custom
                and not await conversations.has_answer(session, conversation.id)
            )
            run = await conversations.record_run(
                session,
                conversation_id=conversation.id,
                owner_id=owner_id,
                model_key=model.key,
            )
            await conversations.add_message(
                session, conversation.id, "user", text, run.id, attachments
            )
            task = asyncio.create_task(
                self._carry_out(
                    run.id, owner_id, conversation.id, model, key, text, contexts, first,
                    attachments=attachments,
                )
            )
            self._active[run.id] = _Active(
                task=task, owner_id=owner_id, conversation_id=conversation.id
            )
        if first:
            # A photo sent alone names the chat after itself.
            title = conversations.first_line_title(
                text if text.strip() or not attachments else attachments[0].name
            )
            if await conversations.retitle(session, conversation.id, title):
                await self._say(owner_id, TitleChanged(conversation_id=conversation.id, title=title))
        await self._say(
            owner_id,
            RunChanged(conversation_id=conversation.id, run_id=run.id, status="running"),
        )
        return run

    async def cancel(self, run_id: uuid.UUID) -> bool:
        """Stop an answer this process is writing. False if it is not."""
        async with self._lock:
            active = self._active.get(run_id)
        if active is None:
            return False
        active.stopping = True
        active.task.cancel()
        await asyncio.wait({active.task})
        return True

    async def cancel_pause(self, session: AsyncSession, run: AgentRun) -> bool:
        if run.status != "awaiting_answer":
            return False
        pending = await conversations.running_tool_step(session, run.id)
        if pending is not None:
            await conversations.finish_step(
                session, run.id, pending.ordinal, status="cancelled"
            )
        await conversations.finish_step(session, run.id, 0, status="cancelled")
        await checkpoints.keep_latest(session, str(run.conversation_id))
        await conversations.finish_run(session, run.id, status="cancelled")
        await self._say(
            run.owner_id,
            RunChanged(
                conversation_id=run.conversation_id,
                run_id=run.id,
                status="cancelled",
            ),
        )
        return True

    async def resume(
        self, session: AsyncSession, *, run: AgentRun, answer: str
    ) -> AgentRun:
        if run.status != "awaiting_answer":
            raise RunRefused(409, "This answer is not waiting for a response")
        pending = await conversations.pending_question(session, run.id)
        if pending is None or answer not in pending.choices:
            raise RunRefused(422, "Choose one of the answers offered")
        model = self._catalog.find(run.model_key)
        if model is None:
            raise RunRefused(409, "Choose a model in the agent settings first")
        key = await preferences.key_for(session, run.owner_id, model.provider)
        if key is None:
            raise RunRefused(
                409,
                f"Add a key for {PROVIDER_TITLES[model.provider]} in the agent settings first",
            )
        conversation = await session.get(Conversation, run.conversation_id)
        first = (
            conversation is not None
            and not conversation.title_is_custom
            and not await conversations.has_answer(session, run.conversation_id)
        )
        question = await conversations.user_message_for_run(session, run.id)
        reasoning = await conversations.step_detail(session, run.id, 0)
        async with self._lock:
            if run.id in self._active:
                raise RunRefused(409, "This answer is already being continued")
            await conversations.set_run_status(session, run.id, "running")
            task = asyncio.create_task(
                self._carry_out(
                    run.id,
                    run.owner_id,
                    run.conversation_id,
                    model,
                    key,
                    question,
                    [],
                    first,
                    resume_answer=answer,
                    reasoning_seed=reasoning,
                    initial_tokens=(run.input_tokens, run.output_tokens),
                )
            )
            self._active[run.id] = _Active(
                task=task, owner_id=run.owner_id, conversation_id=run.conversation_id
            )
        await self._say(
            run.owner_id,
            RunChanged(
                conversation_id=run.conversation_id, run_id=run.id, status="running"
            ),
        )
        return run

    async def forget(self, conversation_ids: list[uuid.UUID]) -> None:
        """Stop what is being written in these conversations and drop their state.

        Called before their rows are deleted, so a stopping task still finds
        the rows it writes its last words to.
        """
        wanted = set(conversation_ids)
        async with self._lock:
            stopping = [a for a in self._active.values() if a.conversation_id in wanted]
        for active in stopping:
            active.stopping = True
            active.task.cancel()
        if stopping:
            await asyncio.wait({active.task for active in stopping})
        for conversation_id in conversation_ids:
            await self._checkpointer.adelete_thread(str(conversation_id))

    async def aclose(self) -> None:
        async with self._lock:
            active = list(self._active.values())
        for run in active:
            run.task.cancel()
        if active:
            await asyncio.wait({run.task for run in active})

    async def _say(self, owner_id: uuid.UUID, event: AgentEvent) -> None:
        await announce(self._topics, owner_id, event)

    async def _carry_out(
        self,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        model: ModelInfo,
        key: str,
        text: str,
        contexts: list[ScreenContext],
        first: bool,
        resume_answer: str | None = None,
        reasoning_seed: str = "",
        initial_tokens: tuple[int, int] = (0, 0),
        attachments: Sequence[NewAttachment] = (),
    ) -> None:
        active = self._active[run_id]
        reasoning: list[str] = [reasoning_seed] if reasoning_seed else []
        tokens = [initial_tokens[0], initial_tokens[1]]
        status: RunStatus = "succeeded"
        error: str | None = None
        answer = ""
        try:
            async with async_session_maker() as session:
                try:
                    if resume_answer is None:
                        step = await conversations.start_step(
                            session, run_id, 0, "thinking", THINKING
                        )
                        await self._say(
                            owner_id,
                            StepChanged(
                                conversation_id=conversation_id,
                                run_id=run_id,
                                step=conversations.step_public(step, with_detail=False),
                            ),
                        )
                    await self._stream(
                        run_id, owner_id, conversation_id, model, key,
                        (
                            Command(resume=resume_answer)
                            if resume_answer is not None
                            else HumanMessage(
                                content=model_content(
                                    message_with_context(text, contexts), attachments
                                )
                            )
                        ),
                        answer=active.answer, reasoning=reasoning, tokens=tokens,
                    )
                except RunPaused:
                    status = "awaiting_answer"
                except TimeoutError:
                    status = "failed"
                    minutes = round(settings.AI_RUN_TIMEOUT_SECONDS / 60)
                    error = f"The answer took longer than {minutes} minutes and was stopped"
                except ToolLimitReached:
                    status = "failed"
                    error = LIMIT_MESSAGE
                except asyncio.CancelledError:
                    if not active.stopping:
                        raise
                    current = asyncio.current_task()
                    if current is not None:
                        current.uncancel()
                    status = "cancelled"
                except Exception as failure:  # noqa: BLE001 - reduced to a sentence
                    # By type only: a provider's text may carry the request.
                    logger.warning("An answer failed: %s", type(failure).__name__)
                    status = "failed"
                    error = self.chat_models.sentence(model, failure)
                answer = "".join(active.answer)
                if status == "awaiting_answer":
                    await conversations.set_step_detail(
                        session, run_id, 0, "".join(reasoning)
                    )
                    await checkpoints.keep_latest(session, str(conversation_id))
                    await conversations.set_run_status(
                        session,
                        run_id,
                        status,
                        input_tokens=tokens[0],
                        output_tokens=tokens[1],
                    )
                    await self._say(
                        owner_id,
                        RunChanged(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            status=status,
                        ),
                    )
                else:
                    await self._settle(
                        session, run_id, owner_id, conversation_id,
                        status=status, error=error, answer=answer,
                        reasoning="".join(reasoning), tokens=tokens,
                    )
        finally:
            async with self._lock:
                self._active.pop(run_id, None)
        if status == "succeeded" and first:
            await self._write_title(owner_id, conversation_id, model, key, text, answer)

    async def _stream(
        self,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        model: ModelInfo,
        key: str,
        input_value: HumanMessage | Command[Any],
        *,
        answer: list[str],
        reasoning: list[str],
        tokens: list[int],
    ) -> None:
        chat = self.chat_models.build(
            model,
            key,
            max_output_tokens=min(model.max_output_tokens, settings.AI_MAX_OUTPUT_TOKENS),
        )
        async with async_session_maker() as session:
            calls = await conversations.last_step_ordinal(session, run_id)
        runtime = ToolRuntime(
            run_id=run_id,
            owner_id=owner_id,
            conversation_id=conversation_id,
            resources=self._resources,
            data_cache=self._data_cache,
            say=self._say,
            opened=lambda user_id, intent: self._say(
                user_id,
                WorkspaceOpened(conversation_id=conversation_id, intent=intent),
            ),
            calls=calls,
            resume_ordinal=(calls if isinstance(input_value, Command) else None),
        )
        agent = create_agent(
            chat,
            tools=build_tools(runtime),
            system_prompt=SYSTEM_PROMPT,
            checkpointer=self._checkpointer,
            middleware=[
                transfer_policy(runtime),
                # Approaching the chosen model's window, older turns become a
                # summary the same model writes — never a truncation (D139).
                # The window is this project's curated file (D140): an absolute
                # threshold, since no provider profile can be trusted to know it.
                SummarizationMiddleware(
                    chat,
                    trigger=(
                        "tokens",
                        max(
                            1,
                            round(
                                model.context_window
                                * settings.AI_SUMMARY_TRIGGER_FRACTION
                            ),
                        ),
                    ),
                    keep=("messages", settings.AI_SUMMARY_KEEP_MESSAGES),
                ),
            ],
        )
        config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
        deltas = _Deltas()
        async with asyncio.timeout(settings.AI_RUN_TIMEOUT_SECONDS):
            # Written when the answer ends or pauses, not after every step: the
            # older states are pruned anyway (D139).
            async for item in agent.astream(
                input_value if isinstance(input_value, Command) else {"messages": [input_value]},
                config,
                stream_mode=["messages", "updates"],
                durability="exit",
                version="v2",
            ):
                if is_interrupted(item):
                    await self._flush(run_id, owner_id, conversation_id, deltas)
                    raise RunPaused
                chunk = model_chunk(item)
                if chunk is None:
                    continue
                said, thought = split_text(chunk)
                answer.append(said)
                reasoning.append(thought)
                deltas.answer += said
                deltas.reasoning += thought
                if chunk.usage_metadata:
                    tokens[0] += chunk.usage_metadata["input_tokens"]
                    tokens[1] += chunk.usage_metadata["output_tokens"]
                if deltas.due():
                    await self._flush(run_id, owner_id, conversation_id, deltas)
            await self._flush(run_id, owner_id, conversation_id, deltas)

    async def _flush(
        self,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        deltas: _Deltas,
    ) -> None:
        answer, reasoning = deltas.take()
        if reasoning:
            await self._say(
                owner_id,
                ReasoningDelta(
                    conversation_id=conversation_id, run_id=run_id, ordinal=0, text=reasoning
                ),
            )
        if answer:
            await self._say(
                owner_id,
                AnswerDelta(conversation_id=conversation_id, run_id=run_id, text=answer),
            )

    async def _settle(
        self,
        session: AsyncSession,
        run_id: uuid.UUID,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        status: RunStatus,
        error: str | None,
        answer: str,
        reasoning: str,
        tokens: list[int],
    ) -> None:
        """Write what the answer came to. What was written before a stop stays."""
        if answer:
            await conversations.add_message(session, conversation_id, "assistant", answer, run_id)
        step_status: StepStatus = (
            "done" if status == "succeeded" else "cancelled" if status == "cancelled" else "failed"
        )
        for cut in await conversations.close_running_steps(
            session, run_id, status=step_status
        ):
            await self._say(
                owner_id,
                StepChanged(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    step=conversations.step_public(cut, with_detail=False),
                ),
            )
        step = await conversations.finish_step(
            session, run_id, 0, status=step_status, detail=reasoning
        )
        if step is not None:
            await self._say(
                owner_id,
                StepChanged(
                    conversation_id=conversation_id,
                    run_id=run_id,
                    step=conversations.step_public(step, with_detail=False),
                ),
            )
        # Before the run is marked ended, so that an ended run means its state
        # is settled as well.
        await checkpoints.keep_latest(session, str(conversation_id))
        await conversations.finish_run(
            session, run_id, status=status, error=error,
            input_tokens=tokens[0], output_tokens=tokens[1],
        )
        await self._say(
            owner_id,
            RunChanged(conversation_id=conversation_id, run_id=run_id, status=status, error=error),
        )

    async def _write_title(
        self,
        owner_id: uuid.UUID,
        conversation_id: uuid.UUID,
        model: ModelInfo,
        key: str,
        question: str,
        answer: str,
    ) -> None:
        """A title by the chosen model, unless the person named the conversation.

        A title is a courtesy: when the model cannot write one, the first line
        of the question stays, and nothing is reported.
        """
        chat = self.chat_models.build(model, key, max_output_tokens=TITLE_OUTPUT_TOKENS)
        excerpt = (
            f"Person: {question[:TITLE_EXCERPT_CHARS]}\n\n"
            f"Assistant: {answer[:TITLE_EXCERPT_CHARS]}"
        )
        try:
            async with asyncio.timeout(TITLE_TIMEOUT_SECONDS):
                reply = await chat.ainvoke(
                    [SystemMessage(TITLE_PROMPT), HumanMessage(excerpt)]
                )
        except Exception as failure:  # noqa: BLE001 - a title is optional
            logger.info("A title could not be written: %s", type(failure).__name__)
            return
        title = clean_title(text_of(reply))
        if not title:
            return
        async with async_session_maker() as session:
            if await conversations.retitle(session, conversation_id, title):
                await self._say(owner_id, TitleChanged(conversation_id=conversation_id, title=title))


def model_chunk(item: object) -> AIMessageChunk | None:
    """The piece of the model's answer a stream item carries, if it carries one.

    Items from other nodes are skipped: once tools exist their output streams
    too, and it is not the answer.
    """
    if not isinstance(item, dict):
        return None
    data = item.get("data")
    if not isinstance(data, tuple) or len(data) != 2:
        return None
    chunk, metadata = data
    if not isinstance(metadata, dict) or metadata.get("langgraph_node") != "model":
        return None
    return chunk if isinstance(chunk, AIMessageChunk) else None


def is_interrupted(item: object) -> bool:
    if not isinstance(item, dict) or item.get("type") != "updates":
        return False
    data = item.get("data")
    return isinstance(data, dict) and bool(data.get("__interrupt__"))


def split_text(message: BaseMessage) -> tuple[str, str]:
    """What a message says and what it reasoned, from its standard blocks."""
    said: list[str] = []
    thought: list[str] = []
    for block in message.content_blocks:
        # Read as a mapping: the block union is keyed by `type`, and each kind
        # names its text differently.
        fields = cast(Mapping[str, object], block)
        if fields.get("type") == "text":
            said.append(str(fields.get("text") or ""))
        elif fields.get("type") == "reasoning":
            thought.append(str(fields.get("reasoning") or ""))
    return "".join(said), "".join(thought)


def text_of(message: BaseMessage) -> str:
    return split_text(message)[0]


def clean_title(text: str) -> str:
    line = next((part.strip() for part in text.splitlines() if part.strip()), "")
    # Round again: a full stop inside the emphasis hides the marks behind it.
    for _ in range(2):
        line = line.strip("#*_`\"'«» ").rstrip(".")
    return line[:TITLE_MAX_CHARS].strip()


def message_with_context(text: str, contexts: list[ScreenContext]) -> str:
    """Attach only the panel identities the person explicitly chose."""
    if not contexts:
        return text
    lines = [
        f"- {context.label}; kind={context.kind}; panel_id={context.panel_id}"
        + (f"; connector_id={context.connector_id}" if context.connector_id else "")
        + (f"; node_id={context.node_id}" if context.node_id else "")
        for context in contexts
    ]
    return f"{text}\n\nSelected workspace tabs:\n" + "\n".join(lines)


async def settle_interrupted() -> int:
    """At startup, before anything new is answered: what the last stop left."""
    async with async_session_maker() as session:
        return await conversations.recover_interrupted(session)


def get_runner(request: Request) -> AgentRunner:
    runner = request.app.state.agent_runner
    if not isinstance(runner, AgentRunner):
        raise RuntimeError("The application has no agent runner; is the lifespan running?")
    return runner


AgentRunnerDep = Annotated[AgentRunner, Depends(get_runner)]

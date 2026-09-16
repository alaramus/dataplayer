"""The application reads exposed to the model, through the same adapters as UI (D133-D135)."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.adapters.actions import (
    Previews,
    RequiresReviewedPlan,
    SupportsActions,
    TakesParams,
)
from app.adapters.cache import DataCache
from app.adapters.fetch import FetchRequest
from app.adapters.protocol import (
    AdapterError,
    SupportsCatalog,
    SupportsFetch,
    SupportsNodePath,
    SupportsNodeSummary,
    SupportsRelationModel,
)
from app.adapters.query import (
    ExecutionMode,
    QueryRequest,
    StatementClass,
    SupportsQuery,
    SupportsRehearsal,
)
from app.adapters.resources import ResourceStore
from app.ai import conversations
from app.ai.models import (
    AgentPreferences,
    AgentQuestion,
    ChangePreview,
    Conversation,
    OpenIntent,
    StepStatus,
)
from app.ai.topic import StepChanged
from app.connectors import access, crud
from app.connectors.action_lookup import (
    acting_or_501,
    action_for_node,
    allowed_or_403,
    available_or_422,
    perform,
)
from app.connectors.models import Connector
from app.core.access import Access, at_least
from app.core.db import async_session_maker
from app.core.schemas import get_datetime_utc
from app.queries.execution import RunRefused as QueryRefused
from app.queries.execution import admit, limits
from app.queries.unlocks import NEEDED
from app.users.models import User

MAX_ROWS = 20
MAX_RESULT_BYTES = 64 * 1024
MAX_TOOL_CALLS = 50
LIMIT_MESSAGE = "This answer stopped after 50 tool calls. Ask a narrower question."
TRANSFER_MARKER = "transfer_not_allowed"
WITHHELD_RESULT = "[removed: connection no longer allows third-party transfer]"
ALLOW_ONCE = "Allow once"
ALLOW_CHAT = "Allow all changes in this chat"
ALLOW_ALL = "Allow all changes in every chat"
CHANGE_CHOICES = [ALLOW_ONCE, ALLOW_CHAT, ALLOW_ALL]


class ToolLimitReached(Exception):
    """The run used every tool call it is allowed."""


@dataclass
class ToolResult:
    value: Any
    substeps: list[str]


@dataclass
class ToolRuntime:
    run_id: uuid.UUID
    owner_id: uuid.UUID
    conversation_id: uuid.UUID
    resources: ResourceStore
    data_cache: DataCache
    say: Callable[[uuid.UUID, StepChanged], Awaitable[None]]
    opened: Callable[[uuid.UUID, OpenIntent], Awaitable[None]]
    calls: int = 0
    resume_ordinal: int | None = None
    _ordinal_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current_ordinal: ContextVar[int | None] = field(
        default_factory=lambda: ContextVar("ai_tool_ordinal", default=None)
    )

    async def invoke(
        self,
        title: str,
        operation: Callable[[AsyncSession, User], Awaitable[Any]],
    ) -> str:
        async with self._ordinal_lock:
            if self.resume_ordinal is not None:
                ordinal = self.resume_ordinal
                self.resume_ordinal = None
                announce_step = False
            else:
                self.calls += 1
                if self.calls > MAX_TOOL_CALLS:
                    raise ToolLimitReached(LIMIT_MESSAGE)
                ordinal = self.calls
                announce_step = True
        async with async_session_maker() as session:
            if announce_step:
                step = await conversations.start_step(
                    session, self.run_id, ordinal, "tool", title
                )
                await self.say(
                    self.owner_id,
                    StepChanged(
                        conversation_id=self.conversation_id,
                        run_id=self.run_id,
                        step=conversations.step_public(step, with_detail=False),
                    ),
                )
            status: StepStatus = "done"
            token = self._current_ordinal.set(ordinal)
            try:
                user = await session.get(User, self.owner_id)
                if user is None or not user.is_active:
                    result: Any = {"error": "user_not_available"}
                else:
                    result = await operation(session, user)
            except (HTTPException, AdapterError, QueryRefused, ValueError) as failure:
                status = "failed"
                result = {"error": safe_error(failure)}
            finally:
                self._current_ordinal.reset(token)
            detail = None
            if isinstance(result, ToolResult):
                detail = json.dumps({"substeps": result.substeps}, ensure_ascii=False)
                result = result.value
            finished = await conversations.finish_step(
                session, self.run_id, ordinal, status=status, detail=detail
            )
            if finished is not None:
                await self.say(
                    self.owner_id,
                    StepChanged(
                        conversation_id=self.conversation_id,
                        run_id=self.run_id,
                        step=conversations.step_public(finished, with_detail=False),
                    ),
                )
            return bounded_json(result)

    async def pause(self, question: AgentQuestion) -> str:
        """Persist the product-level question before LangGraph pauses the tool."""
        ordinal = self._current_ordinal.get()
        if ordinal is None:
            raise RuntimeError("A question must belong to a running tool step")
        async with async_session_maker() as session:
            await conversations.set_step_detail(
                session, self.run_id, ordinal, question.model_dump_json()
            )
        return str(interrupt(question.model_dump(mode="json")))

    async def confirm_change(
        self,
        session: AsyncSession,
        *,
        connector: Connector,
        question: str,
        preview: ChangePreview | None = None,
    ) -> None:
        """Ask before a change, unless a lasting answer already covers it (D136).

        The three answers differ only in what they store: once keeps nothing,
        this chat is remembered on the conversation, every chat on the person.
        Nothing is decided in the browser, and an answer stored here is what
        later calls in the same process read before asking again.
        """
        conversation = await session.get(Conversation, self.conversation_id)
        if conversation is not None and conversation.allow_all_changes:
            return
        stored = await session.get(AgentPreferences, self.owner_id)
        if stored is not None and stored.allow_all_changes:
            return
        answer = await self.pause(
            AgentQuestion(
                kind="confirm_change",
                question=question,
                choices=CHANGE_CHOICES,
                connector_id=connector.id,
                preview=preview,
            )
        )
        if answer == ALLOW_CHAT and conversation is not None:
            conversation.allow_all_changes = True
            conversation.updated_at = get_datetime_utc()
            session.add(conversation)
            await session.commit()
        elif answer == ALLOW_ALL:
            if stored is None:
                stored = AgentPreferences(user_id=self.owner_id)
            stored.allow_all_changes = True
            session.add(stored)
            await session.commit()

    async def connection_label(self, connector_id: str) -> str:
        """Use a visible name in the server-authored step without trusting the model."""
        try:
            parsed = uuid.UUID(connector_id)
        except ValueError:
            return connector_id
        async with async_session_maker() as session:
            user = await session.get(User, self.owner_id)
            if user is None or not user.is_active:
                return connector_id
            found = await crud.get_with_access(session, connector_id=parsed, user=user)
            return found[0].name if found is not None else connector_id

    async def connector(
        self, session: AsyncSession, user: User, connector_id: uuid.UUID
    ) -> tuple[Connector, Any, Access] | dict[str, Any]:
        connector, held = await access.resolve(
            session, connector_id, user, requires="read"
        )
        if connector.allow_third_party_transfer:
            source = await access.resolve_source(
                session, connector_id, user, self.resources, requires="read"
            )
            return connector, source.adapter, held
        if held == "own":
            answer = await self.pause(
                AgentQuestion(
                    kind="allow_transfer",
                    question=(
                        f'Allow third-party transfer for "{connector.name}" so the agent can read it?'
                    ),
                    choices=["Allow", "Not now"],
                    connector_id=connector.id,
                )
            )
            if answer == "Allow":
                connector.allow_third_party_transfer = True
                connector.updated_at = get_datetime_utc()
                session.add(connector)
                await session.commit()
                source = await access.resolve_source(
                    session, connector_id, user, self.resources, requires="read"
                )
                return connector, source.adapter, held
        return transfer_refusal(connector, held)


def safe_error(failure: Exception) -> str:
    if isinstance(failure, HTTPException):
        detail = failure.detail
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict) and isinstance(detail.get("message"), str):
            return str(detail["message"])
        return "The operation was refused"
    if isinstance(failure, AdapterError):
        return failure.message
    if isinstance(failure, QueryRefused):
        return failure.message
    return str(failure)


def write_refusal(
    connector: Connector, held: Access, changing: Sequence[StatementClass]
) -> str | None:
    """Why these statements may not run, in D66's own sentences.

    The owner's policy stands above every permission, so a `read_only`
    connection is never written — the agent is not even asked. A level the
    person does not hold is refused the same way the query route refuses it.
    """
    if not changing:
        return None
    if connector.execution_policy == "read_only":
        return "The owner of this connection allows reading only"
    for kind in changing:
        needed = NEEDED.get(kind, "own")
        if not at_least(held, needed):
            return f"A {kind} statement needs {needed} access to this connection"
    return None


def statement_substep(statement: dict[str, Any]) -> str:
    base = f"Statement {statement['ordinal'] + 1} · {statement['status']}"
    if statement.get("affected_rows") is not None:
        return f"{base} · {statement['affected_rows']} affected"
    if statement.get("row_count") is not None:
        return f"{base} · {statement['row_count']} rows"
    return base


async def change_preview(
    adapter: SupportsQuery, prepared: Any, request: QueryRequest
) -> ChangePreview:
    """What the change would do, for the confirmation card (D46, D136).

    A drop and every DDL statement are rehearsed in a transaction that is
    rolled back; the rest are shown as their own text. A source that cannot
    rehearse still shows the statements.
    """
    rehearsed: dict[int, Any] = {}
    needs_rehearsal = any(
        statement.kind == "ddl" or statement.destructive
        for statement in prepared.statements
    )
    if needs_rehearsal and isinstance(adapter, SupportsRehearsal):
        rehearsal = await adapter.rehearse_query(request)
        rehearsed = {one.ordinal: one for one in rehearsal.statements}
    lines: list[str] = []
    for statement in prepared.statements:
        line = " ".join(statement.text.split())[:300]
        outcome = rehearsed.get(statement.ordinal)
        if outcome is None:
            lines.append(line)
        elif outcome.outcome == "ok":
            suffix = "would succeed"
            if outcome.affected_rows is not None:
                suffix += f", {outcome.affected_rows} rows affected"
            if outcome.notices:
                suffix += "; " + "; ".join(note.message for note in outcome.notices)
            lines.append(f"{line} — {suffix}")
        elif outcome.outcome == "blocked":
            lines.append(f"{line} — blocked by another transaction; nothing was learnt")
        elif outcome.outcome == "failed":
            detail = outcome.diagnostic.message if outcome.diagnostic else "the source refused it"
            lines.append(f"{line} — would fail: {detail}")
        else:
            lines.append(f"{line} — not reached")
    total = len(prepared.statements)
    return ChangePreview(
        summary=f"{total} statement{'s' if total > 1 else ''} would run",
        lines=lines,
    )


def transfer_refusal(connector: Connector, held: str) -> dict[str, Any]:
    return {
        "error": TRANSFER_MARKER,
        "connector_id": str(connector.id),
        "connector": connector.name,
        "message": (
            "Allow third-party transfer on this connection to let the agent read it."
            if held == "own"
            else "Ask the connection owner to allow third-party transfer."
        ),
    }


def bounded_json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    size = len(encoded.encode())
    if size <= MAX_RESULT_BYTES:
        return encoded
    # JSON escaping can expand a character, so the preview deliberately uses
    # only one eighth of the byte budget; the wrapper then remains bounded for
    # quotes, controls and four-byte Unicode alike.
    preview = encoded.encode()[: MAX_RESULT_BYTES // 8].decode("utf-8", errors="ignore")
    return json.dumps({
        "truncated": True,
        "serialized_bytes": size,
        "limit_bytes": MAX_RESULT_BYTES,
        "preview": preview,
    }, ensure_ascii=False)


def connector_id_from_result(content: object) -> uuid.UUID | None:
    """Find the connection whose data one of our tool results carries, if any.

    A refusal names the connection but holds nothing of it, and it must reach
    the model as it is: withheld, the agent could not even say why it stopped.
    """
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("connector_id"), str):
        return None
    if value.get("error") == TRANSFER_MARKER:
        return None
    try:
        return uuid.UUID(value["connector_id"])
    except ValueError:
        return None


def transfer_policy(runtime: ToolRuntime) -> Any:
    """Withhold prior connector results whenever current access no longer permits them."""

    @wrap_model_call
    async def enforce(
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        async with async_session_maker() as session:
            user = await session.get(User, runtime.owner_id)
            allowed: set[uuid.UUID] = set()
            if user is not None and user.is_active:
                rows = await crud.visible_of(session, user_id=user.id)
                allowed = {
                    connector.id
                    for connector in rows
                    if connector.allow_third_party_transfer
                }
        messages = [
            message.model_copy(update={"content": WITHHELD_RESULT})
            if isinstance(message, ToolMessage)
            and (connector_id := connector_id_from_result(message.content)) is not None
            and connector_id not in allowed
            else message
            for message in request.messages
        ]
        return await handler(request.override(messages=messages))

    return enforce


def build_tools(runtime: ToolRuntime) -> list[BaseTool]:
    async def list_connections() -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            rows, total = await crud.list_for(session, user=user, limit=100)
            return {
                "connections": [
                    {
                        "id": str(connector.id),
                        "name": connector.name,
                        "type": connector.adapter_type,
                        "enabled": connector.enabled,
                        "access": held,
                        "third_party_transfer": (
                            "allowed" if connector.allow_third_party_transfer else TRANSFER_MARKER
                        ),
                    }
                    for connector, held, _owner in rows
                ],
                "total": total,
            }
        return await runtime.invoke("Listing connections", read)

    async def browse_catalog(connector_id: str, node_id: str | None = None) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, _held = resolved
            if not isinstance(adapter, SupportsCatalog):
                return {"error": "This connection has no catalog"}
            nodes = await adapter.list_children(node_id)
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "parent_node_id": node_id,
                "nodes": [node.model_dump(mode="json") for node in nodes],
                "total": len(nodes),
            }
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(f'Browsing catalog in "{label}"', read)

    async def describe_node(connector_id: str, node_id: str) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, _held = resolved
            result: dict[str, Any] = {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "node_id": node_id,
            }
            described = False
            if isinstance(adapter, SupportsRelationModel):
                result["relation"] = (await adapter.relation_model(node_id)).model_dump(mode="json")
                described = True
            if isinstance(adapter, SupportsNodeSummary):
                result["summary"] = (await adapter.node_summary(node_id)).model_dump(mode="json")
                described = True
            if not described:
                result["error"] = "This node cannot be described"
            return result
        return await runtime.invoke(f'Describing "{node_id}"', read)

    async def read_rows(connector_id: str, node_id: str, offset: int = 0) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, _held = resolved
            if not isinstance(adapter, SupportsFetch):
                return {"error": "This node cannot be read as rows"}
            page = await adapter.fetch(FetchRequest(node_id=node_id, limit=MAX_ROWS, offset=offset))
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "node_id": node_id,
                "offset": offset,
                "returned_rows": len(page.rows),
                "has_more": page.has_more,
                "columns": [column.model_dump(mode="json") for column in page.columns],
                "rows": page.rows,
            }
        return await runtime.invoke(f'Reading rows from "{node_id}"', read)

    async def open_in_workspace(
        connector_id: str,
        node_id: str | None = None,
        title: str | None = None,
        view: Literal["catalog", "preferred", "rows", "structure", "summary"] = "preferred",
    ) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, _held = resolved
            node = None
            if node_id is not None:
                if not isinstance(adapter, SupportsNodePath):
                    return {"error": "This connection cannot resolve that node for opening"}
                path = await adapter.path_to(node_id)
                node = path[-1] if path else None
                if node is None:
                    return {"error": "The node does not exist"}
            intent = OpenIntent(
                connector_id=connector.id,
                connector_name=connector.name,
                adapter_type=connector.adapter_type,
                node_id=node_id,
                title=node.name if node is not None else title,
                view=view,
                describable=node.describable if node is not None else False,
                representations=(
                    [one.model_dump(mode="json") for one in node.representations]
                    if node is not None else []
                ),
            )
            await runtime.opened(runtime.owner_id, intent)
            return {
                "opened": True,
                "connector": connector.name,
                "connector_id": str(connector.id),
                "node_id": node_id,
                "view": view,
            }
        return await runtime.invoke(f'Opening "{title or node_id or connector_id}"', read)

    async def run_query(connector_id: str, sql: str) -> str:
        async def run(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, held = resolved
            if not isinstance(adapter, SupportsQuery):
                return {"error": "This connection does not support queries"}
            profile = adapter.query_profile()
            prepared = adapter.prepare_query(sql)
            kinds = [statement.kind for statement in prepared.statements]
            changing: list[StatementClass] = [
                kind for kind in kinds if kind in ("dml", "ddl")
            ]
            refusal = write_refusal(connector, held, changing)
            if refusal is not None:
                return {"error": refusal}
            bounds = limits(statement_timeout_seconds=profile.default_timeout_seconds).model_copy(
                update={"max_result_rows": MAX_ROWS, "max_result_bytes": MAX_RESULT_BYTES}
            )
            # Changes run as one transaction that commits only when every
            # statement succeeded; the agent never holds an open one (D136).
            mode: ExecutionMode = "auto_commit" if changing else "read"
            admit(prepared, bounds, mode=mode)
            request = QueryRequest(text=sql, mode=mode, limits=bounds)
            if changing:
                preview = await change_preview(adapter, prepared, request)
                await runtime.confirm_change(
                    session,
                    connector=connector,
                    question=(
                        f'Run {len(changing)} statement{"s" if len(changing) > 1 else ""} '
                        f'that {"change" if len(changing) > 1 else "changes"} data '
                        f'on "{connector.name}"?'
                    ),
                    preview=preview,
                )
            execution = adapter.open_query(request)
            statements: list[dict[str, Any]] = []
            async for event in execution.events():
                if event.event != "statement_finished":
                    continue
                statements.append(event.model_dump(mode="json"))
            if changing and all(statement["status"] == "succeeded" for statement in statements):
                await runtime.data_cache.invalidate_connector(connector.id)
            value = {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "mode": mode,
                "statements": statements,
            }
            return ToolResult(
                value=value,
                substeps=[statement_substep(statement) for statement in statements],
            )
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(f'Running query on "{label}"', run)

    async def run_action(
        connector_id: str,
        action_name: str,
        node_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        async def run(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, held = resolved
            acting: SupportsActions = acting_or_501(adapter)
            action = await action_for_node(acting, action_name, node_id)
            allowed_or_403(action, held)
            arguments = params or {}
            if isinstance(action, RequiresReviewedPlan):
                return {"error": "Review the operation plan before running it"}
            if not isinstance(action, TakesParams):
                return {"error": f"{action.title} uses a different request transport"}
            if action.requires != "read" or action.destructive:
                preview = None
                if isinstance(action, Previews):
                    shown = await perform(lambda: action.preview(node_id, arguments))
                    preview = ChangePreview(summary=shown.summary, lines=shown.items)
                await runtime.confirm_change(
                    session,
                    connector=connector,
                    question=f'Run "{action.title}" on "{connector.name}"?',
                    preview=preview,
                )
            result = await perform(lambda: action.perform(node_id, arguments))
            await runtime.data_cache.invalidate_connector(connector.id)
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "action": action.name,
                "result": result.model_dump(mode="json"),
            }
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(f'Running action "{action_name}" on "{label}"', run)

    async def list_actions(connector_id: str, node_id: str | None = None) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, held = resolved
            acting: SupportsActions = acting_or_501(adapter)
            offered = await available_or_422(acting, node_id)
            available = {one.name for one in offered.actions}
            actions = []
            for action in await acting.all_actions():
                if not at_least(held, action.requires):
                    continue
                actions.append({
                    "name": action.name,
                    "title": action.title,
                    "available": action.name in available,
                    "unavailable_reason": offered.reason_for(action.name),
                    "destructive": action.destructive,
                    "requires": action.requires,
                    "params_schema": action.params_schema(),
                })
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "node_id": node_id,
                "actions": actions,
            }
        return await runtime.invoke(f'Listing actions for "{node_id or connector_id}"', read)

    async def ask_user(question: str, choices: list[str]) -> str:
        async def prepare(_session: AsyncSession, _user: User) -> Any:
            return {
                "question": question,
                "answer": await runtime.pause(
                    AgentQuestion(kind="ask_user", question=question, choices=choices)
                ),
            }
        return await runtime.invoke("Waiting for your answer", prepare)

    definitions: list[tuple[Callable[..., Awaitable[str]], str, str]] = [
        (list_connections, "list_connections", "List every connection visible to the current person, including transfer policy."),
        (browse_catalog, "browse_catalog", "List one level of a connection catalog. Use opaque ids exactly as returned."),
        (describe_node, "describe_node", "Describe a node's columns, constraints, indexes and summary where supported."),
        (read_rows, "read_rows", "Read at most 20 rows from one opaque node id."),
        (run_query, "run_query", "Run a query. Reads are free; statements that change data ask the person first and run as one committed transaction."),
        (list_actions, "list_actions", "List source-declared actions and their parameter schemas without running them."),
        (run_action, "run_action", "Run one source-declared action with validated parameters. A change asks the person first."),
        (open_in_workspace, "open_in_workspace", "Open a connection or node in the person's Data workspace."),
        (ask_user, "ask_user", "Ask the person one necessary clarifying question instead of guessing."),
    ]
    return [
        StructuredTool.from_function(coroutine=fn, name=name, description=description)
        for fn, name, description in definitions
    ]

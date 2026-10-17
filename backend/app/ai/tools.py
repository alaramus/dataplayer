"""The application reads exposed to the model, through the same adapters as UI (D133-D135)."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from langchain.agents.middleware import ModelRequest, ModelResponse, wrap_model_call
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langchain_typesafe import Noul, TypeSafeClassifier
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
from app.adapters.catalog import NodeView
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
    CHANGING,
    ExecutionMode,
    QueryRequest,
    StatementClass,
    SupportsQuery,
    SupportsRehearsal,
)
from app.adapters.resources import ResourceStore
from app.ai import conversations, preferences
from app.ai.models import (
    AgentPreferences,
    AgentQuestion,
    ChangePreview,
    Conversation,
    OpenIntent,
    StepStatus,
)
from app.ai.search_tool import MAX_HITS as MAX_SEARCH_HITS
from app.ai.search_tool import search_for_agent
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
from app.core.translation import N_, Language, current_language, in_language, say
from app.queries.execution import RunRefused as QueryRefused
from app.queries.execution import admit, limits
from app.queries.write_access import NEEDED
from app.search.engine import SearchEngine
from app.search.models import MAX_CONTEXT
from app.users.models import User

MAX_ROWS = 20
# Nodes of one catalog level a call returns. A level is read whole from the
# source, and a schema of thousands of tables sent at once only reached the
# model as the truncated preview of its first bytes.
MAX_NODES = 100
MAX_RESULT_BYTES = 64 * 1024
MAX_TOOL_CALLS = 50
# Shown to the person as the run's error, MAX_TOOL_CALLS put in.
LIMIT_MESSAGE = N_("This answer stopped after {count} tool calls. Ask a narrower question.")
TRANSFER_MARKER = "transfer_not_allowed"
WITHHELD_RESULT = "[removed: connection no longer allows third-party transfer]"
# What the person may answer, in order. An answer is told apart by its place
# in the list: the words are in the person's language.
ALLOW_ONCE = N_("Allow once")
ALLOW_CHAT = N_("Allow all changes in this chat")
ALLOW_ALL = N_("Allow all changes in every chat")
CHANGE_CHOICES = [ALLOW_ONCE, ALLOW_CHAT, ALLOW_ALL]
ALLOW_TRANSFER = N_("Allow")
NOT_NOW = N_("Not now")
# What a read-only conversation answers instead of asking. It says what to
# do about it, because the agent has no way to change it itself.
READ_ONLY_CHAT = (
    "This chat may only read. Allow changes in it to make this one."
)
JEV_UNAVAILABLE = "Jev could not decide. No change was made. Check the Jev key in settings."
JEV_DENIED = "Jev declined this change. No change was made."

# The language of the person the agent answers. A tool's work runs in English,
# because what it returns is read by the model; what the person reads of it —
# a question, a preview, a step — is worded in theirs (D226).
_PERSON: ContextVar[Language] = ContextVar("ai_person_language", default="en")


def for_person[T](work: Callable[[], T]) -> T:
    return in_language(_PERSON.get(), work)


async def for_person_async[T](work: Callable[[], Awaitable[T]]) -> T:
    token = current_language.set(_PERSON.get())
    try:
        return await work()
    finally:
        current_language.reset(token)


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
    # The one search (S10), and the connections of the tabs attached to the
    # message being answered: what `search` asks without being told to.
    search_engine: SearchEngine | None = None
    attached: tuple[uuid.UUID, ...] = ()
    _ordinal_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _current_ordinal: ContextVar[int | None] = field(
        default_factory=lambda: ContextVar("ai_tool_ordinal", default=None)
    )
    _decision_substeps: ContextVar[list[str] | None] = field(
        default_factory=lambda: ContextVar("ai_decision_substeps", default=None)
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
                    raise ToolLimitReached(LIMIT_MESSAGE.format(count=MAX_TOOL_CALLS))
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
            person = _PERSON.set(current_language.get())
            english = current_language.set("en")
            decisions = self._decision_substeps.set([])
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
                decision_substeps = self._decision_substeps.get() or []
                self._decision_substeps.reset(decisions)
                current_language.reset(english)
                _PERSON.reset(person)
                self._current_ordinal.reset(token)
            detail = None
            if isinstance(result, ToolResult):
                detail = json.dumps({"substeps": decision_substeps + result.substeps}, ensure_ascii=False)
                result = result.value
            elif decision_substeps:
                detail = json.dumps({"substeps": decision_substeps}, ensure_ascii=False)
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
    ) -> str | None:
        """Ask before a change, unless the conversation already answers (D136).

        A sentence comes back where the change may not happen at all, for the
        caller to hand the model in place of the result; `None` means go ahead.
        A read-only conversation is the narrow end and stands above what the
        person allowed in general, so it is answered before anybody is asked.

        The three answers differ only in what they store: once keeps nothing,
        this chat is remembered on the conversation, every chat on the person.
        Nothing is decided in the browser, and an answer stored here is what
        later calls in the same process read before asking again.
        """
        conversation = await session.get(Conversation, self.conversation_id)
        policy = conversations.policy_of(
            conversation.change_policy if conversation is not None else "ask"
        )
        if policy == "read_only":
            return READ_ONLY_CHAT
        if policy == "allow":
            return None
        if policy == "jev":
            # A conversation policy wins over the account-wide allow switch.
            key = await preferences.key_for(session, self.owner_id, "typesafe")
            if key is None:
                self._record_jev(for_person(lambda: say("Jev · unavailable")))
                return JEV_UNAVAILABLE
            state: dict[str, Any] = {"action": question, "connection": connector.name}
            if preview is not None:
                preview_text = preview.model_dump_json()
                state["preview"] = (
                    preview_text
                    if len(preview_text) <= 16384
                    else preview_text[:16384] + " [truncated]"
                )
            try:
                async with asyncio.timeout(30):
                    answer = await TypeSafeClassifier(api_key=key).ainvoke(
                        {
                            "state": state,
                            "questions": {
                                "allow": Noul(
                                    instructions=(
                                        "Should this proposed data change run without human approval? "
                                        "Answer yes only when the action and its effects are clear "
                                        "and the risk is acceptable. Treat missing details as no."
                                    )
                                )
                            },
                        }
                    )
                probability = answer.nouls["allow"].noul
            except Exception:  # noqa: BLE001 - fail closed; never expose provider text
                self._record_jev(for_person(lambda: say("Jev · unavailable")))
                return JEV_UNAVAILABLE
            allowed = probability >= 0.5
            self._record_jev(
                for_person(lambda: say("Jev · allowed") if allowed else say("Jev · declined"))
            )
            return None if allowed else JEV_DENIED
        stored = await session.get(AgentPreferences, self.owner_id)
        if stored is not None and stored.allow_all_changes:
            return None
        choices = for_person(lambda: [say(choice) for choice in CHANGE_CHOICES])
        decision = await self.pause(
            AgentQuestion(
                kind="confirm_change",
                question=question,
                choices=choices,
                connector_id=connector.id,
                preview=preview,
            )
        )
        picked = CHANGE_CHOICES[choices.index(decision)] if decision in choices else ALLOW_ONCE
        if picked == ALLOW_CHAT and conversation is not None:
            conversation.change_policy = "allow"
            conversation.updated_at = get_datetime_utc()
            session.add(conversation)
            await session.commit()
        elif picked == ALLOW_ALL:
            if stored is None:
                stored = AgentPreferences(user_id=self.owner_id)
            stored.allow_all_changes = True
            session.add(stored)
            await session.commit()
        return None

    def _record_jev(self, text: str) -> None:
        substeps = self._decision_substeps.get()
        if substeps is not None:
            substeps.append(text)

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
            choices = for_person(lambda: [say(ALLOW_TRANSFER), say(NOT_NOW)])
            answer = await self.pause(
                AgentQuestion(
                    kind="allow_transfer",
                    question=for_person(
                        lambda: say(
                            'Allow third-party transfer for "{name}" so the agent can read it?',
                            name=connector.name,
                        )
                    ),
                    choices=choices,
                    connector_id=connector.id,
                )
            )
            if answer == choices[0]:
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
    at, status = statement["ordinal"] + 1, statement["status"]
    if statement.get("affected_rows") is not None:
        return say(
            "Statement {at} · {status} · {count} affected",
            at=at, status=status, count=statement["affected_rows"],
        )
    if statement.get("row_count") is not None:
        return say(
            "Statement {at} · {status} · {count} rows",
            at=at, status=status, count=statement["row_count"],
        )
    return say("Statement {at} · {status}", at=at, status=status)


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
            said = (
                say("{statement} — would succeed", statement=line)
                if outcome.affected_rows is None
                else say(
                    "{statement} — would succeed, {count} rows affected",
                    statement=line, count=outcome.affected_rows,
                )
            )
            if outcome.notices:
                said += "; " + "; ".join(note.message for note in outcome.notices)
            lines.append(said)
        elif outcome.outcome == "blocked":
            lines.append(
                say("{statement} — blocked by another transaction; nothing was learnt", statement=line)
            )
        elif outcome.outcome == "failed":
            detail = outcome.diagnostic.message if outcome.diagnostic else say("the source refused it")
            lines.append(say("{statement} — would fail: {reason}", statement=line, reason=detail))
        else:
            lines.append(say("{statement} — not reached", statement=line))
    total = len(prepared.statements)
    return ChangePreview(
        summary=(
            say("{count} statement would run", count=total)
            if total == 1
            else say("{count} statements would run", count=total)
        ),
        lines=lines,
    )


def transfer_refusal(connector: Connector, held: str) -> dict[str, Any]:
    return refusal_of(connector.id, connector.name, held)


def refusal_of(connector_id: uuid.UUID, name: str, held: str) -> dict[str, Any]:
    return {
        "error": TRANSFER_MARKER,
        "connector_id": str(connector_id),
        "connector": name,
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


def connector_ids_from_result(content: object) -> frozenset[uuid.UUID]:
    """The connections whose data one of our tool results carries.

    One for a tool that reads one connection, `connector_ids` for a search
    over several. A refusal names the connection but holds nothing of it, and
    it must reach the model as it is: withheld, the agent could not even say
    why it stopped.
    """
    if not isinstance(content, str):
        return frozenset()
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return frozenset()
    if not isinstance(value, dict) or value.get("error") == TRANSFER_MARKER:
        return frozenset()
    named = value.get("connector_ids")
    texts = [value.get("connector_id"), *(named if isinstance(named, list) else [])]
    found: set[uuid.UUID] = set()
    for text in texts:
        if not isinstance(text, str):
            continue
        try:
            found.add(uuid.UUID(text))
        except ValueError:
            continue
    return frozenset(found)


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
            and not connector_ids_from_result(message.content) <= allowed
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
        return await runtime.invoke(say("Listing connections"), read)

    async def browse_catalog(
        connector_id: str, node_id: str | None = None, offset: int = 0
    ) -> str:
        async def read(session: AsyncSession, user: User) -> Any:
            resolved = await runtime.connector(session, user, uuid.UUID(connector_id))
            if isinstance(resolved, dict):
                return resolved
            connector, adapter, _held = resolved
            if not isinstance(adapter, SupportsCatalog):
                return {"error": "This connection has no catalog"}
            nodes = await adapter.list_children(node_id)
            start = max(0, offset)
            page = nodes[start : start + MAX_NODES]
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "parent_node_id": node_id,
                "offset": start,
                "nodes": [node.model_dump(mode="json") for node in page],
                "total": len(nodes),
                "has_more": start + len(page) < len(nodes),
            }
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(say('Browsing catalog in "{connection}"', connection=label), read)

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
        return await runtime.invoke(say('Describing "{node}"', node=node_id), read)

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
        return await runtime.invoke(say('Reading rows from "{node}"', node=node_id), read)

    async def open_in_workspace(
        connector_id: str,
        node_id: str | None = None,
        title: str | None = None,
        view: NodeView = "preferred",
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
                representations=list(node.representations) if node is not None else [],
            )
            await runtime.opened(runtime.owner_id, intent)
            return {
                "opened": True,
                "connector": connector.name,
                "connector_id": str(connector.id),
                "node_id": node_id,
                "view": view,
            }
        return await runtime.invoke(
            say('Opening "{name}"', name=title or node_id or connector_id), read
        )

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
            changing: list[StatementClass] = [kind for kind in kinds if kind in CHANGING]
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
                preview = await for_person_async(
                    lambda: change_preview(adapter, prepared, request)
                )
                refused = await runtime.confirm_change(
                    session,
                    connector=connector,
                    question=for_person(
                        lambda: say(
                            'Run {count} statement that changes data on "{connection}"?',
                            count=len(changing), connection=connector.name,
                        )
                        if len(changing) == 1
                        else say(
                            'Run {count} statements that change data on "{connection}"?',
                            count=len(changing), connection=connector.name,
                        )
                    ),
                    preview=preview,
                )
                if refused is not None:
                    return {"error": refused}
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
                substeps=for_person(lambda: [statement_substep(one) for one in statements]),
            )
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(say('Running query on "{connection}"', connection=label), run)

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
                    shown = await for_person_async(
                        lambda: perform(lambda: action.preview(node_id, arguments))
                    )
                    preview = ChangePreview(summary=shown.summary, lines=shown.items)
                refused = await runtime.confirm_change(
                    session,
                    connector=connector,
                    question=for_person(
                        lambda: say(
                            'Run "{action}" on "{connection}"?',
                            action=say(action.title), connection=connector.name,
                        )
                    ),
                    preview=preview,
                )
                if refused is not None:
                    return {"error": refused}
            result = await perform(lambda: action.perform(node_id, arguments))
            await runtime.data_cache.invalidate_connector(connector.id)
            return {
                "connector": connector.name,
                "connector_id": str(connector.id),
                "action": action.name,
                "result": result.model_dump(mode="json"),
            }
        label = await runtime.connection_label(connector_id)
        return await runtime.invoke(
            say('Running action "{action}" on "{connection}"', action=action_name, connection=label),
            run,
        )

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
        return await runtime.invoke(
            say('Listing actions for "{name}"', name=node_id or connector_id), read
        )

    async def search(words: str, connector_ids: list[str] | None = None) -> str:
        async def find(session: AsyncSession, user: User) -> Any:
            if runtime.search_engine is None:
                return {"error": "Search is not available"}
            return await search_for_agent(
                runtime.search_engine,
                session,
                user,
                words=words,
                named=[uuid.UUID(one) for one in connector_ids or []],
                attached=runtime.attached,
                refusal=refusal_of,
            )
        return await runtime.invoke(say('Searching for "{words}"', words=words.strip()[:80]), find)

    async def ask_user(question: str, choices: list[str]) -> str:
        async def prepare(_session: AsyncSession, _user: User) -> Any:
            return {
                "question": question,
                "answer": await runtime.pause(
                    AgentQuestion(kind="ask_user", question=question, choices=choices)
                ),
            }
        return await runtime.invoke(say("Waiting for your answer"), prepare)

    definitions: list[tuple[Callable[..., Awaitable[str]], str, str]] = [
        (list_connections, "list_connections", "List every connection visible to the current person, including transfer policy."),
        (search, "search", f"Find tables, files, keys and other nodes by name, plus connections, guide pages and source types. Searches inside the connections of attached tabs and those named in connector_ids (at most {MAX_CONTEXT}); at most {MAX_SEARCH_HITS} hits."),
        (browse_catalog, "browse_catalog", f"List one level of a connection catalog, at most {MAX_NODES} nodes from offset. Use opaque ids exactly as returned."),
        (describe_node, "describe_node", "Describe a node's columns, constraints, indexes and summary where supported."),
        (read_rows, "read_rows", f"Read at most {MAX_ROWS} rows from one opaque node id."),
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

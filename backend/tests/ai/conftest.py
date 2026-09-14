"""What the agent tests share: a model that says what it is told to (D139).

No test here calls a provider. CI has no keys, and a real model answers
differently every time, so the runner is handed a factory whose model streams
the blocks a test scripts — reasoning and text, the shape providers stream in —
and can be held mid-answer, or fail the way a provider fails.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from pydantic import ConfigDict

from app.ai.catalog import ModelInfo
from app.ai.runner import AgentRunner
from app.core.config import settings
from app.main import app

AI = f"{settings.API_V1_STR}/ai"
MODEL_KEY = "anthropic:claude-sonnet-5"
KEY = "sk-test-not-a-real-key-7f3a"


class ProviderRefusedKey(Exception):
    """What a provider SDK raises for a key it does not accept."""


@dataclass
class Turn:
    """One call of the model: what it streams, and how it behaves while doing so."""

    pieces: list[dict[str, Any]] = field(default_factory=list)
    # Held after the first piece until set, so a test can act mid-answer.
    gate: asyncio.Event | None = None
    error: Exception | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: tuple[int, int] = (0, 0)


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value, "index": 1}


def reasoning(value: str) -> dict[str, Any]:
    return {"type": "reasoning", "reasoning": value, "index": 0}


@dataclass
class Script:
    turns: list[Turn] = field(default_factory=list)
    calls: list[list[BaseMessage]] = field(default_factory=list)
    built: list[tuple[str, str, int]] = field(default_factory=list)

    def next(self, messages: Sequence[BaseMessage]) -> Turn:
        self.calls.append(list(messages))
        if not self.turns:
            return Turn(pieces=[text("(nothing scripted)")])
        return self.turns.pop(0)


class ScriptedChatModel(BaseChatModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    script: Script

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[Any, AIMessage]:  # type: ignore[override]  # tools are accepted and ignored
        return self  # type: ignore[return-value]  # the model is the runnable

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("the runner calls the model asynchronously")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        turn = self.script.next(messages)
        if turn.error is not None:
            raise turn.error
        message = AIMessage(content=list(turn.pieces), tool_calls=turn.tool_calls)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        turn = self.script.next(messages)
        for number, piece in enumerate(turn.pieces):
            last = number == len(turn.pieces) - 1
            usage = (
                {
                    "input_tokens": turn.usage[0],
                    "output_tokens": turn.usage[1],
                    "total_tokens": sum(turn.usage),
                }
                if last and turn.error is None
                else None
            )
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=[piece], usage_metadata=usage)  # type: ignore[arg-type]  # a usage dict is what the TypedDict is
            )
            if number == 0 and turn.gate is not None:
                await turn.gate.wait()
        if turn.error is not None:
            raise turn.error


class ScriptedModels:
    """The factory handed to the runner in place of the providers'."""

    def __init__(self, script: Script) -> None:
        self.script = script

    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        self.script.built.append((model.key, api_key, max_output_tokens))
        return ScriptedChatModel(script=self.script)

    def sentence(self, model: ModelInfo, error: BaseException) -> str:
        if isinstance(error, ProviderRefusedKey):
            return "The provider refused the key"
        return "The model could not answer"


@pytest.fixture
async def script(
    # Asked for by name so the lifespan has built the runner; ruff reads a
    # dependency as an unused argument.
    client: AsyncClient,  # noqa: ARG001
) -> AsyncGenerator[Script]:
    """The runner's models, scripted for one test and put back afterwards."""
    runner = app.state.agent_runner
    assert isinstance(runner, AgentRunner)
    saved = runner.chat_models
    scripted = Script()
    runner.chat_models = ScriptedModels(scripted)
    try:
        yield scripted
    finally:
        for turn in scripted.turns:
            if turn.gate is not None:
                turn.gate.set()
        runner.chat_models = saved


async def ready_agent(client: AsyncClient, headers: dict[str, str]) -> None:
    """A key for the model's provider and the model chosen."""
    response = await client.put(f"{AI}/keys/anthropic", headers=headers, json={"key": KEY})
    assert response.status_code == 200, response.text
    response = await client.patch(
        f"{AI}/settings", headers=headers, json={"model_key": MODEL_KEY}
    )
    assert response.status_code == 200, response.text


async def new_conversation(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(f"{AI}/conversations", headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def send(
    client: AsyncClient, headers: dict[str, str], conversation_id: str, message: str
) -> dict[str, Any]:
    response = await client.post(
        f"{AI}/conversations/{conversation_id}/messages",
        headers=headers,
        json={"text": message},
    )
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


async def settled(
    client: AsyncClient, headers: dict[str, str], run_id: str, *, seconds: float = 10.0
) -> dict[str, Any]:
    """The run once it has ended, read from the route that is its authority."""
    deadline = time.monotonic() + seconds
    while True:
        response = await client.get(f"{AI}/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        if body["status"] not in ("running", "awaiting_answer"):
            return body
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} did not end: {body}")
        await asyncio.sleep(0.02)


async def running_with(
    client: AsyncClient,
    headers: dict[str, str],
    run_id: str,
    partial: str,
    *,
    seconds: float = 10.0,
) -> dict[str, Any]:
    """The run once it has written at least this much of its answer."""
    deadline = time.monotonic() + seconds
    while True:
        body = (await client.get(f"{AI}/runs/{run_id}", headers=headers)).json()
        if (body.get("partial_answer") or "").startswith(partial):
            return dict(body)
        if time.monotonic() > deadline:
            raise AssertionError(f"run {run_id} never wrote {partial!r}: {body}")
        await asyncio.sleep(0.02)


async def user_id_of(client: AsyncClient, headers: dict[str, str]) -> uuid.UUID:
    response = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])

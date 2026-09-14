"""Anthropic's Claude."""

from typing import Any

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from app.ai.catalog import ModelInfo
from app.ai.providers.failures import FailureKind, by_status

# Haiku 4.5 still takes a thinking budget; every later model thinks adaptively
# and refuses a budget with 400.
_BUDGETED = ("claude-haiku-4-5",)
_BUDGET_TOKENS = 4096


class AnthropicModels:
    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        return ChatAnthropic(
            model_name=model.id,
            api_key=SecretStr(api_key),
            max_tokens_to_sample=max_output_tokens,
            thinking=_thinking(model, max_output_tokens),
            output_version="v1",
            # Stated because the aliased fields read as required to mypy; the
            # run's own timeout bounds an answer (D137).
            timeout=None,
            stop=None,
        )

    def failure(self, error: BaseException) -> FailureKind | None:
        if isinstance(error, anthropic.APIStatusError):
            return by_status(error.status_code)
        if isinstance(error, anthropic.APIConnectionError):
            return "unavailable"
        return None


def _thinking(model: ModelInfo, max_output_tokens: int) -> dict[str, Any] | None:
    if not model.reasoning:
        return None
    if model.id.startswith(_BUDGETED):
        return {"type": "enabled", "budget_tokens": min(_BUDGET_TOKENS, max_output_tokens - 1)}
    # Summarized, because the default shows nothing and the Thinking step
    # would stay empty (D137).
    return {"type": "adaptive", "display": "summarized"}

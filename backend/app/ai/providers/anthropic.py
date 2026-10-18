"""Anthropic's Claude."""

from typing import Any

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from app.ai.catalog import ModelInfo
from app.ai.providers.failures import FailureKind, from_parts


class AnthropicModels:
    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        return ChatAnthropic(
            model_name=model.id,
            api_key=SecretStr(api_key),
            max_tokens_to_sample=max_output_tokens,
            thinking=_thinking(model),
            output_version="v1",
            # Stated because the aliased fields read as required to mypy; the
            # run's own timeout bounds an answer (D137).
            timeout=None,
            stop=None,
        )

    def failure(self, error: BaseException) -> FailureKind | None:
        if isinstance(error, anthropic.APIStatusError):
            return from_parts(
                getattr(error, "status_code", None), getattr(error, "body", None)
            )
        if isinstance(error, anthropic.APIConnectionError):
            return "unavailable"
        return None


def _thinking(model: ModelInfo) -> dict[str, Any] | None:
    if not model.reasoning:
        return None
    # Adaptive: every model in the catalog refuses a fixed budget with 400.
    # Summarized, because the default shows nothing and the Thinking step
    # would stay empty (D137).
    return {"type": "adaptive", "display": "summarized"}

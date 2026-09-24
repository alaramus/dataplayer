"""Turning a catalog entry and a key into a chat model, one module per provider.

Each provider's SDK is imported by its own module and nowhere else (D139), so
an upgrade of one has one place to change. A provider also says what its own
errors mean: the text of a provider's exception is never passed on, because it
may carry the request it failed on (D2c).
"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from app.ai.catalog import ChatProvider, ModelInfo
from app.ai.providers.anthropic import AnthropicModels
from app.ai.providers.deepseek import DeepSeekModels
from app.ai.providers.failures import SENTENCES, UNKNOWN_FAILURE, FailureKind
from app.ai.providers.gemini import GeminiModels
from app.ai.providers.openai import OpenAIModels


class ProviderModels(Protocol):
    """What one provider module offers."""

    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel: ...

    def failure(self, error: BaseException) -> FailureKind | None: ...


class ChatModels(Protocol):
    """The factory the runner is handed, so a test can hand it another."""

    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel: ...

    def sentence(self, model: ModelInfo, error: BaseException) -> str: ...


_BY_PROVIDER: dict[ChatProvider, ProviderModels] = {
    "openai": OpenAIModels(),
    "anthropic": AnthropicModels(),
    "gemini": GeminiModels(),
    "deepseek": DeepSeekModels(),
}


class ProviderChatModels:
    """The real factory: the catalog's provider picks the module."""

    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        return _BY_PROVIDER[model.provider].build(
            model, api_key, max_output_tokens=max_output_tokens
        )

    def sentence(self, model: ModelInfo, error: BaseException) -> str:
        kind = _BY_PROVIDER[model.provider].failure(error)
        return UNKNOWN_FAILURE if kind is None else SENTENCES[kind]

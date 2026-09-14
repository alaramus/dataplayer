"""DeepSeek, whose API and errors are OpenAI's shape."""

import openai
from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr

from app.ai.catalog import ModelInfo
from app.ai.providers.failures import FailureKind, by_status


class DeepSeekModels:
    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        # `reasoning_content` must go back to DeepSeek inside a tool loop; the
        # integration keeps it on the message, which the checkpointer stores.
        return ChatDeepSeek(
            model=model.id,
            api_key=SecretStr(api_key),
            max_tokens=max_output_tokens,
            output_version="v1",
        )

    def failure(self, error: BaseException) -> FailureKind | None:
        if isinstance(error, openai.APIStatusError):
            return by_status(error.status_code)
        if isinstance(error, openai.APIConnectionError):
            return "unavailable"
        return None

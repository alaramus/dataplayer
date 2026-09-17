"""OpenAI, through the Responses API."""

import openai
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.ai.catalog import ModelInfo
from app.ai.providers.failures import FailureKind, from_parts


class OpenAIModels:
    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        # Reasoning items travel back encrypted inside a tool loop, since
        # nothing is stored at OpenAI; dropping them fails the next call (D140).
        return ChatOpenAI(
            model=model.id,
            api_key=SecretStr(api_key),
            max_completion_tokens=max_output_tokens,
            use_responses_api=True,
            store=False,
            include=["reasoning.encrypted_content"],
            reasoning={"summary": "auto"} if model.reasoning else None,
            output_version="v1",
        )

    def failure(self, error: BaseException) -> FailureKind | None:
        if isinstance(error, openai.APIStatusError):
            return from_parts(
                error.status_code, getattr(error, "body", None), getattr(error, "message", None)
            )
        if isinstance(error, openai.APIConnectionError):
            return "unavailable"
        return None

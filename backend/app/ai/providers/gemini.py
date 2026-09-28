"""Google's Gemini."""

from google.genai import errors
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from app.ai.catalog import ModelInfo
from app.ai.providers.failures import FailureKind, from_parts


class GeminiModels:
    def build(
        self, model: ModelInfo, api_key: str, *, max_output_tokens: int
    ) -> BaseChatModel:
        # Thought summaries only arrive when asked for; thought signatures go
        # back inside a tool loop through the message the checkpointer stores.
        return ChatGoogleGenerativeAI(
            model=model.id,
            google_api_key=SecretStr(api_key),
            max_output_tokens=max_output_tokens,
            include_thoughts=model.reasoning,
            output_version="v1",
        )

    def failure(self, error: BaseException) -> FailureKind | None:
        # LangChain re-raises a 4xx as an error of its own that carries only a
        # sentence; the SDK's error, with the status and the body, is its cause.
        # Read at the surface, a spent free-tier quota said "could not answer".
        seen: BaseException | None = error
        while seen is not None:
            if isinstance(seen, errors.APIError):
                return from_parts(
                    getattr(seen, "code", None),
                    getattr(seen, "details", None),
                    getattr(seen, "message", None),
                )
            seen = seen.__cause__
        return None

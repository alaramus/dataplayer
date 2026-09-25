"""Choose one catalog model within the person's provider (D157)."""

import asyncio
import logging
from dataclasses import dataclass

from langchain_typesafe import Choice, TypeSafeClassifier
from pydantic import JsonValue

from app.ai.catalog import ChatProvider, ModelCatalog, ModelInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelRoute:
    model: ModelInfo
    note: str


async def choose(
    *,
    catalog: ModelCatalog,
    provider: ChatProvider,
    fallback: ModelInfo,
    text: str,
    needs_images: bool,
    jev_key: str | None,
) -> ModelRoute:
    candidates = [
        model for model in catalog.models
        if model.provider == provider and (model.image_input or not needs_images)
    ]
    if not candidates:
        raise ValueError("No model in this provider can read the attached image")
    safe_fallback = fallback if fallback in candidates else candidates[0]
    if jev_key is None:
        return ModelRoute(safe_fallback, "Jev unavailable; using fallback")
    if len(candidates) == 1:
        return ModelRoute(candidates[0], "Only compatible model in this provider")
    criteria: dict[str, JsonValue] = {
        model.key: (
            f"{model.name}; context window {model.context_window} tokens; "
            f"maximum output {model.max_output_tokens} tokens; "
            f"reasoning {'supported' if model.reasoning else 'not supported'}; "
            f"images {'supported' if model.image_input else 'not supported'}"
        )
        for model in candidates
    }
    try:
        async with asyncio.timeout(10):
            result = await TypeSafeClassifier(api_key=jev_key).ainvoke(
                {
                    "state": {
                        "latest_user_request": text[:16000] or "[image-only request]",
                        "provider": provider,
                        "contains_images": needs_images,
                    },
                    "questions": {
                        "model": Choice(
                            instructions=(
                                "Choose the model best suited to answer this request. "
                                "Use the listed capabilities and context windows. "
                                "Choose only from the offered models."
                            ),
                            criteria=criteria,
                        )
                    },
                }
            )
        selected = result.choices["model"].choice
        match = next((model for model in candidates if model.key == selected), None)
        if match is not None:
            return ModelRoute(match, "Jev selected this model")
    except Exception as error:  # noqa: BLE001 - provider text may contain request data
        logger.info("Jev model routing failed: %s", type(error).__name__)
    return ModelRoute(safe_fallback, "Jev unavailable; using fallback")

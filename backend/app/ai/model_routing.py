"""Choose one catalog model among the person's keyed providers (D157)."""

import asyncio
import logging
from collections.abc import Sequence
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
    providers: Sequence[ChatProvider],
    fallback: ModelInfo,
    text: str,
    needs_images: bool,
    jev_key: str | None,
) -> ModelRoute:
    candidates = [
        model for model in catalog.models
        if model.provider in providers and (model.image_input or not needs_images)
    ]
    if not candidates:
        if needs_images:
            raise ValueError("No model with a configured key can read the attached image")
        raise ValueError("No model with a configured key is available")
    safe_fallback = fallback if fallback in candidates else candidates[0]
    if jev_key is None:
        return ModelRoute(safe_fallback, "Jev unavailable; using fallback")
    if len(candidates) == 1:
        return ModelRoute(candidates[0], "Only one compatible model available")
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
                        "providers": sorted(providers),
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

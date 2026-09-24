"""Provider-scoped Jev routing and its fallback (D157)."""

from types import SimpleNamespace
from typing import Any

import pytest

from app.ai import model_routing
from app.ai.catalog import catalog


async def test_jev_can_choose_any_compatible_model_in_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = catalog()
    fallback = next(model for model in models.models if model.key == "openai:gpt-5.6-sol")
    target = next(model for model in models.models if model.key == "openai:gpt-5.6-luna")

    class FakeClassifier:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "jev-key"

        async def ainvoke(self, request: dict[str, Any]) -> Any:
            choices = request["questions"]["model"].criteria
            assert set(choices) == {
                model.key for model in models.models
                if model.provider == "openai" and model.image_input
            }
            assert request["state"]["latest_user_request"] == "Explain this image"
            return SimpleNamespace(choices={"model": SimpleNamespace(choice=target.key)})

    monkeypatch.setattr(model_routing, "TypeSafeClassifier", FakeClassifier)
    route = await model_routing.choose(
        catalog=models, provider="openai", fallback=fallback,
        text="Explain this image", needs_images=True, jev_key="jev-key",
    )
    assert route.model == target
    assert route.note == "Jev selected this model"


async def test_jev_failure_keeps_the_previously_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = catalog()
    fallback = next(model for model in models.models if model.key == "openai:gpt-5.6-sol")

    class FailingClassifier:
        def __init__(self, *, api_key: str) -> None:
            pass

        async def ainvoke(self, request: dict[str, Any]) -> Any:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(model_routing, "TypeSafeClassifier", FailingClassifier)
    route = await model_routing.choose(
        catalog=models, provider="openai", fallback=fallback,
        text="Answer this", needs_images=False, jev_key="jev-key",
    )
    assert route.model == fallback
    assert route.note == "Jev unavailable; using fallback"

    without_key = await model_routing.choose(
        catalog=models, provider="openai", fallback=fallback,
        text="Answer this", needs_images=False, jev_key=None,
    )
    assert without_key.model == fallback

    incompatible = next(model for model in models.models if model.key == "openai:gpt-5.4-nano-2026-03-17")
    with_image = await model_routing.choose(
        catalog=models, provider="openai", fallback=incompatible,
        text="Describe this", needs_images=True, jev_key=None,
    )
    assert with_image.model.image_input
    assert with_image.model.provider == "openai"

"""The model list is a file checked strictly, so a typo fails here (D140)."""

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from app.ai.catalog import CATALOG_FILE, PROVIDER_TITLES, Provider, catalog, read

ENTRY: dict[str, Any] = {
    "provider": "openai",
    "id": "gpt-test",
    "name": "GPT test",
    "context_window": 400000,
    "max_output_tokens": 128000,
    "reasoning": True,
    "image_input": False,
}


def _write(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_every_provider_is_named() -> None:
    """A provider without a name would reach the screen as its bare id."""
    assert set(PROVIDER_TITLES) == set(get_args(Provider))


def test_the_shipped_list_is_valid_and_covers_every_provider() -> None:
    shipped = read(CATALOG_FILE)

    assert {model.provider for model in shipped.models} == {
        "openai",
        "anthropic",
        "deepseek",
        "gemini",
    }
    assert catalog().find("anthropic:claude-sonnet-5") is not None


@pytest.mark.parametrize(
    "broken",
    [
        {**ENTRY, "provider": "mistral"},
        {**ENTRY, "context_windows": 1},
        {**ENTRY, "context_window": 0},
        {key: value for key, value in ENTRY.items() if key != "reasoning"},
    ],
)
def test_an_entry_it_does_not_accept_stops_the_read(
    tmp_path: Path, broken: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        read(_write(tmp_path, [ENTRY | {"id": "gpt-ok"}, broken]))


def test_the_same_model_twice_stops_the_read(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="listed twice"):
        read(_write(tmp_path, [ENTRY, ENTRY]))


def test_two_providers_may_name_a_model_alike(tmp_path: Path) -> None:
    listed = read(_write(tmp_path, [ENTRY, ENTRY | {"provider": "deepseek"}]))

    assert {model.key for model in listed.models} == {"openai:gpt-test", "deepseek:gpt-test"}


def test_a_choice_the_list_dropped_is_no_model(tmp_path: Path) -> None:
    listed = read(_write(tmp_path, [ENTRY]))

    assert listed.find("openai:gpt-test") is not None
    assert listed.find("openai:gpt-gone") is None
    assert listed.find(None) is None

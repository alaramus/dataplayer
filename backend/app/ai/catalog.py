"""The models the agent may use, read from one file and checked strictly (D140).

The list changes with a release and nowhere else: `models.json` beside this
module is the whole of it. A file that does not validate stops the server from
starting, and a test reads it in CI, so a typo is found before anybody opens the
settings.
"""

from functools import cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

Provider = Literal["openai", "anthropic", "deepseek", "gemini"]

PROVIDERS: tuple[Provider, ...] = ("openai", "anthropic", "deepseek", "gemini")

CATALOG_FILE = Path(__file__).with_name("models.json")


class ModelInfo(BaseModel):
    """One model, and what the agent needs to know about it before calling it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    # Tokens in and out. The window decides when a conversation is summarised
    # (AI6); the output ceiling bounds one answer together with the setting.
    context_window: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    reasoning: bool
    image_input: bool

    @property
    def key(self) -> str:
        """The model as a preference stores it: two providers may share an id."""
        return f"{self.provider}:{self.id}"


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[ModelInfo, ...]

    @model_validator(mode="after")
    def _one_entry_per_model(self) -> ModelCatalog:
        seen: set[str] = set()
        for model in self.models:
            if model.key in seen:
                raise ValueError(f"{model.key} is listed twice")
            seen.add(model.key)
        return self

    def find(self, key: str | None) -> ModelInfo | None:
        """The model a stored choice names, or nothing if the file dropped it."""
        return next((model for model in self.models if model.key == key), None)


_ENTRIES: TypeAdapter[list[ModelInfo]] = TypeAdapter(list[ModelInfo])


def read(path: Path = CATALOG_FILE) -> ModelCatalog:
    """Read and validate a catalog file. Raises on anything it does not accept."""
    entries = _ENTRIES.validate_json(path.read_bytes())
    return ModelCatalog(models=tuple(entries))


@cache
def catalog() -> ModelCatalog:
    """The catalog this build shipped with, read once per process."""
    return read()

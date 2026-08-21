from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr

from app.adapters.protocol import DataAdapter
from app.adapters.resources import Pooling


class UnknownAdapterType(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown adapter type: {name}")
        self.name = name


@dataclass(frozen=True)
class AdapterContext:
    """What the server supplies and the client must not name.

    Handed to every driver at construction, and every driver takes only what
    it needs: a file source cannot exist without a root, and letting that root
    travel in the options would put it into the connector form and into stored
    configuration; PostgreSQL ignores the root and uses the pooling instead.
    """

    home_dir: Path
    # Absent for a draft: it has no identity to key long-lived things by, and
    # a check is meant to exercise credentials rather than reuse a connection.
    pooling: Pooling | None = None


Factory = Callable[[Any, AdapterContext], DataAdapter]


@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    options_schema: type[BaseModel]
    factory: Factory

_registry: dict[str, AdapterType] = {}


def register(
    *, name: str, title: str, options_schema: type[BaseModel]
) -> Callable[[Factory], Factory]:
    """Register a source type. Applied to the driver factory."""

    def decorator(factory: Factory) -> Factory:
        if name in _registry:
            raise ValueError(f"Adapter type already registered: {name}")
        _registry[name] = AdapterType(
            name=name, title=title, options_schema=options_schema, factory=factory
        )
        return factory

    return decorator


def get(name: str) -> AdapterType:
    try:
        return _registry[name]
    except KeyError:
        raise UnknownAdapterType(name) from None


def all_types() -> list[AdapterType]:
    return sorted(_registry.values(), key=lambda t: t.title)


def secret_field_names(schema: type[BaseModel]) -> set[str]:
    """Names of schema fields declared as SecretStr.

    The single source of truth about which values are encrypted: there is no
    separate list of secret fields, so a field cannot be left out by mistake.
    """
    return {
        name
        for name, field in schema.model_fields.items()
        if field.annotation is SecretStr
    }

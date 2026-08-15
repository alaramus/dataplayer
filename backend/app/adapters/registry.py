from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, SecretStr

from app.adapters.protocol import DataAdapter


class UnknownAdapterType(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown adapter type: {name}")
        self.name = name


@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    options_schema: type[BaseModel]
    factory: Callable[[Any], DataAdapter]


Factory = Callable[[Any], DataAdapter]

_registry: dict[str, AdapterType] = {}


def register(
    *, name: str, title: str, options_schema: type[BaseModel]
) -> Callable[[Factory], Factory]:
    """Зарегистрировать тип источника. Применяется к фабрике драйвера."""

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
    """Имена полей схемы, объявленных как SecretStr.

    Единственный источник истины о том, какие значения подлежат шифрованию:
    отдельного списка секретных полей не существует, поэтому пометить поле
    и забыть — невозможно.
    """
    return {
        name
        for name, field in schema.model_fields.items()
        if field.annotation is SecretStr
    }

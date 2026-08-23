from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, SecretStr

from app.adapters.actions import DeclaresActions
from app.adapters.protocol import DataAdapter, SupportsCatalog, SupportsFetch
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

# What kind of thing a source is, for the one screen that groups them. A
# closed set rather than a free string: a category is a set of values, so a
# typo has to fail to compile instead of quietly creating a group of one.
Category = Literal["sql", "files"]

# The wording lives beside the set it names, on the server, so the client is
# never a second place where a category is called something.
_CATEGORY_TITLES: dict[Category, str] = {
    "sql": "SQL Databases",
    "files": "Files & Storage",
}


def category_title(category: Category) -> str:
    return _CATEGORY_TITLES[category]


# What sort of statement a capability makes: what can be looked at, and what
# can be changed. Two rather than the old application's ten, because two is
# what the derivation below can honestly tell apart.
CapabilityGroup = Literal["explore", "manage"]


class Capability(BaseModel):
    """One thing a source type can do, in words a user reads.

    A model rather than a tuple because it crosses the API boundary.
    """

    group: CapabilityGroup
    title: str


@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    category: Category
    description: str
    options_schema: type[BaseModel]
    # The driver class, kept beside the factory that builds instances of it.
    # Capabilities are a question about the type — no connector exists yet, so
    # there are no options and no session to build an instance from.
    adapter_class: type[DataAdapter]
    factory: Factory

_registry: dict[str, AdapterType] = {}


def register(
    *,
    name: str,
    title: str,
    category: Category,
    description: str,
    options_schema: type[BaseModel],
    adapter_class: type[DataAdapter],
) -> Callable[[Factory], Factory]:
    """Register a source type. Applied to the driver factory.

    Every argument is required: a type that did not say what it is would reach
    the catalog as a nameless tile, and the one place that could have said so
    is this call.
    """

    def decorator(factory: Factory) -> Factory:
        if name in _registry:
            raise ValueError(f"Adapter type already registered: {name}")
        _registry[name] = AdapterType(
            name=name,
            title=title,
            category=category,
            description=description,
            options_schema=options_schema,
            adapter_class=adapter_class,
            factory=factory,
        )
        return factory

    return decorator


def capabilities_of(adapter_type: AdapterType) -> list[Capability]:
    """What a source type can do, read off the driver rather than listed.

    There is no table of capabilities to keep in step: a driver that stops
    implementing `list_children` stops claiming to browse in the same commit,
    and the titles of its actions come from the very classes that will be
    dispatched. The old application kept 105 capability names by hand on the
    client and said so in its own README, at the cost it names there.

    `issubclass` rather than `isinstance` because the question is about the
    type. All three protocols hold methods only, which is what makes the class
    check legal at all.
    """
    driver = adapter_type.adapter_class
    found: list[Capability] = []

    if issubclass(driver, SupportsCatalog):
        found.append(Capability(group="explore", title="Browse the catalog"))
    if issubclass(driver, SupportsFetch):
        found.append(Capability(group="explore", title="Read rows"))
    if issubclass(driver, DeclaresActions):
        found.extend(
            Capability(group="manage", title=action_type.title)
            for action_type in driver.action_types()
        )

    return found


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

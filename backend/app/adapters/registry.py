from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.adapters.actions import DeclaresActions
from app.adapters.cache import SourceCacheWindows, SupportsReadCache
from app.adapters.options import OptionsSchema
from app.adapters.protocol import (
    DataAdapter,
    SearchesContents,
    SupportsAddColumn,
    SupportsBackup,
    SupportsCatalog,
    SupportsContent,
    SupportsContentEdit,
    SupportsCreateRelation,
    SupportsDelete,
    SupportsDropColumn,
    SupportsExport,
    SupportsFetch,
    SupportsInsert,
    SupportsNodePath,
    SupportsNodeSearch,
    SupportsReferences,
    SupportsRelationModel,
    SupportsUpdate,
)
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
Category = Literal["sql", "keyvalue", "files"]

# The wording lives beside the set it names, on the server, so the client is
# never a second place where a category is called something.
_CATEGORY_TITLES: dict[Category, str] = {
    "sql": "SQL Databases",
    "keyvalue": "Key-Value Stores",
    "files": "Files & Storage",
}


def category_title(category: Category) -> str:
    return _CATEGORY_TITLES[category]


# How a source's catalog is best shown. Not a decoration: a catalog walked one
# level at a time and a catalog expanded in place are different screens, and
# which one a source wants is a property of the source rather than of the
# screen. PostgreSQL has thousands of relations under a schema and is walked;
# a Redis key space is bounded and its leaves hold structure, so it is a tree
# that opens where you are.
#
# A closed set, so a screen switching on it cannot meet a value it has no
# panel for, and read off the type rather than branched on by name — a screen
# that said `if adapterType === "redis"` would be the old application (D62).
CatalogShape = Literal["levels", "tree"]

# What sort of statement a capability makes: what can be looked at, and what
# can be changed. Two rather than the old application's ten, because two is
# what the derivation below can honestly tell apart.
CapabilityGroup = Literal["explore", "manage"]


# What a screen may switch on. A title is written to be read and may be
# reworded tomorrow; a code is a promise. Only what a screen has actually had
# to ask about carries one, so this grows when a question is asked rather than
# in advance — and everything else stays what it is, something to read.
CapabilityCode = Literal["search", "content_search", "create_relation", "backup"]


class Capability(BaseModel):
    """One thing a source type can do, in words a user reads.

    A model rather than a tuple because it crosses the API boundary.
    """

    group: CapabilityGroup
    title: str
    code: CapabilityCode | None = None


@dataclass(frozen=True)
class AdapterType:
    name: str
    title: str
    category: Category
    description: str
    catalog_shape: CatalogShape
    # A model, or a discriminated union of them when the fields depend on
    # the way the source is connected to. Everything that reads it goes
    # through `app.adapters.options`, which answers for both.
    options_schema: OptionsSchema
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
    options_schema: OptionsSchema,
    adapter_class: type[DataAdapter],
    catalog_shape: CatalogShape = "levels",
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
            catalog_shape=catalog_shape,
            options_schema=options_schema,
            adapter_class=adapter_class,
            factory=factory,
        )
        return factory

    return decorator


def cache_windows_of(adapter_type: AdapterType) -> SourceCacheWindows | None:
    """What this kind of source keeps its answers for, or nothing if it keeps none.

    Read off the driver rather than listed, like the capabilities below: a
    source that stops opting into caching stops claiming a window in the same
    commit. Nothing at all is the honest answer for a source that never opted
    in — no window its owner types would change anything about it (D105).
    """
    driver = adapter_type.adapter_class
    if not issubclass(driver, SupportsReadCache):
        return None
    return SourceCacheWindows(
        catalog=driver.cache_ttl("catalog"), fetch=driver.cache_ttl("fetch")
    )


def capabilities_of(adapter_type: AdapterType) -> list[Capability]:
    """What a source type can do, read off the driver rather than listed.

    There is no table of capabilities to keep in step: a driver that stops
    implementing `list_children` stops claiming to browse in the same commit,
    and the titles of its actions come from the very classes that will be
    dispatched. The old application kept 105 capability names by hand on the
    client and said so in its own README, at the cost it names there.

    `issubclass` rather than `isinstance` because the question is about the
    type. These protocols hold methods only, which is what makes the class
    check legal at all.
    """
    driver = adapter_type.adapter_class
    found: list[Capability] = []

    if issubclass(driver, SupportsCatalog):
        found.append(Capability(group="explore", title="Browse the catalog"))
    if issubclass(driver, SupportsNodePath):
        found.append(Capability(group="explore", title="Locate a node"))
    if issubclass(driver, SupportsNodeSearch):
        found.append(
            Capability(group="explore", title="Search by name", code="search")
        )
    if issubclass(driver, SearchesContents):
        found.append(
            Capability(
                group="explore",
                title="Search inside files",
                code="content_search",
            )
        )
    if issubclass(driver, SupportsContent):
        found.append(Capability(group="explore", title="View content"))
    if issubclass(driver, SupportsContentEdit):
        found.append(Capability(group="manage", title="Edit content"))
    if issubclass(driver, SupportsFetch):
        found.append(Capability(group="explore", title="Read rows"))
    if issubclass(driver, SupportsExport):
        found.append(Capability(group="explore", title="Export all matching rows"))
    if issubclass(driver, SupportsRelationModel):
        found.append(Capability(group="explore", title="Describe a relation"))
    if issubclass(driver, SupportsReferences):
        found.append(Capability(group="explore", title="Follow references"))
    if issubclass(driver, SupportsAddColumn):
        found.append(Capability(group="manage", title="Add columns"))
    if issubclass(driver, SupportsDropColumn):
        found.append(Capability(group="manage", title="Drop columns"))
    if issubclass(driver, SupportsUpdate):
        found.append(Capability(group="manage", title="Edit rows"))
    if issubclass(driver, SupportsInsert):
        found.append(Capability(group="manage", title="Insert rows"))
    if issubclass(driver, SupportsDelete):
        found.append(Capability(group="manage", title="Delete rows"))
    if issubclass(driver, SupportsCreateRelation):
        found.append(
            Capability(
                group="manage",
                title="Create a relation from rows",
                code="create_relation",
            )
        )
    if issubclass(driver, SupportsBackup):
        found.append(
            Capability(
                group="manage",
                title="Copy the whole database out",
                code="backup",
            )
        )
    if issubclass(driver, DeclaresActions):
        found.extend(
            Capability(
                group="explore" if action_type.requires == "read" else "manage",
                title=action_type.title,
            )
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

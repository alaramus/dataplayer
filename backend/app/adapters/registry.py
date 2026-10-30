from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from app.adapters.actions import DeclaresActions
from app.adapters.cache import SourceCacheWindows, SupportsReadCache
from app.adapters.credentials import KeyAccess
from app.adapters.features import FEATURE_TITLES
from app.adapters.metrics import SupportsMetrics
from app.adapters.options import OptionsSchema
from app.adapters.protocol import (
    DataAdapter,
    SearchesContents,
    SupportsAddColumn,
    SupportsArrivingReferences,
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
from app.adapters.terminal import SupportsConsoleProgram, SupportsTerminal
from app.adapters.tunnels import TunnelAccess
from app.core.translation import N_, say


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
    # The owner's stored keys, for a source that signs in with one (D146).
    # Absent where nothing could sign in with a key, and a driver that needs
    # one then refuses rather than guessing.
    keys: KeyAccess | None = None
    # The owner's SSH connections, for a database reached through one (D282).
    tunnels: TunnelAccess | None = None


Factory = Callable[[Any, AdapterContext], DataAdapter]

# What kind of thing a source is, for the one screen that groups them. A
# closed set rather than a free string: a category is a set of values, so a
# typo has to fail to compile instead of quietly creating a group of one.
Category = Literal["sql", "document", "keyvalue", "files"]

# The wording lives beside the set it names, on the server, so the client is
# never a second place where a category is called something.
CATEGORY_TITLES: dict[Category, str] = {
    "sql": N_("SQL Databases"),
    "document": N_("Document Databases"),
    "keyvalue": N_("Key-Value Stores"),
    "files": N_("Files & Storage"),
}


def category_title(category: Category) -> str:
    return CATEGORY_TITLES[category]


# How a source's catalog is best shown. Not a decoration: a catalog walked one
# level at a time and a catalog expanded in place are different screens, and
# which one a source wants is a property of the source rather than of the
# screen. PostgreSQL has thousands of relations under a schema and is walked;
# a Redis key space is bounded and its leaves hold structure, so it is a tree
# that opens where you are.
#
# A closed set, so a screen switching on it cannot meet a value it has no
# panel for, and read off the type rather than branched on by name — no
# screen says `if adapterType === "redis"` (D62).
CatalogShape = Literal["levels", "tree"]

# What sort of statement a capability makes: what can be looked at, and what
# can be changed. Two rather than a finer taxonomy, because two is what the
# derivation below can honestly tell apart.
CapabilityGroup = Literal["explore", "manage"]


# What a screen may switch on. A title is written to be read and may be
# reworded tomorrow; a code is a promise. Only what a screen has actually had
# to ask about carries one, so this grows when a question is asked rather than
# in advance — and everything else stays what it is, something to read.
CapabilityCode = Literal[
    "search",
    "content_search",
    "relation_model",
    "create_relation",
    "backup",
    "metrics",
    "terminal",
    "declared_references",
    "relationship_graph",
]


class Capability(BaseModel):
    """One thing a source type can do, in words a user reads.

    A model rather than a tuple because it crosses the API boundary.
    """

    group: CapabilityGroup
    title: str
    code: CapabilityCode | None = None


@dataclass(frozen=True)
class CatalogFace:
    """One card a source type shows in the catalog of types (D264).

    A type that speaks to several products, the way `mysql` speaks to MySQL
    and MariaDB, shows a card for each, so a person finds the product they
    run rather than the type's name for it. Every card is the one type: one
    form, one driver, and the server says which it is.
    """

    # Names the card, and its picture in the client.
    key: str
    title: str
    # The services this card offers to start, by template key.
    templates: tuple[str, ...] = ()


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
    # Empty for a type that is one product: it is its own card.
    faces: tuple[CatalogFace, ...] = ()


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
    faces: tuple[CatalogFace, ...] = (),
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
            faces=faces,
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


def searches_its_catalog(driver: type) -> bool:
    """Whether a catalog of this type offers a search of its own (D76).

    Searching by name is not enough: a found row has to be placed. A list
    places it by walking to its level, which takes a node path; a tree (D91)
    places it by the ancestors each match carries, and a node path is what
    D195 withheld from Redis.
    """
    # Asked before `issubclass` narrows the driver past what the registry holds.
    tree = any(
        one.adapter_class is driver and one.catalog_shape == "tree"
        for one in _registry.values()
    )
    return issubclass(driver, SupportsNodeSearch) and (
        tree or issubclass(driver, SupportsNodePath)
    )


def capabilities_of(adapter_type: AdapterType) -> list[Capability]:
    """What a source type can do, read off the driver rather than listed.

    There is no table of capabilities to keep in step: a driver that stops
    implementing `list_children` stops claiming to browse in the same commit,
    and the titles of its actions come from the very classes that will be
    dispatched. A hand-kept list of capabilities drifts from the drivers;
    deriving them cannot.

    `issubclass` rather than `isinstance` because the question is about the
    type. These protocols hold methods only, which is what makes the class
    check legal at all.
    """
    driver = adapter_type.adapter_class
    found: list[Capability] = []

    if issubclass(driver, SupportsCatalog):
        found.append(Capability(group="explore", title=say("Browse the catalog")))
    if issubclass(driver, SupportsNodePath):
        found.append(Capability(group="explore", title=say("Locate a node")))
    if searches_its_catalog(driver):
        found.append(
            Capability(group="explore", title=say("Search by name"), code="search")
        )
    if issubclass(driver, SearchesContents):
        found.append(
            Capability(
                group="explore",
                title=say("Search inside files"),
                code="content_search",
            )
        )
    if issubclass(driver, SupportsContent):
        found.append(Capability(group="explore", title=say("View content")))
    if issubclass(driver, SupportsContentEdit):
        found.append(Capability(group="manage", title=say("Edit content")))
    if issubclass(driver, SupportsFetch):
        found.append(Capability(group="explore", title=say("Read rows")))
        if issubclass(driver, SupportsNodePath):
            found.append(
                Capability(
                    group="explore",
                    title=say("Declared references"),
                    code="declared_references",
                )
            )
    if issubclass(driver, SupportsExport):
        found.append(Capability(group="explore", title=say("Export all matching rows")))
    if issubclass(driver, SupportsRelationModel):
        found.append(
            Capability(
                group="explore",
                title=say("Describe a relation"),
                code="relation_model",
            )
        )
        if issubclass(driver, SupportsNodePath):
            found.append(
                Capability(
                    group="explore",
                    title=say("Draw relationships"),
                    code="relationship_graph",
                )
            )
    if issubclass(driver, SupportsReferences):
        found.append(Capability(group="explore", title=say("Follow references")))
    if issubclass(driver, SupportsArrivingReferences):
        found.append(Capability(group="explore", title=say("Find what points here")))
    if issubclass(driver, SupportsAddColumn):
        found.append(Capability(group="manage", title=say("Add columns")))
    if issubclass(driver, SupportsDropColumn):
        found.append(Capability(group="manage", title=say("Drop columns")))
    if issubclass(driver, SupportsUpdate):
        found.append(Capability(group="manage", title=say("Edit rows")))
    if issubclass(driver, SupportsInsert):
        found.append(Capability(group="manage", title=say("Insert rows")))
    if issubclass(driver, SupportsDelete):
        found.append(Capability(group="manage", title=say("Delete rows")))
    if issubclass(driver, SupportsCreateRelation):
        found.append(
            Capability(
                group="manage",
                title=say("Create a relation from rows"),
                code="create_relation",
            )
        )
    if issubclass(driver, SupportsMetrics):
        found.append(
            Capability(
                group="explore",
                title=say("Report its own metrics to dashboards"),
                code="metrics",
            )
        )
    if issubclass(driver, SupportsBackup):
        found.append(
            Capability(
                group="manage",
                title=say("Copy the whole database out"),
                code="backup",
            )
        )
    # A shell and a client program in a container are one thing to a screen.
    if issubclass(driver, SupportsTerminal) or issubclass(driver, SupportsConsoleProgram):
        found.append(
            Capability(group="manage", title=say("Open a terminal"), code="terminal")
        )
    if issubclass(driver, DeclaresActions):
        for action_type in driver.action_types():
            title = say(action_type.title)
            required = action_type.feature_requirements
            if len(required) == 1:
                title = say(
                    "{action} (when {feature} is installed)",
                    action=title,
                    feature=FEATURE_TITLES[required[0]],
                )
            elif required:
                title = say(
                    "{action} (when {features} are installed)",
                    action=title,
                    features=", ".join(FEATURE_TITLES[code] for code in required),
                )
            found.append(
                Capability(
                    group="explore" if action_type.requires == "read" else "manage",
                    title=title,
                )
            )

    return found


def get(name: str) -> AdapterType:
    try:
        return _registry[name]
    except KeyError:
        raise UnknownAdapterType(name) from None


def all_types() -> list[AdapterType]:
    return sorted(_registry.values(), key=lambda t: t.title)

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, SecretStr

from app.adapters import registry
from app.adapters.actions import Action, ActionResult, JsonAction
from app.adapters.catalog import CatalogNode
from app.adapters.fetch import FetchRequest, FetchResult
from app.adapters.protocol import ConnectionCheckResult

pytestmark = pytest.mark.usefixtures("isolated_registry")


class FakeOptions(BaseModel):
    host: str
    port: int = 5432
    password: SecretStr


class FakeAdapter:
    """A source that can only be reached, and does nothing else.

    Deliberately minimal: what it must NOT claim is as much under test as what
    a full driver does claim.
    """

    def __init__(self, options: FakeOptions, context: registry.AdapterContext) -> None:
        self.options = options
        self.context = context

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="fake", latency_ms=1)


class NoParams(BaseModel):
    pass


class Sweep(JsonAction[NoParams]):
    name = "sweep"
    title = "Sweep the floor"
    applies_to = frozenset({"directory"})
    acts_on = "children"
    params_model = NoParams

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        return ActionResult(message="swept")


class Polish(JsonAction[NoParams]):
    name = "polish"
    title = "Polish it"
    applies_to = frozenset({"file"})
    acts_on = "node"
    params_model = NoParams

    async def run(self, node_id: str | None, params: NoParams) -> ActionResult:
        return ActionResult(message="polished")


FULL_ACTION_TYPES: tuple[type[Action[Any]], ...] = (Sweep, Polish)


class FullAdapter(FakeAdapter):
    """A source that satisfies every capability protocol there is."""

    async def list_children(self, node_id: str | None) -> list[CatalogNode]:
        return []

    async def path_to(self, node_id: str) -> list[CatalogNode]:
        return []

    async def fetch(self, request: FetchRequest) -> FetchResult:
        raise NotImplementedError

    @classmethod
    def action_types(cls) -> tuple[type[Action[Any]], ...]:
        return FULL_ACTION_TYPES


CONTEXT = registry.AdapterContext(home_dir=Path("/data/users/someone"))


def register_fake(**overrides: Any) -> None:
    arguments: dict[str, Any] = {
        "name": "fake",
        "title": "Fake",
        "category": "sql",
        "description": "A source used by the tests.",
        "options_schema": FakeOptions,
        "adapter_class": FakeAdapter,
    }
    arguments.update(overrides)
    registry.register(**arguments)(arguments["adapter_class"])


def test_registered_type_is_retrievable() -> None:
    register_fake()

    adapter_type = registry.get("fake")

    assert adapter_type.name == "fake"
    assert adapter_type.title == "Fake"
    assert adapter_type.options_schema is FakeOptions


def test_registered_type_carries_its_description() -> None:
    register_fake()

    adapter_type = registry.get("fake")

    assert adapter_type.category == "sql"
    assert adapter_type.description == "A source used by the tests."
    assert adapter_type.adapter_class is FakeAdapter


def test_factory_builds_adapter() -> None:
    register_fake()

    adapter = registry.get("fake").factory(
        FakeOptions(host="h", password=SecretStr("p")), CONTEXT
    )

    assert isinstance(adapter, FakeAdapter)


def test_factory_receives_the_context() -> None:
    """The root a source may reach is computed by the server, never sent."""
    register_fake()

    adapter = registry.get("fake").factory(
        FakeOptions(host="h", password=SecretStr("p")), CONTEXT
    )

    assert adapter.context.home_dir == Path("/data/users/someone")


def test_unknown_type_raises() -> None:
    with pytest.raises(registry.UnknownAdapterType):
        registry.get("nope")


def test_duplicate_registration_raises() -> None:
    register_fake()

    with pytest.raises(ValueError, match="already registered"):
        register_fake(title="Other")


def test_all_types_sorted_by_title() -> None:
    registry._registry.clear()
    register_fake(name="b", title="Zeta")
    register_fake(name="a", title="Alpha")

    assert [t.title for t in registry.all_types()] == ["Alpha", "Zeta"]


def test_category_title_comes_from_the_server() -> None:
    """A second table of names on the client is a table that drifts."""
    assert registry.category_title("sql") == "SQL Databases"
    assert registry.category_title("files") == "Files & Storage"


def test_capabilities_of_a_source_that_only_connects_are_empty() -> None:
    """Nothing is claimed on behalf of a driver that implements nothing."""
    register_fake()

    assert registry.capabilities_of(registry.get("fake")) == []


def test_capabilities_are_read_off_the_protocols_the_driver_satisfies() -> None:
    register_fake(adapter_class=FullAdapter)

    titles = [c.title for c in registry.capabilities_of(registry.get("fake"))]

    assert titles[:3] == ["Browse the catalog", "Locate a node", "Read rows"]


def test_capabilities_carry_the_titles_of_the_declared_actions() -> None:
    """Derived from the action classes themselves, so there is no second list."""
    register_fake(adapter_class=FullAdapter)

    capabilities = registry.capabilities_of(registry.get("fake"))
    manageable = [c.title for c in capabilities if c.group == "manage"]

    assert manageable == ["Sweep the floor", "Polish it"]


def test_exploring_is_grouped_apart_from_changing() -> None:
    register_fake(adapter_class=FullAdapter)

    groups = {c.title: c.group for c in registry.capabilities_of(registry.get("fake"))}

    assert groups["Browse the catalog"] == "explore"
    assert groups["Sweep the floor"] == "manage"

import pytest
from pydantic import BaseModel, SecretStr

from app.adapters import registry
from app.adapters.protocol import ConnectionCheckResult

pytestmark = pytest.mark.usefixtures("isolated_registry")


class FakeOptions(BaseModel):
    host: str
    port: int = 5432
    password: SecretStr


class FakeAdapter:
    def __init__(self, options: FakeOptions) -> None:
        self.options = options

    async def check_connection(self) -> ConnectionCheckResult:
        return ConnectionCheckResult(ok=True, message="fake", latency_ms=1)


def test_registered_type_is_retrievable() -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    adapter_type = registry.get("fake")

    assert adapter_type.name == "fake"
    assert adapter_type.title == "Fake"
    assert adapter_type.options_schema is FakeOptions


def test_factory_builds_adapter() -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    adapter = registry.get("fake").factory(
        FakeOptions(host="h", password=SecretStr("p"))
    )

    assert isinstance(adapter, FakeAdapter)


def test_unknown_type_raises() -> None:
    with pytest.raises(registry.UnknownAdapterType):
        registry.get("nope")


def test_duplicate_registration_raises() -> None:
    registry.register(name="fake", title="Fake", options_schema=FakeOptions)(FakeAdapter)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(name="fake", title="Other", options_schema=FakeOptions)(
            FakeAdapter
        )


def test_all_types_sorted_by_title() -> None:
    registry._registry.clear()
    registry.register(name="b", title="Zeta", options_schema=FakeOptions)(FakeAdapter)
    registry.register(name="a", title="Alpha", options_schema=FakeOptions)(FakeAdapter)

    assert [t.title for t in registry.all_types()] == ["Alpha", "Zeta"]


def test_secret_field_names_finds_only_secretstr_fields() -> None:
    assert registry.secret_field_names(FakeOptions) == {"password"}

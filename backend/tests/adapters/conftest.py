from collections.abc import Generator

import pytest

from app.adapters import registry


@pytest.fixture
def isolated_registry() -> Generator[None]:
    """Isolate the registry so registrations made by a test do not leak."""
    saved = dict(registry._registry)
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)

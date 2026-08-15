from collections.abc import Generator

import pytest

from app.adapters import registry


@pytest.fixture
def isolated_registry() -> Generator[None]:
    """Изолирует реестр, чтобы регистрации из теста не протекали в другие."""
    saved = dict(registry._registry)
    try:
        yield
    finally:
        registry._registry.clear()
        registry._registry.update(saved)

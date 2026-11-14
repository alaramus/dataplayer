"""Putting a stand-in on the application's state for one test."""

from typing import Any

import pytest

from app.main import app


def replace_state(monkeypatch: pytest.MonkeyPatch, name: str, value: Any) -> None:
    """`monkeypatch.setattr(app.state, ...)` without its trap.

    From pytest 9.2 setattr reads the old value from the instance `__dict__`,
    where Starlette's State keeps nothing, so undoing it deletes the real one
    and every later test runs without it. State's own dictionary is patched
    instead.
    """
    monkeypatch.setitem(app.state._state, name, value)

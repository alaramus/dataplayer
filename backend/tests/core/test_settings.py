"""What a deployment has to supply, and whether the pipeline supplies it.

Settings name `../.env`, so a run started from `backend/` reads whatever the
developer keeps there and fills the gaps CI will not fill. Three pipelines have
now gone red on a required setting a local run appeared to prove present, the
last of them on `QUERY_CONTENT_KEY`.

The rehearsal in `docs/architecture/backend.md` catches this and needs Docker,
Linux and a clean checkout, which is why nobody runs it. This does the same
thing in a second, in the suite that is run anyway: a setting with no default
is a setting somebody must declare, and there are exactly two places that
declare them.
"""

import re
from pathlib import Path

from pydantic_core import PydanticUndefined

from app.core.config import Settings

REPOSITORY = Path(__file__).resolve().parents[3]


def _required() -> set[str]:
    """Every setting with no default: what a deployment has to supply."""
    return {
        name
        for name, field in Settings.model_fields.items()
        if field.default is PydanticUndefined and field.default_factory is None
    }


def _declared_in_pipeline() -> set[str]:
    """The variables the backend job of the pipeline sets."""
    text = (REPOSITORY / ".gitlab-ci.yml").read_text(encoding="utf-8")
    block = text.split("\nbackend:", 1)[1].split("\n  cache:", 1)[0]
    block = block.split("variables:", 1)[1]
    return {
        match.group(1)
        for match in re.finditer(r"^\s{4}([A-Z_][A-Z0-9_]*):", block, re.MULTILINE)
    }


def _declared_in_example() -> set[str]:
    """The names the example environment file offers a deployment."""
    text = (REPOSITORY / ".env.example").read_text(encoding="utf-8")
    return {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_the_pipeline_declares_every_setting_that_has_no_default() -> None:
    missing = _required() - _declared_in_pipeline()

    assert not missing, (
        f"{', '.join(sorted(missing))} has no default and is not set by the "
        "backend job in .gitlab-ci.yml; the pipeline will fail before it runs "
        "a single check"
    )


def test_the_example_environment_offers_every_setting_that_has_no_default() -> None:
    """AGENTS.md rule 5, checked rather than remembered."""
    missing = _required() - _declared_in_example()

    assert not missing, (
        f"{', '.join(sorted(missing))} has no default and is not in "
        ".env.example; nobody setting the project up would know to supply it"
    )

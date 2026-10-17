"""Framework hints from table names, without reading application data."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.translation import N_

FrameworkId = Literal["django", "alembic", "liquibase", "wordpress"]


class DetectedFramework(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: FrameworkId
    title: str
    table_filter: str


@dataclass(frozen=True)
class FrameworkSignature:
    marker: str
    result: DetectedFramework


SIGNATURES = (
    FrameworkSignature(
        "django_content_type",
        DetectedFramework(id="django", title=N_("Django"), table_filter="django_"),
    ),
    FrameworkSignature(
        "alembic_version",
        DetectedFramework(
            id="alembic", title=N_("Alembic"), table_filter="alembic_version"
        ),
    ),
    FrameworkSignature(
        "databasechangelog",
        DetectedFramework(
            id="liquibase", title=N_("Liquibase"), table_filter="databasechangelog"
        ),
    ),
    FrameworkSignature(
        "wp_options",
        DetectedFramework(id="wordpress", title=N_("WordPress"), table_filter="wp_"),
    ),
)


def detect_frameworks(table_names: Sequence[str]) -> list[DetectedFramework]:
    """Recognize conventional markers within one schema, never across schemas."""
    names = {name.casefold() for name in table_names}
    return [signature.result for signature in SIGNATURES if signature.marker in names]

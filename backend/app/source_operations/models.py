"""What an owned source operation carries, and how its outcome is told (D123).

Stored in the job's `parameters` and validated whenever it is read back: the
column is storage, not a way of passing dictionaries between layers. Nothing in
it is a secret; the connection's credentials stay in the connection.
"""

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.operations import (
    MAX_OPERATION_TARGETS,
    ObservedState,
    OperationTarget,
)
from app.core.access import Access

TargetOutcome = Literal[
    "pending", "running", "completed", "already", "refused", "rolled_back", "unknown",
]

# How each outcome is counted in the one sentence a finished job says, in this order.
_TOLD: tuple[tuple[TargetOutcome, str], ...] = (
    ("completed", "done"),
    ("already", "already as requested"),
    ("refused", "refused"),
    ("rolled_back", "rolled back"),
    ("unknown", "outcome unknown"),
    ("running", "in progress"),
    ("pending", "not attempted"),
)
_MESSAGE_LIMIT = 500


class TargetRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: OperationTarget
    outcome: TargetOutcome = "pending"
    # Why it was refused or is unknown, in the application's words.
    message: str | None = Field(default=None, max_length=500)
    # What reading it back found afterwards; absent when it was not read.
    observed: ObservedState | None = None


class SourceOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    action: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=100)
    node_id: str | None = Field(default=None, max_length=2000)
    # The action's own form, validated again by the action for every unit.
    params: dict[str, Any]
    requires: Access
    # The connection's updated_at when the plan was drawn; any edit stops the job.
    connector_revision: str | None
    summary: str = Field(min_length=1, max_length=300)
    unit_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    targets: list[TargetRecord] = Field(min_length=1, max_length=MAX_OPERATION_TARGETS)

    def told(self, stopped: str | None = None) -> str:
        """One sentence for the job's message: what happened to how many."""
        counts = Counter(record.outcome for record in self.targets)
        parts = ", ".join(f"{counts[outcome]} {words}" for outcome, words in _TOLD if counts[outcome])
        sentence = f"{self.summary}: {parts}" if stopped is None else f"{self.summary}: {parts}. {stopped}"
        return sentence if len(sentence) <= _MESSAGE_LIMIT else f"{sentence[:_MESSAGE_LIMIT - 1]}…"

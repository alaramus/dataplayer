"""Source work too long for a request: a reviewed, fixed set of targets (D123).

The source plans the work, carries out one target at a time and reads targets
back. Everything around that — admission, durable outcomes, cancellation and
restart — belongs to `app.source_operations`, which no adapter imports.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

# More targets than this is a narrower selection, never a truncated or split job.
MAX_OPERATION_TARGETS = 1000

# What one unit did: changed its target, or found it already as requested.
UnitOutcome = Literal["completed", "already"]
# What reading a target back found.
ObservedState = Literal["as_requested", "unchanged", "gone"]


class OperationTarget(BaseModel):
    """One object of the source a unit of work is about, named as the source names it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: str = Field(min_length=1, max_length=63)
    name: str = Field(min_length=1, max_length=63)


class OperationPlan(BaseModel):
    """What was reviewed, fixed at admission: the job does exactly these targets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(min_length=1, max_length=300)
    # What every unit re-checks before it runs: the parts of the plan that must
    # not change while the job works through its targets. Their states may.
    unit_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    targets: tuple[OperationTarget, ...] = Field(
        min_length=1, max_length=MAX_OPERATION_TARGETS,
    )


@runtime_checkable
class ProducesJob(Protocol):
    """An action carried out as an owned job, one target per source transaction.

    `run_unit` raises ActionRefused when the source refused and nothing changed,
    and AdapterError when the unit may have committed without it being
    confirmed. A cancelled unit propagates CancelledError once the driver has
    cancelled and rolled back what was running.
    """

    async def plan_job(
        self, node_id: str | None, raw: Mapping[str, Any], reviewed_fingerprint: str,
    ) -> OperationPlan: ...

    async def run_unit(
        self, node_id: str | None, raw: Mapping[str, Any], unit_fingerprint: str,
        target: OperationTarget,
    ) -> UnitOutcome: ...

    async def observe(
        self, node_id: str | None, raw: Mapping[str, Any], targets: Sequence[OperationTarget],
    ) -> list[ObservedState]: ...

"""A pipeline's run as its job keeps it (D177): the links it carries out, in
order, and what became of each.

What each step runs is copied in when the run starts, so an edit made while
it runs is kept for the next run and changes nothing in this one. Never a
secret: a paste names nodes and choices, and the job row is not encrypted.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.paste.models import PasteRun
from app.connectors.paste.transfer import Transfer
from app.pipelines.models import MAX_LABEL, MAX_LINKS, MAX_NAME

# `waiting` has not started; `not_run` never will, the run having stopped
# before it.
StepOutcome = Literal["waiting", "running", "done", "failed", "not_run"]

# A job's sentence fits its column (Job.message); a step's, its field here.
JOB_SAYS = 512
STEP_SAYS = 600


def clipped(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStep(_Strict):
    """One link of the run, and what it did."""

    link_id: uuid.UUID
    title: str = Field(max_length=MAX_LABEL)
    # The connections by the names their cards keep, and the ends as a
    # sentence names them: "Sales · orders".
    source_connection: str = Field(max_length=MAX_LABEL)
    destination_connection: str = Field(max_length=MAX_LABEL)
    source_label: str = Field(max_length=2 * MAX_LABEL + 3)
    target_label: str = Field(max_length=2 * MAX_LABEL + 9)
    destination_connector_id: uuid.UUID
    # Whether carrying it out changes the source connection too: a move.
    changes_source: bool = False
    # The paste it stands for. Where an end is what an earlier step makes
    # (D178), that step is named here and its node is put in when this runs.
    paste: PasteRun
    reads: uuid.UUID | None = None
    writes_into: uuid.UUID | None = None
    outcome: StepOutcome = "waiting"
    message: str | None = Field(default=None, max_length=STEP_SAYS)
    # A transfer's own payload once it is planned, as a transfer job keeps it.
    transfer: Transfer | None = None
    # The node it made in this run, and the name it was made with.
    made: str | None = Field(default=None, max_length=4096)
    made_name: str | None = Field(default=None, max_length=255)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunRecord(_Strict):
    version: Literal[1] = 1
    pipeline_id: uuid.UUID
    pipeline_name: str = Field(max_length=MAX_NAME)
    # The time a schedule came, when the schedule started it (D179).
    scheduled_for: datetime | None = None
    steps: list[RunStep] = Field(min_length=1, max_length=MAX_LINKS)

    def step_of(self, link_id: uuid.UUID) -> RunStep | None:
        return next((step for step in self.steps if step.link_id == link_id), None)

    def not_run_after(self, index: int) -> None:
        for step in self.steps[index + 1 :]:
            if step.outcome == "waiting":
                step.outcome = "not_run"

    def _rest(self, said: str) -> str:
        rest = sum(1 for step in self.steps if step.outcome in ("waiting", "not_run"))
        return clipped(said if rest == 0 else f"{said}; {rest} not run", JOB_SAYS)

    def ran(self) -> str:
        """The run's sentence when no step failed."""
        done = sum(1 for step in self.steps if step.outcome == "done")
        if done < len(self.steps):
            # A link reading what another made nothing of in this run (D178).
            return self._rest(f"{done} of {len(self.steps)} links ran")
        if len(self.steps) == 1:
            return clipped(self.steps[0].message or "Its one link ran", JOB_SAYS)
        return f"All {len(self.steps)} links ran"

    def failed_at(self, index: int) -> str:
        """The run's sentence when the step at `index` failed."""
        step = self.steps[index]
        said = f"Stopped at {index + 1} of {len(self.steps)}, {step.title}"
        return self._rest(f"{said}: {step.message}" if step.message else said)

    def stopped(self) -> str:
        """The run's sentence when its owner stopped it."""
        count = len(self.steps)
        at = next((index for index, step in enumerate(self.steps) if step.outcome == "failed"), None)
        if at is not None:
            return self._rest(f"Stopped on request at {at + 1} of {count}, {self.steps[at].title}")
        done = sum(1 for step in self.steps if step.outcome == "done")
        if done == 0:
            return self._rest("Stopped on request before its first link")
        return self._rest(f"Stopped on request after {done} of {count}")
